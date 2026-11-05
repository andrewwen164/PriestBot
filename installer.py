"""First-time permanent Windows installation (stdlib-only bootstrap)."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys
from priestbot.install_core import (
    apply_release, create_desktop_shortcut, installed_dir,
    install_addon_for_user, load_settings, log, restart_application, save_settings,
)


def choose_old_config() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        answer = messagebox.askyesno(
            "PriestBot first install",
            "Have a config.json from v0.8 or an earlier bot?\n\n"
            "Choose Yes to import your spell keys and settings once.\n"
            "Choose No to use the defaults.", parent=root
        )
        path = filedialog.askopenfilename(
            title="Choose old PriestBot config.json",
            filetypes=[("JSON settings", "*.json")], parent=root
        ) if answer else ""
        root.destroy()
        return Path(path) if path else None
    except Exception as exc:
        print(f"Could not open configuration picker: {exc}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-config", type=Path, help="Import an existing config.json on first install")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    dest = installed_dir()
    print(f"Installing PriestBot permanently at:\n  {dest}")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        # This is a one-time migration; updates never touch config.json.
        existing = dest / "config.json"
        migrate = args.from_config
        if not existing.exists():
            if not migrate and (source / "config.json").is_file():
                migrate = source / "config.json"
            if not migrate:
                migrate = choose_old_config()
            if migrate:
                # Require actual JSON object; refuse accidental unrelated data.
                import json
                value = json.loads(migrate.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("The selected configuration is not a JSON object")
                shutil.copy2(migrate, existing)
                print("Imported your previous spell keys and settings.")
        version = apply_release(source, dest)
        # The settings file is intentionally NOT part of the release.
        settings = load_settings(dest)
        save_settings(dest, settings)
        try:
            create_desktop_shortcut(dest)
        except Exception as exc:
            log(dest, f"Shortcut creation failed: {exc}; you can rerun the installer later.")
        try:
            installed = install_addon_for_user(dest)
        except Exception as exc:
            installed = False
            log(dest, "AddOn installation failed: " + str(exc))
        if not installed:
            print("PriestBridge still needs installation; use 'Install / repair addon' inside the app.")
        print(f"PriestBot v{version} installed. Opening it now.")
        restart_application(dest)
        return 0
    except Exception as exc:
        log(dest, "INSTALL FAILED: " + repr(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
