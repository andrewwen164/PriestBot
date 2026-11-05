"""External updater: runs after the GUI exits; supports elevated addon-only mode."""
from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import sys
import tempfile
import time

from priestbot.install_core import (
    apply_release, extract_checked, install_addon_for_user, installed_dir,
    create_desktop_shortcut,
    log, restart_application, write_status,
)


def wait_for_pid_exit(pid: int, timeout: int = 60) -> None:
    if not pid or pid == 0:
        return
    if sys.platform == "win32":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:  # Already gone
            return
        try:
            if kernel.WaitForSingleObject(handle, timeout * 1000) != 0:
                raise TimeoutError("Old PriestBot process did not close; update canceled")
        finally:
            kernel.CloseHandle(handle)
    else:
        # Only used by Linux unit tests; actual deployments are Windows.
        import os
        for _ in range(timeout * 10):
            try: os.kill(pid, 0)
            except ProcessLookupError: return
            time.sleep(.1)
        raise TimeoutError("Old process did not exit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--install-dir", type=Path, default=installed_dir())
    parser.add_argument("--addon-only", action="store_true")
    args = parser.parse_args()
    root = args.install_dir.resolve()
    if args.addon_only:
        try:
            return 0 if install_addon_for_user(root, allow_elevation=False) else 1
        except Exception as exc:
            log(root, "ADDON UPDATE FAILED: " + repr(exc))
            return 1
    if not args.zip:
        parser.error("--zip is required except in --addon-only mode")
    try:
        version_label = str(args.zip)
        log(root, "Preparing ZIP update: " + version_label)
        wait_for_pid_exit(args.parent_pid)
        with tempfile.TemporaryDirectory(prefix="priestbot-update-") as temp:
            version = extract_checked(args.zip, Path(temp))
            apply_release(Path(temp), root)
        # Refresh the shortcut icon as part of every successful upgrade.
        # A failure to refresh the shortcut must not discard the upgrade.
        try:
            create_desktop_shortcut(root)
        except Exception as exc:
            log(root, "Desktop shortcut icon refresh failed: " + repr(exc))
        addon_done = install_addon_for_user(root)
        addon_msg = ("PriestBridge installed. Type /reload in WoW."
                     if addon_done else "PriestBridge update pending: use Install / repair addon.")
        message = f"Updated to v{version}. {addon_msg}"
        write_status(root, True, message)
        log(root, message)
        restart_application(root)
        return 0
    except Exception as exc:
        message = "UPDATE FAILED: " + repr(exc)
        log(root, message)
        write_status(root, False, message)
        try:
            restart_application(root)
        except Exception as restart_exc:
            log(root, "Could not relaunch bot: " + repr(restart_exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
