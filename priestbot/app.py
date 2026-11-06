"""GUI + F7 calibration, F8 start/pause, F9 emergency stop.

Opt-in background PostMessage support for a visible WoW window. No client memory
or injected code. All modes default to dry-run on every launch.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from .config import Config, CONFIG_PATH
from .engine import PriestEngine
from .keybindings import ACTION_LABELS, validate_bindings


class App:
    def __init__(self, root):
        self.root = root
        root.title("PriestBot 0.25.3 - Attended Farmer")
        root.geometry("945x840")
        root.minsize(760, 700)
        if sys.platform == "win32":
            try:
                from .icon_asset import create_priest_icon
                root.iconbitmap(str(create_priest_icon(Path(__file__).resolve().parents[1])))
            except (AttributeError, OSError, ImportError):
                pass  # Cosmetic window icon must not prevent startup.
        self.cfg = Config.load()
        # Never inherit LIVE INPUT from an older copied config.json at startup.
        # The user must explicitly enable real keys in each app session.
        self.cfg.dry_run = True
        self.live = tk.BooleanVar(value=False)
        self.drink = tk.BooleanVar(value=self.cfg.enable_drink)
        self.damage_mode = tk.StringVar(value=self.cfg.main_damage)
        self.telemetry_source = tk.StringVar(value=self.cfg.telemetry_source)
        self.input_mode = tk.StringVar(value=self.cfg.input_mode)
        self.background_test_cancel = threading.Event()
        self.shield = tk.BooleanVar(value=self.cfg.use_shield)
        self.pain = tk.BooleanVar(value=self.cfg.use_pain)
        self.heal = tk.BooleanVar(value=self.cfg.use_heal)
        self.renew = tk.BooleanVar(value=self.cfg.use_renew)
        self.melee_oom = tk.BooleanVar(value=self.cfg.melee_when_oom)
        self.movement = tk.BooleanVar(value=self.cfg.enable_movement)
        self.stationary_tracking = tk.BooleanVar(value=self.cfg.enable_stationary_tracking)
        self.processes = tk.StringVar(value=", ".join(self.cfg.allowed_processes))
        self.learn_record = tk.BooleanVar(value=self.cfg.learning_record_gameplay)
        self.learn_corrections = tk.BooleanVar(value=self.cfg.learning_record_corrections)
        self.learn_mouse = tk.BooleanVar(value=self.cfg.learning_record_mouse)
        self.learn_all_keys = tk.BooleanVar(value=self.cfg.learning_record_all_keys)
        self.demo_capture_paused = tk.BooleanVar(value=False)
        self.demo_mouse_listener = None
        self.learn_auto = tk.BooleanVar(value=self.cfg.learning_auto_train)
        self.demo_recorder = None
        self.semantic_packet_count = 0
        self.bot_recorder = None
        self.demo_stop = threading.Event()
        self.demo_thread = None
        self.training_running = False
        self.vision_training_running = False
        self.state_text = tk.StringVar(value="Idle. Press F7 in WoW to capture calibration image.")
        self.values_text = tk.StringVar(value="HP --  |  Mana --  |  Target --")
        self.aura_text = tk.StringVar(value="Shield: --   |   Pain: --   |   Last confirmed cast: --")
        self.target_text = tk.StringVar(value="Target generation: --   |   Spell events: --")
        self.decision_text = tk.StringVar(value="Decision: idle")
        self.calibration_text = tk.StringVar(value="Bar calibration: " + self.calibration_summary())
        self.events = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()
        self.running = False
        self.log_area = None
        self.listener = None
        self.build()
        self.show_last_update_status()
        self.root.after(120, self.poll_events)
        if sys.platform == "win32":
            self.root.after(650, self._repair_shortcut_after_upgrade)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            from pynput import keyboard
            self.listener = keyboard.Listener(on_press=self.hotkey, on_release=self.key_released)
            self.listener.start()
        except Exception as exc:
            messagebox.showerror("Hotkeys unavailable", f"Install dependencies with setup_windows.bat.\n{exc}")

    def _repair_shortcut_after_upgrade(self):
        try:
            from .install_core import installed_dir, ensure_shortcut_icon_migrated
            current = Path(__file__).resolve().parents[1]
            if current.resolve() == installed_dir().resolve():
                if ensure_shortcut_icon_migrated(current):
                    self.log("Recreated desktop shortcut with the Classic Priest icon.")
        except Exception as exc:
            self.log("Shortcut icon refresh failed: " + str(exc))

    def build(self):
        frame=ttk.Frame(self.root, padding=12)
        frame.pack(fill="both",expand=True)
        ttk.Label(frame, text="PriestBot — Attended Farmer",font=("Segoe UI",17,"bold")).pack(anchor="w")
        ttk.Label(frame,text="F6 verify  ·  F7 calibrate  ·  F8 start/pause  ·  F9 emergency stop",
                  font=("Segoe UI",10)).pack(anchor="w",pady=(2,8))
        ttk.Label(frame,textvariable=self.state_text,wraplength=770,
                  font=("Segoe UI",10,"bold")).pack(anchor="w",pady=4)
        ttk.Label(frame,textvariable=self.values_text).pack(anchor="w",pady=3)
        dashboard=ttk.LabelFrame(frame,text="Live telemetry and decisions",padding=8)
        dashboard.pack(fill="x", pady=(5, 7))
        for variable in (self.aura_text,self.target_text,self.decision_text):
            ttk.Label(dashboard,textvariable=variable,wraplength=840).pack(anchor="w",pady=1)
        # Primary actions remain visible, including emergency stop, on every tab.
        row=ttk.Frame(frame);row.pack(fill="x",pady=(5,6))
        ttk.Button(row,text="Start / Pause (F8)",command=self.toggle).pack(side="left",padx=3)
        ttk.Button(row,text="PANIC STOP (F9)",command=self.panic).pack(side="left",padx=3)
        ttk.Button(row,text="Verify addon (F6)",command=self.verify_addon).pack(side="left",padx=3)
        ttk.Button(row,text="Export diagnostic ZIP",command=self.export_diagnostics).pack(side="left",padx=3)
        ttk.Checkbutton(frame,text="Enable REAL key presses (OFF every launch; verify dry-run first)",
                        variable=self.live,command=self.store_flags).pack(anchor="w",pady=(0,7))
        tabs=ttk.Notebook(frame)
        tabs.pack(fill="x",pady=(0,8))
        farm=ttk.Frame(tabs,padding=11)
        record=ttk.Frame(tabs,padding=11)
        setup=ttk.Frame(tabs,padding=11)
        tabs.add(farm,text="Farm")
        tabs.add(record,text="Record & Review")
        tabs.add(setup,text="Setup & Tools")
        updates = ttk.LabelFrame(setup, text="Installation & updates", padding=8)
        updates.pack(fill="x", pady=(4, 5))
        for label, callback in (
            ("Update from ZIP...", self.update_from_zip),
            ("Install / repair PriestBridge", self.reinstall_addon),
        ):
            ttk.Button(updates, text=label, command=callback).pack(side="left", padx=(0, 6))
        self._command_menu(updates,"More maintenance ▾",(
            ("Manual calibration (F7)",self.capture),
            ("Change WoW AddOns folder",self.change_addon_folder),
            ("Recreate desktop shortcut",self.recreate_shortcut),
            ("Show config.json",self.show_config),
        )).pack(side="left",padx=(0,6))
        learn_row = ttk.LabelFrame(record, text="Demonstration capture", padding=8)
        learn_row.pack(fill="x", pady=(5, 5))
        for i, (label, value) in enumerate((("Record game telemetry/screenshots", self.learn_record),
                                            ("Record manual movement corrections", self.learn_corrections),
                                            ("Record mouse clicks, drags and wheel", self.learn_mouse),
                                            ("Record all game-focused gameplay keys", self.learn_all_keys),
                                            ("Auto-train candidates after sessions", self.learn_auto))):
            ttk.Checkbutton(learn_row, text=label, variable=value, command=self.store_flags).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 12), pady=2)
        learn_buttons = ttk.Frame(record)
        learn_buttons.pack(fill="x", pady=(3, 8), before=learn_row)
        ttk.Button(learn_buttons,text="Start / Stop demonstration",
                   command=self.toggle_demonstration).pack(side="left",padx=(0,8))
        ttk.Button(learn_buttons,text="Pause / Resume input logging",
                   command=self.pause_demo_input).pack(side="left",padx=(0,8))
        self._command_menu(learn_buttons,"Review data ▾",(
            ("Farming: targets, spells and loot",self.view_farming),
            ("Action semantics / bindings",self.view_semantics),
            ("Evaluation dashboard",self.view_evaluation),
            ("Data coverage",self.view_coverage),
            ("Vision evaluation / coverage",self.view_vision),
            ("Open learning-data folder",self.open_learning_data),
        )).pack(side="left")
        vision_buttons=ttk.Frame(record); vision_buttons.pack(fill="x",pady=(0,4))
        self._command_menu(vision_buttons,"Training tools ▾",(
            ("Demonstration keys",self.configure_demo_keys),
            ("Train candidate now",self.train_now),
            ("Train temporal vision",self.train_temporal),
            ("Approve advisory (read-only)",self.approve_advisory),
        )).pack(side="left",padx=(0,8))
        ttk.Label(vision_buttons,text="Training models are advisory-only; GPU optional.").pack(side="left")
        options=ttk.Frame(farm); options.pack(fill="x",pady=(1,6))
        ttk.Label(options,text="Main damage spell:").pack(side="left",padx=(0,8))
        mode=ttk.Combobox(options,textvariable=self.damage_mode,values=["smite", "wand", "mind_blast_wand", "melee"],
                          state="readonly",width=19)
        mode.pack(side="left")
        mode.bind("<<ComboboxSelected>>",lambda _: self.store_flags())
        ttk.Button(options,text="Spell key bindings...",command=self.configure_keys).pack(side="left",padx=(14,0))
        flags=ttk.LabelFrame(farm,text="Rotation",padding=7); flags.pack(fill="x",pady=(0,6))
        for index,(label,var) in enumerate((("Shield",self.shield),("Shadow Word: Pain",self.pain),
                                            ("Heal / Lesser Heal (60% default)",self.heal),
                                            ("Renew between pulls (<80% default)",self.renew),
                                            ("Melee when OOM",self.melee_oom),
                                            ("Drink between pulls",self.drink))):
            ttk.Checkbutton(flags,text=label,variable=var,command=self.store_flags).grid(
                row=index//3, column=index%3, sticky="w", padx=(0,18), pady=2)
        ttk.Checkbutton(setup, text="Experimental walking/turning on range errors (not for stationary farming)",
                        variable=self.movement, command=self.store_flags).pack(anchor="w", pady=4)
        ttk.Checkbutton(farm, text="Track fleeing mobs: bounded turns and LoS waits (never chase)",
                        variable=self.stationary_tracking, command=self.store_flags).pack(anchor="w", pady=3)
        source_row = ttk.Frame(setup); source_row.pack(fill="x", pady=(8, 4))
        ttk.Label(source_row, text="Telemetry source:").pack(side="left", padx=(0, 8))
        source = ttk.Combobox(source_row, textvariable=self.telemetry_source,
                              values=["manual", "addon"], state="readonly", width=12)
        source.pack(side="left")
        source.bind("<<ComboboxSelected>>", lambda _: self.store_flags())
        ttk.Label(source_row, text="addon = fixed screen telemetry; keep game visible").pack(side="left", padx=(10, 0))
        input_row=ttk.Frame(farm); input_row.pack(fill="x", pady=(4, 6))
        ttk.Label(input_row, text="Input method:").pack(side="left",padx=(0,8))
        input_combo = ttk.Combobox(input_row,textvariable=self.input_mode,
                                   values=["foreground", "background"],state="readonly",width=16)
        input_combo.pack(side="left")
        input_combo.bind("<<ComboboxSelected>>",lambda _:self.store_flags())
        ttk.Label(input_row,text="background = experimental; WoW must stay visible").pack(side="left",padx=10)
        ttk.Button(setup,text="Test background Tab (5s)",command=self.test_background_tab).pack(anchor="w",pady=(3,7))
        row2=ttk.Frame(setup);row2.pack(fill="x",pady=8)
        ttk.Label(row2,text="Allowed game .exe names:").pack(side="left")
        ttk.Entry(row2,textvariable=self.processes,width=65).pack(side="left",padx=7,fill="x",expand=True)
        ttk.Button(row2,text="Save",command=self.store_flags).pack(side="left")
        ttk.Label(setup,textvariable=self.calibration_text,wraplength=850).pack(anchor="w",pady=5)
        ttk.Separator(frame).pack(fill="x",pady=8)
        ttk.Label(frame,text="Activity log",font=("Segoe UI",10,"bold")).pack(anchor="w")
        self.log_area=tk.Text(frame,height=10,width=100,state="disabled",font=("Consolas",9))
        self.log_area.pack(fill="both",expand=True)
        self.log("DRY RUN starts ON; no keys are sent until you explicitly enable real input.")
        self.log("Farm: rotation, spell keys, stationary tracking. Record & Review: demonstrations and learning.")
        self.log("Setup & Tools: addon installation, calibration, maintenance, advanced movement.")
        self.log("F6 verifies PriestBridge. Export diagnostic ZIP to share test results in PriestBot Chat 2.")
        self.log("Healing: casted Heal ≤60%; optional Renew <80% between pulls; pre-pull Shield when enabled.")
        self.log("Stationary target tracking is opt-in. No blind pursuit of fleeing mobs.")
        self.log("Learning models remain advisory-only; no model controls game inputs.")

    @staticmethod
    def _command_menu(parent, label, actions):
        """Keep infrequent tools accessible without cluttering the main view."""
        button = ttk.Menubutton(parent, text=label)
        menu = tk.Menu(button, tearoff=False)
        for title, callback in actions:
            menu.add_command(label=title, command=callback)
        button.configure(menu=menu)
        return button

    def _is_permanent_install(self):
        from .install_core import installed_dir, SETTINGS_FILENAME
        root_dir = Path(__file__).resolve().parents[1]
        return root_dir.resolve() == installed_dir().resolve() and (root_dir / SETTINGS_FILENAME).is_file()

    def show_last_update_status(self):
        from .install_core import STATUS_FILENAME
        path = Path(__file__).resolve().parents[1] / STATUS_FILENAME
        if path.is_file():
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                self.log(report.get("message", "Update finished"))
                self.state_text.set(report.get("message", "Update finished"))
                path.unlink(missing_ok=True)
            except Exception as exc:
                self.log("Update status could not be read: " + str(exc))

    def update_from_zip(self):
        if self.running:
            messagebox.showwarning("Pause first", "Pause and let the worker stop before updating.", parent=self.root)
            return
        if not self._is_permanent_install():
            messagebox.showinfo("First install required",
                "Install PriestBot with install_windows.bat once, then use ZIP updates. "
                "Later updates will work from this button.", parent=self.root)
            return
        path = filedialog.askopenfilename(title="Choose a PriestBot update ZIP",
                        filetypes=[("PriestBot ZIP releases", "*.zip")], parent=self.root)
        if not path:
            return
        from .install_core import inspect_zip
        try:
            version, _ = inspect_zip(Path(path))
        except Exception as exc:
            messagebox.showerror("Invalid release", f"The selected ZIP cannot be installed:\n{exc}", parent=self.root)
            return
        if not messagebox.askyesno("Update PriestBot",
            f"Install PriestBot v{version} from this local ZIP?\n\n"
            "Your config.json, spell keys, virtual environment and desktop shortcut will be retained. "
            "The game addon will also be updated (Windows may request administrator approval).\n\n"
            "The bot will close and reopen after the update.", parent=self.root):
            return
        self.cfg.save()
        from .install_core import installed_dir
        import subprocess
        args = [sys.executable, str(installed_dir() / "updater_runner.py"),
                "--zip", path, "--install-dir", str(installed_dir()),
                "--parent-pid", str(os.getpid())]
        try:
            subprocess.Popen(args, cwd=str(installed_dir()),
                  creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as exc:
            messagebox.showerror("Cannot start update", str(exc), parent=self.root)
            return
        self.log(f"Starting upgrade to v{version}; closing bot...")
        self.close()

    def reinstall_addon(self):
        if self.running:
            messagebox.showwarning("Pause first", "Pause the bot before replacing its WoW addon.", parent=self.root)
            return
        if not self._is_permanent_install():
            messagebox.showinfo("Install PriestBot", "Run install_windows.bat first.", parent=self.root)
            return
        from .install_core import installed_dir, load_settings
        root_dir = installed_dir()
        addons_dir = load_settings(root_dir)["addons_dir"]
        if not messagebox.askyesno("Install PriestBridge",
            f"Install/repair PriestBridge in:\n{addons_dir}\n\n"
            "Windows may request administrator approval. Afterwards, type /reload in WoW.", parent=self.root):
            return
        self.state_text.set("Installing PriestBridge (approve UAC if Windows asks)...")
        def worker():
            from .install_core import install_addon_for_user
            try:
                success = install_addon_for_user(root_dir)
                self.events.put(("addon_done", (success, None)))
            except Exception as exc:
                self.events.put(("addon_done", (False, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def change_addon_folder(self):
        if self.running:
            messagebox.showwarning("Pause first", "Pause before changing installation settings.", parent=self.root)
            return
        if not self._is_permanent_install():
            messagebox.showinfo("Install PriestBot", "Run install_windows.bat first.", parent=self.root)
            return
        from .install_core import installed_dir, load_settings, save_settings
        root_dir = installed_dir()
        settings = load_settings(root_dir)
        chosen = filedialog.askdirectory(title="Choose WoW Interface/AddOns folder",
                   initialdir=settings["addons_dir"] if Path(settings["addons_dir"]).is_dir() else None,
                   parent=self.root)
        if not chosen:
            return
        if Path(chosen).name.lower() != "addons":
            if not messagebox.askyesno("Unexpected folder",
                    f"The selected folder isn't named AddOns:\n{chosen}\nUse it anyway?", parent=self.root):
                return
        settings["addons_dir"] = chosen
        settings["addon_pending"] = True
        save_settings(root_dir, settings)
        self.log("WoW addon folder saved: " + chosen)
        self.log("Click Install / repair PriestBridge to copy into the new folder.")

    def recreate_shortcut(self):
        if not self._is_permanent_install():
            messagebox.showinfo("Install PriestBot", "Run install_windows.bat first.", parent=self.root)
            return
        from .install_core import create_desktop_shortcut, installed_dir
        try:
            create_desktop_shortcut(installed_dir())
            self.log("Desktop shortcut created/repaired.")
        except Exception as exc:
            messagebox.showerror("Shortcut failed", str(exc), parent=self.root)

    def calibration_summary(self):
        return "ready" if all([self.cfg.player_health,self.cfg.player_mana,self.cfg.target_health]) else "not yet set"

    def configure_keys(self):
        if self.running:
            messagebox.showwarning("Pause first", "Pause the bot before changing spell keys.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title("Spell and action key bindings")
        window.geometry("530x620")
        window.transient(self.root)
        window.grab_set()
        outer = ttk.Frame(window, padding=15)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Match these keys to your WoW action bar", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Enter a key such as 3, e, or shift+e (also ctrl+1, alt+q, ctrl+shift+r). F6/F7/F8/F9 are reserved.",
                  wraplength=490).pack(anchor="w", pady=(3, 12))
        vars = {}
        grid = ttk.Frame(outer)
        grid.pack(fill="x")
        for idx, (action, label) in enumerate(ACTION_LABELS.items()):
            ttk.Label(grid, text=label, width=25).grid(row=idx, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.cfg.keys.get(action, ""))
            vars[action] = var
            ttk.Entry(grid, textvariable=var, width=14).grid(row=idx, column=1, sticky="w", padx=(10, 0), pady=4)
        ttk.Label(outer, text="Tip: bind Heal, Renew and Shield to self-cast macros so defensive spells never target enemies.",
                  wraplength=490).pack(anchor="w", pady=(14, 5))
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", side="bottom", pady=(10, 0))

        def save_bindings():
            try:
                normalized = validate_bindings({action: var.get() for action, var in vars.items()})
            except ValueError as exc:
                messagebox.showerror("Fix key bindings", str(exc), parent=window)
                return
            self.cfg.keys = normalized
            self.cfg.save()
            self.log("Spell/action bindings saved: " + ", ".join(f"{k}={v}" for k, v in normalized.items()))
            window.grab_release()
            window.destroy()

        def reset():
            defaults = Config().keys
            for action, var in vars.items():
                var.set(defaults[action])

        ttk.Button(bottom, text="Cancel", command=window.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(bottom, text="Save key bindings", command=save_bindings).pack(side="right")
        ttk.Button(bottom, text="Reset defaults", command=reset).pack(side="left")
        window.bind("<Return>", lambda _: save_bindings())

    def store_flags(self):
        self.cfg.dry_run = not self.live.get()
        self.cfg.enable_drink = self.drink.get()
        self.cfg.main_damage = self.damage_mode.get()
        self.cfg.telemetry_source = self.telemetry_source.get()
        self.cfg.input_mode = self.input_mode.get()
        self.cfg.use_shield = self.shield.get()
        self.cfg.use_pain = self.pain.get()
        self.cfg.use_heal = self.heal.get()
        self.cfg.use_renew = self.renew.get()
        self.cfg.melee_when_oom = self.melee_oom.get()
        self.cfg.enable_movement = self.movement.get()
        self.cfg.enable_stationary_tracking = self.stationary_tracking.get()
        self.cfg.learning_record_gameplay = self.learn_record.get()
        self.cfg.learning_record_corrections = self.learn_corrections.get()
        self.cfg.learning_record_mouse = self.learn_mouse.get()
        self.cfg.learning_record_all_keys = self.learn_all_keys.get()
        self.cfg.learning_auto_train = self.learn_auto.get()
        self.cfg.allowed_processes = [x.strip().lower() for x in self.processes.get().split(",") if x.strip()]
        self.cfg.save()
        self.log("Settings saved; DRY RUN="+str(self.cfg.dry_run))

    def test_background_tab(self):
        """Armed one-shot, never a farming run. Gives time to focus a browser."""
        if self.running:
            self.log("Pause farming before testing background input.")
            return
        if self.input_mode.get() != "background":
            self.log("Select background input mode before testing.")
            return
        try:
            from .background_input import choose_game_window, WindowsMessages
            api = WindowsMessages()
            target = choose_game_window(self.cfg.allowed_processes, api)
        except Exception as exc:
            self.log("Background test could not find WoW: " + str(exc))
            return
        self.background_test_cancel.set()  # cancel any previous test
        self.background_test_cancel = threading.Event()
        cancel = self.background_test_cancel
        self.log(f"BACKGROUND TEST ARMED: 5s to click your browser. Will post ONE Tab to WoW pid {target.pid}.")
        def delayed_test():
            if cancel.wait(5.0):
                return
            try:
                from .background_input import post_game_key, WindowsMessages
                from .input_control import game_has_focus
                if game_has_focus(self.cfg.allowed_processes):
                    self.events.put(("log", "Test cancelled: WoW still has focus. Click your browser during countdown."))
                    return
                post_game_key(self.cfg.keys["next_target"], target,
                              self.cfg.allowed_processes, api=WindowsMessages(),
                              cancelled=cancel.is_set)
                self.events.put(("log", "Background Tab queued to WoW (NOT confirmed processed). Check if target changed."))
            except Exception as exc:
                self.events.put(("log", "Background Tab test failed: " + str(exc)))
        threading.Thread(target=delayed_test,daemon=True).start()

    def show_config(self):
        import subprocess
        self.cfg.save()
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe",str(CONFIG_PATH)])
        else:
            self.log(str(CONFIG_PATH))
        self.log("After editing config.json, restart the app to apply changes.")

    def export_diagnostics(self):
        """Build report in background; read-only telemetry snapshot if available."""
        self.log('Generating offline telemetry/decision scenarios and uploadable ZIP...')
        def worker():
            try:
                from .diagnostics import generate_report
                from zipfile import ZipFile
                report_path = generate_report(include_live=True, current_config=self.cfg)
                with ZipFile(report_path) as z:
                    summary = json.loads(z.read('report.json'))['summary']
                self.events.put(('diagnostic_done', (str(report_path), summary, None)))
            except Exception as exc:
                self.events.put(('diagnostic_done', (None, None, str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def log(self, text):
        self.log_area.configure(state="normal")
        self.log_area.insert("end",time.strftime("%H:%M:%S ")+str(text)+"\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def hotkey(self, key):
        # Manually recorded actions are whitelisted movement keys and only when
        # WoW has keyboard focus. The global listener never logs arbitrary keys.
        self._demo_key_event(key, pressed=True)
        try:
            from pynput.keyboard import Key
            if key == Key.f6:
                self.events.put(("verify_addon",None))
            elif key == Key.f7:
                self.events.put(("calibrate",None))
            elif key == Key.f8:
                self.events.put(("toggle",None))
            elif key == Key.f9:
                # Shutdown set immediately on listener thread; not GUI polling.
                self.stop_flag.set()
                self.events.put(("panic",None))
        except Exception as exc:
            self.events.put(("log","Hotkey error: "+str(exc)))

    @staticmethod
    def _key_name(key):
        name = getattr(key, "char", None)
        # pynput can return a control character for Ctrl+letter; preserve key identity.
        if name is not None and (len(str(name)) != 1 or ord(str(name)) < 32):
            name = None
        if name is None:
            name = getattr(key, "name", None)
        if name is None:
            vk = getattr(key, "vk", None)
            if isinstance(vk, int) and (65 <= vk <= 90 or 48 <= vk <= 57):
                name = chr(vk).lower()
        return str(name).lower() if name else None

    def _demo_key_event(self, key, *, pressed):
        rec = self.demo_recorder
        if rec is None or not self.cfg.learning_record_corrections:
            return
        name = App._key_name(key)
        if not name:
            return
        try:
            from .input_control import game_has_focus
            from .keybindings import normalize_binding
            if not game_has_focus(self.cfg.allowed_processes):
                rec.focus_lost()
                return
            now = time.monotonic()
            # Composite bindings include held Shift/Ctrl/Alt. Raw key capture and
            # canonical movement labels are separate: spell/chat keys don't
            # become misleading movement training labels.
            modifiers = rec._mods(rec.held_raw_keys)
            if pressed and name in ("shift", "ctrl", "alt", "shift_l", "shift_r", "ctrl_l", "ctrl_r", "alt_l", "alt_r"):
                modifiers = rec._mods(set(rec.held_raw_keys) | {name})
            chord = "+".join(modifiers + [name]) if name not in ("shift", "ctrl", "alt") else name
            bound_actions = []
            for action, bound in self.cfg.learning_demo_keys.items():
                try:
                    if normalize_binding(bound) in (name, chord) and ("+" not in normalize_binding(bound) or chord == normalize_binding(bound)):
                        bound_actions.append(action)
                except (ValueError, TypeError):
                    continue
            rec.raw_key(name, pressed, now, action=bound_actions[0] if bound_actions else None,
                        record=self.cfg.learning_record_all_keys)
            if rec.privacy_paused or rec.capture_paused:
                return
            for action in bound_actions:
                if pressed:
                    rec.key_down(action, now)
                else:
                    rec.key_up(action, now)
        except Exception:
            pass

    def _demo_mouse_click(self, x, y, button, pressed):
        rec = self.demo_recorder
        if rec is None or not self.cfg.learning_record_corrections or not self.cfg.learning_record_mouse:
            return
        try:
            from .input_control import game_has_focus
            from .learning import game_client_point
            if not game_has_focus(self.cfg.allowed_processes):
                rec.focus_lost()
                return
            point = game_client_point(x, y, self.cfg.allowed_processes)
            if point is None:
                rec.cancel_mouse()
                return
            rec.mouse_button(getattr(button, "name", "unknown"), pressed, *point, time.monotonic())
        except Exception:
            rec.cancel_mouse()

    def _demo_mouse_moved(self, x, y):
        rec = self.demo_recorder
        if rec is None or not self.cfg.learning_record_mouse:
            return
        try:
            from .input_control import game_has_focus
            from .learning import game_client_point
            if game_has_focus(self.cfg.allowed_processes):
                point = game_client_point(x, y, self.cfg.allowed_processes)
                if point is None:
                    rec.cancel_mouse()
                    return
                rec.all_mouse_move(*point, time.monotonic())
            else:
                rec.focus_lost()
        except Exception:
            rec.cancel_mouse()

    def _demo_mouse_scroll(self, x, y, dx, dy):
        rec = self.demo_recorder
        if rec is None or not self.cfg.learning_record_mouse:
            return
        try:
            from .input_control import game_has_focus
            from .learning import game_client_point
            if not game_has_focus(self.cfg.allowed_processes):
                rec.focus_lost()
                return
            point = game_client_point(x, y, self.cfg.allowed_processes)
            if point is not None:
                rec.scroll(*point, dx, dy, time.monotonic())
        except Exception:
            rec.cancel_mouse()

    def key_released(self, key):
        self._demo_key_event(key, pressed=False)

    def pause_demo_input(self):
        rec = self.demo_recorder
        if rec is None:
            self.log("Start a demonstration before pausing input recording.")
            return
        paused = not rec.capture_paused
        rec.set_capture_paused(paused)
        self.demo_capture_paused.set(paused)
        self.log("Demonstration input logging " + ("PAUSED" if paused else "RESUMED"))

    def configure_demo_keys(self):
        if self.demo_recorder is not None or self.running:
            self.log("Stop gameplay/demonstration before editing movement-demo keys.")
            return
        window = tk.Toplevel(self.root)
        window.title("Manual demonstration key bindings")
        window.transient(self.root)
        window.grab_set()
        ttk.Label(window, text="Movement keys become supervised labels. All other game-focused key presses are recorded in the raw timeline (not trained).\nChat text is suppressed after Enter or /; manually pause recording for other text boxes.",
                  padding=12).pack(anchor="w")
        vars = {}
        for label, action in (("Move forward", "move_forward"), ("Turn left", "turn_left"),
                              ("Turn right", "turn_right"), ("Move backward", "move_backward"),
                              ("Strafe left", "strafe_left"), ("Strafe right", "strafe_right"),
                              ("Jump", "jump"), ("Auto-run", "auto_run")):
            row = ttk.Frame(window, padding=5); row.pack(fill="x")
            ttk.Label(row, text=label, width=17).pack(side="left")
            vars[action] = tk.StringVar(value=self.cfg.learning_demo_keys.get(action, ""))
            ttk.Entry(row, textvariable=vars[action], width=14).pack(side="left")
        def save():
            from .keybindings import normalize_binding
            try:
                keys = {k: normalize_binding(v.get()) for k,v in vars.items()}
                if len(set(keys.values())) != len(keys):
                    raise ValueError("Demo keys must be distinct; use modifiers as needed")
            except ValueError as exc:
                messagebox.showerror("Invalid keys", str(exc), parent=window)
                return
            self.cfg.learning_demo_keys = keys
            self.cfg.save()
            window.destroy()
            self.log("Demonstration movement keys saved")
        ttk.Button(window, text="Save demonstration keys", command=save).pack(pady=12)

    def toggle_demonstration(self):
        if self.demo_recorder is not None:
            self.demo_stop.set()
            self.log("Stopping manual demonstration session...")
            return
        if self.running:
            self.log("Pause the combat bot before recording manual corrections.")
            return
        if not self.learn_corrections.get():
            self.log("Enable 'Record manual movement corrections' first.")
            return
        from .learning import SessionRecorder, learning_root
        try:
            rec = SessionRecorder(learning_root(), "demonstration", screenshot_period_s=.30)
        except OSError as exc:
            self.log("Cannot start demonstration: " + str(exc))
            return
        self.demo_recorder = rec
        self.demo_capture_paused.set(False)
        self.demo_stop.clear()
        if self.cfg.learning_record_mouse:
            try:
                from pynput import mouse
                self.demo_mouse_listener = mouse.Listener(on_move=self._demo_mouse_moved,
                                                          on_click=self._demo_mouse_click,
                                                          on_scroll=self._demo_mouse_scroll)
                self.demo_mouse_listener.start()
            except Exception as exc:
                self.demo_recorder = None
                rec.close()
                self.log("Mouse listener could not start; demonstration cancelled: " + str(exc))
                return
        self.demo_thread = threading.Thread(target=self._demo_loop, args=(rec,), daemon=True)
        self.demo_thread.start()
        self.log("Demonstration ON: WoW-only inputs + visual intervals + farming labels for target selection, spell casts, loot windows and cleared slots. Requires PriestBridge v0.23 for native loot evidence; chat guarded.")

    def _demo_loop(self, rec):
        try:
            from mss import mss
            from .learning import game_frame
            from .input_control import game_has_focus
            from .bridge import monitor_bridge, BridgeNotFound
            from .semantic_bridge import monitor_semantics
            with mss() as sct:
                while not self.demo_stop.is_set():
                    if game_has_focus(self.cfg.allowed_processes):
                        image = game_frame(sct, self.cfg.allowed_processes)
                        if image is not None:
                            try:
                                rd = monitor_bridge(sct)
                                obs = rd.observation
                                rec.observe(obs, image=image, dry_run=True)
                                packet = monitor_semantics(sct, rd)
                                if packet is not None:
                                    rec.ingest_semantic(packet)
                                    self.semantic_packet_count = rec.semantic.packets
                            except BridgeNotFound:
                                pass
                    else:
                        rec.focus_lost()  # never turn another app's input into training data
                    self.demo_stop.wait(.24)
        except Exception as exc:
            self.events.put(("log", "Demonstration recorder error: " + str(exc)))
        finally:
            if self.demo_mouse_listener is not None:
                self.demo_mouse_listener.stop()
                self.demo_mouse_listener = None
            rec.close()
            self.demo_recorder = None
            self.events.put(("log", "Demonstration saved to learning_data/sessions/" + rec.session_id +
                             f" ({rec.stats['manual_corrections']} movement labels, {rec.stats['input_events']} raw game inputs; "
                             f"{rec.farming.events_written} farming examples)"))
            self.events.put(("auto_train", None))
            self.events.put(("auto_train_vision", None))

    def train_now(self):
        self._queue_training(force=True)

    def _queue_training(self, force=False):
        if not force and not self.cfg.learning_auto_train:
            return
        if self.training_running:
            if force:
                self.log("Training already running.")
            return
        self.training_running = True
        self.log("Training candidate offline from recorded HUMAN corrections (no model deployment)...")
        def work():
            from .learning import learning_root, train_candidate
            try:
                result = train_candidate(learning_root())
                if result["status"] == "candidate_created":
                    e = result["evaluation"]
                    msg = (f"Candidate {result['candidate_id']} trained: holdout evaluated={e['evaluated']}, "
                           f"eligible={e['promotion_eligible']}. Click Evaluation dashboard.")
                else:
                    msg = "Training skipped: " + result["message"]
                self.events.put(("log", msg))
            except Exception as exc:
                self.events.put(("log", "Training failed: " + str(exc)))
            finally:
                self.events.put(("training_done", None))
        threading.Thread(target=work, daemon=True).start()

    def train_temporal(self):
        self._queue_vision_training(force=True)

    def _queue_vision_training(self, force=False):
        if not force and not self.cfg.learning_auto_train:
            return
        if self.vision_training_running:
            if force:
                self.log("Temporal vision training is already running")
            return
        self.vision_training_running = True
        self.log("Training temporal vision candidate OFFLINE (no WoW input authority)...")
        def work():
            from .learning import learning_root
            from .temporal_vision import train_temporal_candidate
            try:
                result = train_temporal_candidate(learning_root())
                if result.get('status') == 'candidate_created':
                    ev=result['evaluation']
                    msg=(f"Temporal vision candidate {result['candidate_id']}: "
                         f"holdout={ev.get('evaluated',False)}, "
                         f"macro F1={ev.get('macro_f1','not evaluated')}, "
                         "deployment=DISABLED. Open Vision evaluation / coverage.")
                else:
                    msg="Temporal vision training skipped: "+result.get('message',result.get('status','unknown'))
                self.events.put(('log',msg))
            except Exception as exc:
                self.events.put(('log','Temporal vision training failed: '+str(exc)))
            finally:
                self.events.put(('vision_training_done',None))
        threading.Thread(target=work,daemon=True).start()

    def view_vision(self):
        from .learning import learning_root
        from .temporal_vision import temporal_coverage, latest_vision_report
        from .vision_dashboard import VisionDashboard
        base=learning_root()
        coverage=temporal_coverage(base)
        coverage['_base']=base
        VisionDashboard(self.root, coverage, latest_vision_report(base))

    def view_farming(self):
        """Read-only demonstration coverage: attempts != observed outcomes."""
        from .learning import learning_root
        rec = self.demo_recorder or self.bot_recorder
        if rec is not None:
            report = rec.farming_report()
        else:
            import json
            sessions = sorted((learning_root() / 'sessions').glob('*/farming_report.json'),
                              key=lambda p: p.parent.name, reverse=True)
            if not sessions:
                self.log('No farming demonstration report yet. Record a new session with PriestBridge v0.23.')
                return
            try:
                report = json.loads(sessions[0].read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                self.log('Cannot open farming report: ' + str(exc))
                return
        win = tk.Toplevel(self.root)
        win.title('PriestBot — Farming demonstration coverage')
        win.geometry('980x660')
        from tkinter import ttk
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=12, pady=12)
        summary = ttk.Frame(notebook, padding=12)
        notebook.add(summary, text='Coverage')
        ttk.Label(summary, text='Farming demonstration: attempts vs game evidence',
                  font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 12))
        counts = report.get('counts') or {}
        labels = [
            ('Target-search attempts', 'target_search_attempt'),
            ('Selected target events', 'target_selected'),
            ('Spell inputs', 'rotation_input'),
            ('Confirmed spell successes', 'spell_success'),
            ('Spell failures', 'spell_failure'),
            ('Loot opened', 'loot_opened'),
            ('Loot slots cleared', 'loot_slot_cleared'),
            ('Loot closed', 'loot_closed'),
            ('Mouse click candidates', 'mouse_click_candidate'),
        ]
        for title, field in labels:
            ttk.Label(summary, text=f'{title}: {counts.get(field, 0)}').pack(anchor='w', pady=2)
        ttk.Label(summary, text=f"Saved input/event examples: {report.get('examples_saved', 0)}").pack(anchor='w', pady=7)
        for guidance in report.get('recommendations') or []:
            ttk.Label(summary, text='• ' + guidance, wraplength=890).pack(anchor='w', pady=3)
        ttk.Label(summary, text=report.get('limitations',''), wraplength=900,
                  foreground='#7b4a16').pack(anchor='w', pady=(15, 0))
        events_tab = ttk.Frame(notebook, padding=8)
        notebook.add(events_tab, text='Recent evidence')
        cols = ('category','evidence','phase','details')
        tree = ttk.Treeview(events_tab, columns=cols, show='headings')
        for c, width in zip(cols, (185,225,105,430)):
            tree.heading(c, text=c.title())
            tree.column(c, width=width, stretch=True)
        tree.pack(fill='both', expand=True)
        for row in reversed(report.get('recent') or []):
            details = ', '.join(f'{k}={str(v)[:42]}' for k,v in row.items()
                                if k not in ('category','evidence','phase','observed_at_mono','before_frame'))
            tree.insert('', 'end', values=(row.get('category',''),row.get('evidence',''),
                                            row.get('phase',''),details[:240]))

    def view_semantics(self):
        """Read-only in-game binding and observed outcome report."""
        from .learning import learning_root
        import json
        report = None
        rec = self.demo_recorder or self.bot_recorder
        if rec is not None and not rec.closed:
            report = rec.semantics_report()
        else:
            sessions = sorted((learning_root() / 'sessions').glob('*/action_semantics.json'),
                              key=lambda path: path.stat().st_mtime, reverse=True)
            if sessions:
                try:
                    report = json.loads(sessions[0].read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    report = None
        win = tk.Toplevel(self.root)
        win.title('Action Semantics — bindings & outcomes')
        win.geometry('940x620')
        if not report:
            ttk.Label(win, text='No semantic report yet. Start a demonstration with v0.21 PriestBridge loaded.',
                      wraplength=800).pack(padx=16, pady=20)
            return
        summary = ttk.Label(win, text=(
            f"Received {report.get('packets',0)} optical packets. "
            f"Resolved {len(report.get('bindings',[]))} bindings. "
            f"Outcomes: {report.get('counts',{})}"), wraplength=900)
        summary.pack(anchor='w', padx=10, pady=9)
        if not report.get('bindings'):
            kinds=report.get('packet_types') or {}
            expected=report.get('declared_bindings')
            if not kinds:
                diagnostic=('Binding packet diagnostics were not saved in this older recording. '
                            'Install the updated PriestBridge, run /pb bindings outside combat, '
                            'and record a new 1-minute demonstration.')
            elif expected==0:
                diagnostic=('PriestBridge reported zero enumerated bindings. '
                            'Run /pb bindings outside combat and inspect GetNumBindings().')
            elif kinds.get('B',0)==0:
                diagnostic=(f"No binding (B) packets received. Addon declared {expected if expected is not None else 'unknown'} bindings. "
                            'The upgraded addon interleaves binding packets with gameplay events; '
                            'run /pb bindings and verify the new addon is installed.')
            else:
                diagnostic=(f"Received {kinds.get('B',0)} binding packets but none mapped. "
                            'Inspect generation, packet decoding and key notation.')
            ttk.Label(win, text=diagnostic, foreground='#ac4b18',
                      wraplength=890).pack(anchor='w',padx=10,pady=(0,8))
        kinds=report.get('packet_types') or {}
        if kinds:
            ttk.Label(win, text=(f"Packet types: {dict(sorted(kinds.items()))} · "
                f"Declared bindings: {report.get('declared_bindings')} · "
                f"Binding records: {report.get('binding_records_seen',0)}"),
                wraplength=890).pack(anchor='w',padx=10,pady=(0,7))
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True, padx=10, pady=8)
        for name, cols, rows in (
            ('Bindings', ('key','action_type','action_id','action_name','command'), report.get('bindings',[])),
            ('Recent evidence', ('event','input','action','status','game_event','evidence'), report.get('recent',[]))):
            page=ttk.Frame(notebook)
            notebook.add(page,text=name)
            tree=ttk.Treeview(page,columns=cols,show='headings')
            for col in cols:
                tree.heading(col,text=col.replace('_',' ').title())
                tree.column(col,width=130 if col != 'action_name' else 240,anchor='w')
            for row in rows[-100:]:
                tree.insert('','end',values=[str(row.get(k,'')) for k in cols])
            vscroll=ttk.Scrollbar(page,orient='vertical',command=tree.yview)
            tree.configure(yscrollcommand=vscroll.set)
            vscroll.pack(side='right', fill='y')
            tree.pack(fill='both',expand=True)
        ttk.Label(win,text='Attempt is not success. Macro conditions and unreadable consumable auras remain unknown.',
                  wraplength=900).pack(anchor='w',padx=10,pady=8)

    def view_evaluation(self):
        from .learning import latest_report, learning_root, training_coverage
        from .learning_dashboard import LearningDashboard
        base = learning_root()
        report = latest_report(base)
        LearningDashboard(self.root, report, training_coverage(base), base=base,
                          starting_tab="evaluation")

    def view_coverage(self):
        from .learning import latest_report, learning_root, training_coverage
        from .learning_dashboard import LearningDashboard
        base = learning_root()
        LearningDashboard(self.root, latest_report(base), training_coverage(base),
                          base=base, starting_tab="coverage")

    def open_learning_data(self):
        from .learning import learning_root
        folder = learning_root()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            self.log("Learning data: " + str(folder))

    def approve_advisory(self):
        from .learning import latest_report, learning_root, promote_advisory
        report = latest_report(learning_root())
        if not report:
            self.log("No candidate to approve.")
            return
        ev = report["evaluation"]
        if not (ev["evaluated"] and ev["promotion_eligible"]):
            self.log("Candidate BLOCKED: evaluation gate not passed. See Evaluation dashboard.")
            return
        if not messagebox.askyesno("Approve advisory ONLY",
            "Enable this evaluated model for read-only movement suggestions?\n"
            "It will NOT send any game inputs or change combat decisions.", parent=self.root):
            return
        try:
            promote_advisory(learning_root(), report["candidate_id"])
            self.log("Evaluated movement model activated in ADVISORY ONLY mode. Restart bot to show suggestions.")
        except ValueError as exc:
            self.log("Candidate not approved: " + str(exc))

    def verify_addon(self):
        if self.running:
            self.log("Pause the bot before verifying addon telemetry.")
            return
        try:
            from mss import mss
            from .bridge import monitor_bridge
            with mss() as sct:
                rd = monitor_bridge(sct)
            obs = rd.observation
            extra = (f", casting={obs.casting}, spell_error={obs.error or 'none'}, "
                     f"event_seq={obs.error_seq}" if obs.error_seq is not None
                     else ", legacy v0.6 addon (no spell signals)")
            if obs.success_seq is not None:
                extra += (f", Shield={obs.shield_aura}, Pain={obs.pain_aura}, "
                          f"last_success={obs.success_spell or 'none'}, success_seq={obs.success_seq}, "
                          f"target_seq={obs.target_seq}")
            else:
                extra += ", no v0.8 aura/success telemetry"
            result = (f"PriestBridge at ({rd.marker_x}, {rd.marker_y}), "
                      f"scale {rd.scale:.2f}; HP={obs.hp:.0%}, "
                      f"Mana={obs.mana:.0%}, Target={obs.target_hp:.0%}" + extra)
            self.log(result)
            self.state_text.set("Addon detected. Inspect percentages before live input.")
            self.values_text.set(f"HP {obs.hp:.0%}  | Mana {obs.mana:.0%}  | Target {obs.target_hp:.0%}")
            self.aura_text.set(f"Shield: {obs.shield_aura or 'legacy/unknown'}  |  "
                               f"Pain: {obs.pain_aura or 'legacy/unknown'}  |  "
                               f"Last cast: {obs.success_spell or 'none'}")
            self.target_text.set(f"Target generation: {obs.target_seq if obs.target_seq is not None else '--'}  |  "
                                 f"Success sequence: {obs.success_seq if obs.success_seq is not None else '--'}")
        except Exception as exc:
            self.log("Addon telemetry unavailable: " + str(exc))
            self.state_text.set("Addon detection failed. Verify /pb show and client compatibility.")

    def capture(self):
        if self.running:
            self.log("Pause the bot before calibrating.")
            return
        try:
            from mss import mss
            from .vision import full_screenshot
            from .calibrator import BarCalibrator
            with mss() as sct:
                image, x, y = full_screenshot(sct)
            existing = {name: getattr(self.cfg, name) for name in
                        ("player_health", "player_mana", "target_health")}
            BarCalibrator(self.root,image,x,y,self.calibrated,existing=existing)
        except Exception as exc:
            self.log("Calibration failed: "+str(exc))

    def calibrated(self, rects):
        for name, rect in rects.items():
            setattr(self.cfg,name,rect)
        self.cfg.save()
        self.calibration_text.set("Bar calibration: " + self.calibration_summary())
        self.state_text.set("Calibrated. Begin with DRY RUN to verify sensor percentages.")
        self.log("Calibration saved. HP: {} Mana: {} Target: {}".format(
            self.cfg.player_health, self.cfg.player_mana, self.cfg.target_health))

    def toggle(self):
        if self.running:
            self.stop_flag.set()
            self.log("Pause requested")
            return
        if self.demo_recorder is not None:
            self.log("Stop manual demonstration first.")
            return
        if self.telemetry_source.get() == "manual" and not all(
            [self.cfg.player_health,self.cfg.player_mana,self.cfg.target_health]
        ):
            self.log("Calibrate all three bars first or select addon telemetry.")
            return
        self.store_flags()
        if self.cfg.enable_movement and self.cfg.telemetry_source != "addon":
            self.log("Movement requires PriestBridge addon telemetry to report range/facing events. Select addon first.")
            return
        if self.cfg.input_mode == "background":
            if self.cfg.telemetry_source != "addon":
                self.log("Background mode requires addon telemetry (visual manual calibration is not verified for this mode).")
                return
            if not self.listener or not getattr(self.listener, "running", False):
                self.log("Background mode requires the F9 emergency hotkey listener. Fix hotkeys before starting.")
                return
            try:
                from .background_input import choose_game_window
                target = choose_game_window(self.cfg.allowed_processes)
                self.log(f"Bound background input to WoW PID {target.pid}, HWND {target.hwnd} ({target.title}).")
                self.game_target = target
            except Exception as exc:
                self.log("Cannot start background mode: " + str(exc))
                return
        else:
            self.game_target = None
        self.background_test_cancel.set()
        self.stop_flag.clear()
        self.running=True
        self.worker=threading.Thread(target=self.loop,daemon=True)
        self.worker.start()
        self.state_text.set("Running: DRY RUN" if self.cfg.dry_run else "Running: LIVE INPUT")
        self.log("Started " + ("DRY RUN" if self.cfg.dry_run else "LIVE INPUT") +
                 (" (background PostMessage; queued does NOT confirm accepted)"
                  if self.cfg.input_mode == "background" else " (foreground)"))

    def panic(self):
        self.background_test_cancel.set()
        self.stop_flag.set()
        self.state_text.set("PANIC STOP - no further inputs")
        self.log("F9 emergency stop")

    def loop(self):
        try:
            from mss import mss
            from .vision import monitor_bars
            from .bridge import monitor_bridge, BridgeNotFound
            from .telemetry_guard import TelemetryGuard
            from .input_control import game_has_focus, press_game_key, hold_game_key
            from .background_input import target_is_valid, post_game_key, post_game_hold
            background = self.cfg.input_mode == "background"
            target = getattr(self, "game_target", None)
            with mss() as sct:
                engine=PriestEngine(self.cfg)
                from .learning import SessionRecorder, learning_root, game_frame, Advisory, observation_dict
                rec = None
                if self.cfg.learning_record_gameplay:
                    try:
                        rec = SessionRecorder(learning_root(), "bot")
                        self.bot_recorder = rec
                        self.events.put(("log", "Recording bot session: " + rec.session_id))
                    except OSError as exc:
                        self.events.put(("log", "Learning recorder disabled: " + str(exc)))
                advisory = Advisory(learning_root())
                last_advice = float('-inf')
                last_metrics=0.0
                last_status=""
                last_error_seq=None
                last_success_seq=None
                guard = TelemetryGuard(self.cfg.telemetry_grace_s,
                                       self.cfg.telemetry_recovery_frames)
                while not self.stop_flag.is_set():
                    if background:
                        if target is None or not target_is_valid(target, self.cfg.allowed_processes):
                            self.events.put(("log", "STOPPED: WoW background window disappeared, changed or was minimized"))
                            self.events.put(("status", "STOPPED: WoW window unavailable"))
                            self._alarm()
                            break
                    elif not game_has_focus(self.cfg.allowed_processes):
                        if last_status != "Game not foreground; paused":
                            last_status = "Game not foreground; paused"
                            self.events.put(("status",last_status))
                        self.stop_flag.wait(0.4)
                        continue
                    if self.cfg.telemetry_source == "addon":
                        try:
                            reading = monitor_bridge(sct)
                        except BridgeNotFound as exc:
                            first_bad = guard.missing_since is None
                            check = guard.failed(time.monotonic(), str(exc))
                            if first_bad:
                                self.events.put(("status", "PAUSED: verifying lost addon telemetry; no keys sent"))
                                self.events.put(("log", "Telemetry lost: " + str(exc) +
                                                 "; all inputs paused while checking"))
                            if check.state == 'stop':
                                self.events.put(("status", "STOPPED: addon telemetry did not recover"))
                                self.events.put(("log", f"STOPPED: addon telemetry invalid for "
                                                 f"{check.elapsed_s:.1f}s: {check.detail}"))
                                self._alarm()
                                break
                            self.stop_flag.wait(max(0.1, self.cfg.scan_period_s))
                            continue
                        check = guard.succeeded(time.monotonic())
                        if check.state == 'stop':
                            self.events.put(("status", "STOPPED: addon telemetry recovery timed out"))
                            self.events.put(("log", f"STOPPED: addon telemetry recovery exceeded "
                                             f"{check.elapsed_s:.1f}s; no inputs sent during outage"))
                            self._alarm()
                            break
                        if check.state == 'pause':
                            # A single clean frame after a failure is not enough;
                            # never act on an unconfirmed recovery frame.
                            self.stop_flag.wait(max(0.1, self.cfg.scan_period_s))
                            continue
                        if check.state == 'recovered':
                            self.events.put(("log", f"Telemetry restored after {check.elapsed_s:.1f}s "
                                             f"({self.cfg.telemetry_recovery_frames} clean frames); resuming"))
                            self.events.put(("status", "Telemetry restored; resuming"))
                        obs = reading.observation
                    else:
                        obs=monitor_bars(sct,self.cfg)
                    now=time.monotonic()
                    if obs.error_seq is not None:
                        if last_error_seq is None:
                            last_error_seq=obs.error_seq
                        elif obs.error_seq != last_error_seq:
                            last_error_seq=obs.error_seq
                            self.events.put(("log", f"Addon spell signal: {obs.error or 'expired/none'} (event {obs.error_seq})"))
                    if obs.success_seq is not None:
                        if last_success_seq is None:
                            last_success_seq=obs.success_seq
                        elif obs.success_seq != last_success_seq:
                            last_success_seq=obs.success_seq
                            self.events.put(("log", f"Confirmed cast event: {obs.success_spell or 'other'} (seq {obs.success_seq})"))
                    if now-last_metrics > .45:
                        extras = (f"  |  Casting {'yes' if obs.casting else 'no'}"
                                  if obs.casting is not None else "")
                        self.events.put(("metrics",f"HP {obs.hp:.0%}  |  Mana {obs.mana:.0%}  |  Target {obs.target_hp:.0%}" + extras))
                        self.events.put(("aura", (obs.shield_aura or 'legacy/unknown',
                                                  obs.pain_aura or 'legacy/unknown',
                                                  obs.success_spell or 'none')))
                        self.events.put(("target",(obs.target_seq,obs.success_seq)))
                        last_metrics=now
                    result=engine.update(obs,now)
                    if rec is not None:
                        try:
                            image = (game_frame(sct, self.cfg.allowed_processes)
                                     if now - rec.last_frame_at >= rec.screenshot_period_s else None)
                            rec.observe(obs, decision=result, image=image, mono=now, dry_run=self.cfg.dry_run)
                            if self.cfg.telemetry_source == 'addon':
                                from .semantic_bridge import monitor_semantics
                                packet = monitor_semantics(sct, reading)
                                if packet is not None:
                                    rec.ingest_semantic(packet, now)
                            # Read-only learned suggestions; never pass to engine/input code.
                            if advisory.names and image is not None and now - last_advice >= 8.0:
                                suggestion = advisory.predict(image, observation_dict(obs))
                                if suggestion and suggestion[1] >= .60:
                                    self.events.put(("log", f"ADVISORY ONLY: {suggestion[0]} "
                                                     f"(confidence {suggestion[1]:.0%}); no key sent"))
                                    last_advice = now
                        except Exception as exc:
                            self.events.put(("log", "Learning recording stopped: " + str(exc)))
                            rec.close()
                            rec = None
                    self.events.put(("decision",result.reason))
                    if result.stop:
                        self.events.put(("status", "STOPPED: "+result.reason))
                        self.events.put(("log", "STOPPED: "+result.reason))
                        self._alarm()
                        break
                    if result.action:
                        verb = "WOULD " if self.cfg.dry_run else ("POST " if background else "DO ")
                        self.events.put(("log", verb + result.action + " - " + result.reason))
                        if not self.cfg.dry_run:
                            if result.action in ('move_forward', 'turn_right'):
                                seconds = (self.cfg.approach_pulse_s if result.action == 'move_forward'
                                           else self.cfg.turn_pulse_s)
                                if background:
                                    post_game_hold(self.cfg.keys[result.action], target,
                                                   self.cfg.allowed_processes,
                                                   seconds=seconds,
                                                   cancelled=self.stop_flag.is_set)
                                else:
                                    hold_game_key(self.cfg.keys[result.action], self.cfg.allowed_processes,
                                                  seconds=seconds, cancelled=self.stop_flag.is_set)
                            elif background:
                                post_game_key(self.cfg.keys[result.action], target,
                                              self.cfg.allowed_processes,
                                              cancelled=self.stop_flag.is_set)
                            else:
                                # Test foreground AGAIN just before sending the key.
                                press_game_key(self.cfg.keys[result.action], self.cfg.allowed_processes)
                    if result.reason!=last_status:
                        last_status=result.reason
                        self.events.put(("status",last_status))
                    self.stop_flag.wait(max(0.1,self.cfg.scan_period_s))
        except Exception as exc:
            self.events.put(("status","ERROR: "+str(exc)))
            self.events.put(("log","ERROR: "+repr(exc)))
            self._alarm()
        finally:
            if 'rec' in locals() and rec is not None:
                rec.close()
                self.bot_recorder = None
                self.events.put(("log", "Learning session saved: " + rec.session_id))
                self.events.put(("auto_train", None))
            self.stop_flag.set()
            self.events.put(("stopped",None))

    def _alarm(self):
        if sys.platform=="win32":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

    def poll_events(self):
        try:
            while True:
                kind, value=self.events.get_nowait()
                if kind=="log":self.log(value)
                elif kind=="status":self.state_text.set(value)
                elif kind=="metrics":self.values_text.set(value)
                elif kind=="aura":
                    shield,pain,success=value
                    self.aura_text.set(f"Shield: {shield}  |  Pain: {pain}  |  Last confirmed cast: {success}")
                elif kind=="target":
                    target,success=value
                    self.target_text.set(f"Target generation: {target if target is not None else '--'}  |  "
                                         f"Success sequence: {success if success is not None else '--'}")
                elif kind=="decision": self.decision_text.set("Decision: "+value)
                elif kind=="diagnostic_done":
                    path, summary, error = value
                    if error:
                        self.log('Diagnostic export failed: ' + error)
                        messagebox.showerror('Diagnostics failed', error, parent=self.root)
                    else:
                        self.log(f"Diagnostics: {summary['passed']}/{summary['total']} passed — {path}")
                        messagebox.showinfo('Upload this report to ChatGPT',
                            f"Offline checks: {summary['passed']}/{summary['total']} passed.\n\n"
                            f"Upload this ZIP into PriestBot Chat 2:\n{path}\n\n"
                            'The live telemetry snapshot may say unavailable if WoW is not visible.',
                            parent=self.root)
                elif kind=="calibrate":self.capture()
                elif kind=="verify_addon":self.verify_addon()
                elif kind=="toggle":self.toggle()
                elif kind=="panic":self.panic()
                elif kind=="addon_done":
                    success, error = value
                    self.log("PriestBridge installed. Type /reload in WoW." if success else
                             "Addon update pending: " + (error or "UAC denied or copy failed."))
                    self.state_text.set("Addon installed — /reload in WoW" if success else "Addon update pending")
                elif kind=="auto_train": self._queue_training()
                elif kind=="auto_train_vision": self._queue_vision_training()
                elif kind=="training_done": self.training_running=False
                elif kind=="vision_training_done": self.vision_training_running=False
                elif kind=="stopped":
                    self.running=False
                    self.log("Worker stopped")
        except queue.Empty:
            pass
        self.root.after(120,self.poll_events)

    def close(self):
        self.background_test_cancel.set()
        self.stop_flag.set()
        self.demo_stop.set()
        if self.demo_mouse_listener is not None:
            self.demo_mouse_listener.stop()
        if self.listener:self.listener.stop()
        self.root.destroy()


def main():
    root=tk.Tk()
    App(root)
    root.mainloop()

if __name__=="__main__":
    main()
