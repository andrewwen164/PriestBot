from priestbot import install_core
from priestbot.icon_asset import create_priest_icon, ICON_FILENAME


def test_versioned_icon_name_bypasses_previous_shell_cache(tmp_path):
    new = create_priest_icon(tmp_path)
    assert new.name == ICON_FILENAME == "PriestBot.ClassicPriest.v2.ico"
    assert new.is_file()
    assert not (tmp_path / "PriestBot.ico").exists()


def test_repair_shortcut_replaces_link_and_refreshes(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(install_core.sys, "platform", "win32")
    monkeypatch.setattr(install_core.subprocess, "run", lambda args, check: calls.append(args))
    install_core.create_desktop_shortcut(tmp_path)
    script = calls[0][-1]
    assert "PriestBot.lnk" in script
    assert "Remove-Item -LiteralPath $shortcut -Force" in script
    assert "PriestBot.ClassicPriest.v2.ico,0" in script
    assert (tmp_path / ICON_FILENAME).exists()


def test_first_launch_repairs_older_updater_shortcut_once(monkeypatch, tmp_path):
    calls=[]
    monkeypatch.setattr(install_core.sys, "platform", "win32")
    monkeypatch.setattr(install_core, "create_desktop_shortcut", lambda root: calls.append(root))
    assert install_core.ensure_shortcut_icon_migrated(tmp_path)
    assert calls == [tmp_path]
    assert not install_core.ensure_shortcut_icon_migrated(tmp_path)
    assert calls == [tmp_path]
