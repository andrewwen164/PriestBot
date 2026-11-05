"""Local, opt-in ZIP installation and upgrade helpers for PriestBot.

No downloads or game-memory access. Only the packaged application files and the
PriestBridge addon may be replaced; state/config/.venv are preserved.
"""
from __future__ import annotations

from datetime import datetime
import ctypes
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

APP_NAME = "PriestBot"
DEFAULT_WOW_ADDONS = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns"
SETTINGS_FILENAME = "install_settings.json"
STATUS_FILENAME = "last_update_status.json"
APP_VERSION = "0.23.1"
REQUIRED = {
    "launch.py", "requirements.txt", "run_windows.bat",
    "priestbot/__init__.py", "priestbot/app.py", "priestbot/install_core.py",
    "updater_runner.py", "addons/PriestBridge/PriestBridge.toc",
    "addons/PriestBridge/PriestBridge.lua", "version.json",
}
ROOT_FILES = {
    "README.md", ".gitignore", "launch.py", "requirements.txt",
    "run_windows.bat", "setup_windows.bat", "install_windows.bat",
    "installer.py", "updater_runner.py", "version.json",
}
MAX_RELEASE_BYTES = 32 * 1024 * 1024


def installed_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def allowed_release_path(name: str) -> bool:
    """Only expected app sources, tests and two owned addon files."""
    if "\\" in name or ":" in name or name.startswith("/"):
        return False
    parts = PurePosixPath(name).parts
    if not parts or any(p in ("..", ".") for p in parts):
        return False
    if name in ROOT_FILES:
        return True
    if len(parts) == 2 and parts[0] == "priestbot":
        return parts[1].endswith(".py") and parts[1].replace("_", "").replace(".py", "").isalnum()
    if len(parts) == 2 and parts[0] == "tests":
        return parts[1].startswith("test_") and parts[1].endswith(".py") and parts[1][5:-3].replace("_", "").isalnum()
    return name in {"addons/PriestBridge/PriestBridge.lua", "addons/PriestBridge/PriestBridge.toc"}


def verify_members(names: list[str]) -> list[str]:
    files = [n for n in names if not n.endswith("/")]
    if len(files) != len(set(files)):
        raise ValueError("Release contains duplicate file paths")
    unexpected = [n for n in files if not allowed_release_path(n)]
    if unexpected:
        raise ValueError("Release contains unexpected/unsafe paths: " + ", ".join(unexpected[:5]))
    missing = REQUIRED - set(files)
    if missing:
        raise ValueError("Not a complete PriestBot release; missing: " + ", ".join(sorted(missing)))
    return files


def inspect_zip(zip_path: Path) -> tuple[str, list[str]]:
    """Validate archive structure, file types, size and declared version."""
    with zipfile.ZipFile(zip_path) as z:
        files = verify_members(z.namelist())
        total_size = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            unix_mode = (info.external_attr >> 16)
            if stat.S_ISLNK(unix_mode):
                raise ValueError("Release contains a symlink")
            if info.file_size > 8 * 1024 * 1024:
                raise ValueError("An archive file is too large")
            total_size += info.file_size
            if total_size > MAX_RELEASE_BYTES:
                raise ValueError("Release exceeds size limit")
        if z.testzip() is not None:
            raise ValueError("Release ZIP checksum failed")
        version = json.loads(z.read("version.json").decode("utf-8"))["version"]
        if not isinstance(version, str) or not version or len(version) > 32:
            raise ValueError("Invalid version metadata")
    return version, files


def extract_checked(zip_path: Path, destination: Path) -> str:
    version, files = inspect_zip(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        for name in files:
            out = destination / name
            out.parent.mkdir(parents=True, exist_ok=True)
            # Extract by known path rather than ZipFile.extract (no traversal).
            with z.open(name) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return version


def inspect_folder(source: Path) -> tuple[str, list[str]]:
    files = [p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()
             and not any(part.startswith(".") and part != ".gitignore" for part in p.relative_to(source).parts)
             and "__pycache__" not in p.parts]
    # Packaging folder can have pytest/test artifacts; prefer explicitly allowed files.
    files = [f for f in files if allowed_release_path(f)]
    verify_members(files)
    return json.loads((source / "version.json").read_text(encoding="utf-8"))["version"], files


def load_settings(root: Path) -> dict:
    defaults = {"addons_dir": DEFAULT_WOW_ADDONS, "addon_pending": False}
    path = root / SETTINGS_FILENAME
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for name in defaults:
            if name in raw:
                defaults[name] = raw[name]
    return defaults


def save_settings(root: Path, settings: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (SETTINGS_FILENAME + ".tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, root / SETTINGS_FILENAME)


def write_status(root: Path, success: bool, message: str) -> None:
    (root / STATUS_FILENAME).write_text(json.dumps({
        "success": success, "message": message, "time": datetime.now().isoformat(timespec="seconds")
    }, indent=2) + "\n", encoding="utf-8")


def log(root: Path, message: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "update.log").open("a", encoding="utf-8") as f:
        f.write(datetime.now().isoformat(timespec="seconds") + " " + message + "\n")
    print(message, flush=True)


def python_in_venv(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def ensure_dependencies(source: Path, dest: Path) -> None:
    vpython = python_in_venv(dest)
    created = not vpython.is_file()
    if created:
        log(dest, "Creating virtual environment (first install only)...")
        subprocess.run([sys.executable, "-m", "venv", str(dest / ".venv")], check=True)
    old = dest / "requirements.txt"
    new = source / "requirements.txt"
    if not created and old.is_file() and old.read_bytes() == new.read_bytes():
        log(dest, "Python dependencies unchanged; reusing existing .venv")
        return
    log(dest, "Installing dependencies required by this release...")
    subprocess.run([str(vpython), "-m", "pip", "install", "-r", str(new)], check=True)


def copy_release_files(source: Path, dest: Path, files: list[str]) -> Path:
    """Replace owned files with a backup and rollback on copy errors."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = dest / "backups" / ("release-" + stamp)
    copied: list[tuple[Path, Path | None]] = []
    try:
        for relative in files:
            src = source / relative
            target = dest / relative
            previous = backup / relative if target.exists() else None
            if previous is not None:
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, previous)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_target = target.with_name(target.name + ".updating")
            try:
                shutil.copy2(src, temp_target)
                os.replace(temp_target, target)
            finally:
                temp_target.unlink(missing_ok=True)
            copied.append((target, previous))
    except Exception:
        for target, previous in reversed(copied):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                shutil.copy2(previous, target)
        raise
    return backup


def apply_release(source: Path, dest: Path, *, install_deps: bool = True) -> str:
    version, files = inspect_folder(source)
    dest.mkdir(parents=True, exist_ok=True)
    if install_deps:
        ensure_dependencies(source, dest)
    backup = copy_release_files(source, dest, files)
    log(dest, f"Updated PriestBot files to v{version}; backup: {backup}")
    return version


def copy_addon(source_dir: Path, addons_dir: Path, backup_root: Path) -> bool:
    """Update only PriestBridge's own .toc/.lua files, leaving other addons alone."""
    if not addons_dir.is_dir():
        raise FileNotFoundError(f"WoW AddOns directory not found: {addons_dir}")
    target = addons_dir / "PriestBridge"
    source_files = ["PriestBridge.lua", "PriestBridge.toc"]
    for name in source_files:
        if not (source_dir / name).is_file():
            raise FileNotFoundError(f"Missing packaged addon file: {name}")
    if all((target / n).is_file() and (target / n).read_bytes() == (source_dir / n).read_bytes()
           for n in source_files):
        return False
    backup = backup_root / ("addon-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    replaced = []
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name in source_files:
            existing = target / name
            saved = backup / name if existing.is_file() else None
            if saved:
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing, saved)
            temp_target = target / (name + ".updating")
            try:
                shutil.copy2(source_dir / name, temp_target)
                os.replace(temp_target, existing)
            finally:
                # If permission denial happens before temp file exists, ignore it.
                try: temp_target.unlink(missing_ok=True)
                except OSError: pass
            replaced.append((existing, saved))
    except Exception:
        for existing, saved in reversed(replaced):
            try:
                if saved:
                    shutil.copy2(saved, existing)
                else:
                    existing.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return True


def request_admin_addon_install(root: Path) -> bool:
    """Use UAC for addon copy ONLY, then wait for exit code. Windows only."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]
    params = subprocess.list2cmdline([str(root / "updater_runner.py"), "--addon-only", "--install-dir", str(root)])
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = str(python_in_venv(root))
    info.lpParameters = params
    info.lpDirectory = str(root)
    info.nShow = 1
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        log(root, f"Addon UAC was canceled/unavailable (Windows error {ctypes.get_last_error()}).")
        return False
    try:
        wait = kernel.WaitForSingleObject(info.hProcess, 120_000)
        if wait != 0:  # timeout or error
            log(root, "Addon installer did not finish within 2 minutes")
            return False
        exit_code = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)) and exit_code.value == 0)
    finally:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(info.hProcess)


def install_addon_for_user(root: Path, *, allow_elevation: bool = True) -> bool:
    settings = load_settings(root)
    directory = Path(settings["addons_dir"])
    source_dir = root / "addons" / "PriestBridge"
    try:
        changed = copy_addon(source_dir, directory, root / "backups" / "addons")
        log(root, f"PriestBridge {'installed/updated' if changed else 'already up to date'}: {directory}")
        settings["addon_pending"] = False
        save_settings(root, settings)
        return True
    except (PermissionError, OSError) as exc:
        log(root, f"Normal addon copy failed: {exc}")
        if allow_elevation and sys.platform == "win32" and request_admin_addon_install(root):
            settings["addon_pending"] = False
            save_settings(root, settings)
            return True
        settings["addon_pending"] = True
        save_settings(root, settings)
        log(root, "Addon update pending. Retry using Install/Repair PriestBridge in the app.")
        return False


def create_desktop_shortcut(root: Path) -> None:
    """Create a standard user-level .lnk in Windows' actual redirected Desktop folder."""
    if sys.platform != "win32":
        return
    def ps_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
    from .icon_asset import create_priest_icon
    icon_path = create_priest_icon(root)
    script = (
        "$desktop=[Environment]::GetFolderPath('DesktopDirectory');"
        "$shell=New-Object -ComObject WScript.Shell;"
        "$link=$shell.CreateShortcut((Join-Path $desktop 'PriestBot.lnk'));"
        "$link.TargetPath=" + ps_literal(str(root / "run_windows.bat")) + ";"
        "$link.WorkingDirectory=" + ps_literal(str(root)) + ";"
        "$link.Description='PriestBot - private server companion';"
        "$link.IconLocation=" + ps_literal(str(icon_path) + ",0") + ";"
        "$link.Save()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], check=True)
    log(root, "Desktop shortcut created: PriestBot")


def restart_application(root: Path) -> None:
    vpython = python_in_venv(root)
    if not vpython.is_file():
        raise FileNotFoundError("Virtual environment missing; run install_windows.bat again")
    kwargs = {"cwd": str(root)}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen([str(vpython), str(root / "launch.py")], **kwargs)
