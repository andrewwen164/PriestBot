"""Ensure our ZIP layout stays installable by the *previous* v0.21 updater.

The v0.21 updater has a strict root allowlist. The v0.22 release previously
failed because it added GPU_TRAINING.md and setup_vision_pytorch_windows.bat.
"""
from pathlib import Path
from priestbot.install_core import inspect_folder, inspect_zip, ROOT_FILES
import zipfile

# Snapshot of ROOT_FILES from the shipping v0.21 updater, not the latest one.
LEGACY_ROOT = {
    "README.md", ".gitignore", "launch.py", "requirements.txt",
    "run_windows.bat", "setup_windows.bat", "install_windows.bat",
    "installer.py", "updater_runner.py", "version.json",
}

def test_release_has_no_new_root_files():
    root = Path(__file__).resolve().parents[1]
    assert ROOT_FILES == LEGACY_ROOT
    actual_roots = {p.name for p in root.iterdir() if p.is_file()}
    assert actual_roots <= LEGACY_ROOT

def test_zip_members_compatible_with_prior_updater(tmp_path):
    root = Path(__file__).resolve().parents[1]
    _, files = inspect_folder(root)
    assert "GPU_TRAINING.md" not in files
    assert "setup_vision_pytorch_windows.bat" not in files
    zippath = tmp_path / "release.zip"
    with zipfile.ZipFile(zippath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(root / name, name)
    version, members = inspect_zip(zippath)
    assert version == "0.25.2"
    assert set(members) == set(files)
