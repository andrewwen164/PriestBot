"""v0.9's critical package/upgrade/migration behavior, without Windows side effects."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import zipfile

import pytest

from priestbot import install_core as core


@pytest.fixture
def release(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dest = tmp_path / "release"
    dest.mkdir()
    _, files = core.inspect_folder(root)
    for path in files:
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, target)
    return dest


def package_zip(release, out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        _, files = core.inspect_folder(release)
        for name in files:
            z.write(release / name, name)
    return out


def test_release_has_all_expected_assets(release):
    version, files = core.inspect_folder(release)
    assert version == "0.24.1"
    assert core.REQUIRED.issubset(set(files))


def test_zip_validated_extracted_with_own_paths(release, tmp_path):
    src = package_zip(release, tmp_path / "release.zip")
    version, files = core.inspect_zip(src)
    assert version == "0.24.1"
    out = tmp_path / "out"
    out.mkdir()
    assert core.extract_checked(src, out) == version
    assert (out / "priestbot" / "app.py").is_file()
    assert set(files) == set(f.relative_to(out).as_posix() for f in out.rglob('*') if f.is_file())


@pytest.mark.parametrize("bad_name", [
    "../config.json", "config.json", ".venv/Scripts/python.exe",
    "addons/OtherAddon/hack.lua", "priestbot/../../bad.py",
    "C:/Windows/system.ini", "/absolute.py", "priestbot\\app.py",
])
def test_disallow_unexpected_archive_paths(release, tmp_path, bad_name):
    out = package_zip(release, tmp_path / "release.zip")
    with zipfile.ZipFile(out, 'a') as z:
        z.writestr(bad_name, b"not permitted")
    with pytest.raises(ValueError):
        core.inspect_zip(out)


def test_reject_duplicate_archive_paths(release, tmp_path):
    out = package_zip(release, tmp_path / "release.zip")
    with zipfile.ZipFile(out, 'a') as z:
        z.writestr('launch.py', 'print("different")')
    with pytest.raises(ValueError, match="duplicate"):
        core.inspect_zip(out)


def test_reject_missing_required_files(tmp_path):
    out = tmp_path / "empty.zip"
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('version.json', '{"version":"0.9"}')
    with pytest.raises(ValueError, match="missing"):
        core.inspect_zip(out)


def test_preserve_config_venv_settings_and_shortcut_across_upgrade(release, tmp_path):
    install = tmp_path / 'PriestBot'
    install.mkdir()
    interpreter = core.python_in_venv(install)
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"fake venv (do not replace)")
    (install / 'config.json').write_text('{"keys":{"smite":"q"}}')
    (install / core.SETTINGS_FILENAME).write_text('{"addons_dir":"X:/World of Warcraft/AddOns"}')
    shortcut = install / 'PriestBot.lnk'
    shortcut.write_bytes(b"placeholder link")
    (install / 'launch.py').write_text('old version')
    # Fake unchanged requirements -> no package-install invocation.
    (install / 'requirements.txt').write_bytes((release / 'requirements.txt').read_bytes())
    version = core.apply_release(release, install)
    assert version == '0.24.1'
    assert interpreter.read_bytes() == b"fake venv (do not replace)"
    assert json.loads((install / 'config.json').read_text())['keys']['smite'] == 'q'
    assert json.loads((install / core.SETTINGS_FILENAME).read_text())['addons_dir'].startswith('X:')
    assert shortcut.read_bytes() == b'placeholder link'
    assert (install / 'launch.py').read_bytes() == (release / 'launch.py').read_bytes()
    backups = list((install / 'backups').rglob('launch.py'))
    assert len(backups) == 1 and backups[0].read_text() == 'old version'
    # Update again and guarantee user state remains untouched.
    core.apply_release(release, install)
    assert json.loads((install / 'config.json').read_text())['keys']['smite'] == 'q'


def test_dependencies_run_on_first_venv_creation_even_when_requirements_equal(release, tmp_path, monkeypatch):
    install = tmp_path / 'inst'
    install.mkdir()
    (install / 'requirements.txt').write_bytes((release / 'requirements.txt').read_bytes())
    calls = []
    def run(args, check=False):
        calls.append(args)
        if args[1:3] == ['-m', 'venv']:
            python = core.python_in_venv(install)
            python.parent.mkdir(parents=True)
            python.write_bytes(b'fake')
    monkeypatch.setattr(core.subprocess, 'run', run)
    core.ensure_dependencies(release, install)
    assert len(calls) == 2
    assert calls[0][1:3] == ['-m', 'venv']
    assert calls[1][1:4] == ['-m', 'pip', 'install']


def test_addon_update_only_touches_owned_files(release, tmp_path):
    addons = tmp_path / 'game' / 'Interface' / 'AddOns'
    dest = addons / 'PriestBridge'
    dest.mkdir(parents=True)
    (dest / 'custom_settings.lua').write_text('keep')
    (dest / 'PriestBridge.lua').write_text('previous')
    (addons / 'OtherAddon').mkdir()
    (addons / 'OtherAddon' / 'saved.lua').write_text('do not delete')
    assert core.copy_addon(release / 'addons' / 'PriestBridge', addons, tmp_path / 'backups')
    assert (dest / 'custom_settings.lua').read_text() == 'keep'
    assert (addons / 'OtherAddon' / 'saved.lua').read_text() == 'do not delete'
    assert (dest / 'PriestBridge.lua').read_bytes() == (release / 'addons' / 'PriestBridge' / 'PriestBridge.lua').read_bytes()
    assert not core.copy_addon(release / 'addons' / 'PriestBridge', addons, tmp_path / 'backups')
    assert len(list((tmp_path / 'backups').rglob('PriestBridge.lua'))) == 1


def test_wrong_game_folder_never_gets_created(release, tmp_path):
    with pytest.raises(FileNotFoundError):
        core.copy_addon(release / 'addons' / 'PriestBridge', tmp_path / 'missing' / 'AddOns', tmp_path / 'backups')


def test_failed_update_rolls_back_replaced_files(release, tmp_path, monkeypatch):
    install = tmp_path / 'PriestBot'
    install.mkdir()
    (install / 'launch.py').write_text('OLD LAUNCHER')
    # Fail part-way through replacement (order is listing order).
    files = ['launch.py', 'priestbot/app.py']
    original_replace = core.os.replace
    def fail_on_app(src, dest):
        if Path(dest).name == 'app.py':
            raise PermissionError('simulate file lock')
        return original_replace(src, dest)
    monkeypatch.setattr(core.os, 'replace', fail_on_app)
    with pytest.raises(PermissionError):
        core.copy_release_files(release, install, files)
    assert (install / 'launch.py').read_text() == 'OLD LAUNCHER'
    assert not (install / 'priestbot' / 'app.py').exists()


def test_settings_default_path_and_preservation(tmp_path):
    root = tmp_path / 'install'
    settings = core.load_settings(root)
    assert settings['addons_dir'] == core.DEFAULT_WOW_ADDONS
    settings['addons_dir'] = 'D:/Games/WoW/Interface/AddOns'
    core.save_settings(root, settings)
    assert core.load_settings(root)['addons_dir'].startswith('D:')
