from pathlib import Path
from PIL import Image
from priestbot.icon_asset import create_priest_icon
from priestbot import install_core as core


def test_priest_classic_icon_is_valid_multisize_ico(tmp_path):
    icon = create_priest_icon(tmp_path)
    with Image.open(icon) as image:
        assert image.format == "ICO"
        assert (32, 32) in image.ico.sizes()
        assert (256, 256) in image.ico.sizes()
    assert create_priest_icon(tmp_path) == icon


def test_previous_zip_updater_still_accepts_icon_release(tmp_path):
    root = Path(__file__).resolve().parents[1]
    assert core.allowed_release_path("priestbot/icon_asset.py")
    assert not core.allowed_release_path("assets/PriestBot.ico")
    version, files = core.inspect_folder(root)
    assert version == "0.23.3"
    assert "priestbot/icon_asset.py" in files
    assert "assets/PriestBot.ico" not in files


def test_windows_shortcut_points_to_local_priest_icon(tmp_path, monkeypatch):
    from priestbot import install_core
    calls = []
    monkeypatch.setattr(install_core.sys, "platform", "win32")
    monkeypatch.setattr(install_core.subprocess, "run", lambda args, check: calls.append(args))
    install_core.create_desktop_shortcut(tmp_path)
    assert calls
    powershell = calls[-1][-1]
    assert 'PriestBot.ClassicPriest.v2.ico,0' in powershell
    assert 'Remove-Item -LiteralPath $shortcut -Force' in powershell
    assert 'shell32.dll' not in powershell
    assert (tmp_path / 'PriestBot.ClassicPriest.v2.ico').is_file()
