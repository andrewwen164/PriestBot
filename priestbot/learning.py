"""Opt-in game-only demonstration recorder and offline *advisory-only* classifier.

The authoritative combat engine never calls this model for actions. No game-memory
reads, external services or background desktop/key logging. Frames are cropped to
the foreground game's client area, never the entire multi-monitor desktop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter, defaultdict
from .scene_vision import detect_red_nameplates, NameplateTracker, estimate_scene_shift
import json
import os
from pathlib import Path
import threading
import time
import uuid

import numpy as np
from PIL import Image

KEY_LABELS = ("move_forward", "turn_left", "turn_right", "move_backward",
              "strafe_left", "strafe_right", "jump", "auto_run")
MOUSE_LABELS = ("mouse_turn_left", "mouse_turn_right",
                "move_forward_mouse_turn_left", "move_forward_mouse_turn_right",
                "camera_look_left", "camera_look_right", "camera_look_up",
                "camera_look_down", "move_forward_camera_look_left",
                "move_forward_camera_look_right",
                "mouse_both_forward", "mouse_both_forward_turn_left",
                "mouse_both_forward_turn_right")
LABELS = KEY_LABELS + MOUSE_LABELS
MODIFIERS = {"shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r",
             "alt", "alt_l", "alt_r", "alt_gr", "cmd", "cmd_l", "cmd_r"}
PRIVACY_PAUSE_KEYS = {"enter", "return", "/", "slash"}
PRIVACY_END_KEYS = {"enter", "return", "esc", "escape"}
SYSTEM_KEYS = {"f6", "f7", "f8", "f9"}
MAX_EVENT_RATE_HZ = 30
MIN_MOUSE_DRAG_PX = 12
MAX_MOUSE_SAMPLE_PX = 600  # discard pointer-warp artifacts; report how many occurred
FEAT_W, FEAT_H = 32, 18
MIN_SAMPLES = 36
MIN_EACH = 8
ADVISORY_CONFIDENCE = 0.60


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def learning_root(project_root: Path | None = None) -> Path:
    # INSTALL: user data is intentionally outside the release file whitelist.
    return (project_root or Path(__file__).resolve().parents[1]) / "learning_data"


def game_frame(sct, allowed_processes: list[str]) -> Image.Image | None:
    """Capture only the client area of foreground WoW; never the browser/desktop.

    Returns None rather than guessing if not Windows, wrong PID/process, or the
    game is not focused. Excludes decorations and clamps dimensions.
    """
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    import psutil
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        exe_name = psutil.Process(pid.value).name().lower()
    except (psutil.Error, OSError):
        return None
    if exe_name not in {p.lower() for p in allowed_processes}:
        return None
    client = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None
    top_left = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(top_left)):
        return None
    width, height = client.right, client.bottom
    if not (100 <= width <= 7680 and 100 <= height <= 4320):
        return None
    grab = sct.grab({"left": top_left.x, "top": top_left.y,
                     "width": width, "height": height})
    return Image.frombytes("RGB", (width, height), grab.rgb)



def game_client_point(x: int, y: int, allowed_processes: list[str]):
    """Relative to active WoW client area; None for other apps/outside game.

    All standard keyboard events already pass a WoW foreground-PID check.
    This additional mouse-coordinate check prevents browser clicks or window
    chrome from being recorded as in-game input. OS mouse coordinates, not
    WoW raw-input relative look deltas.
    """
    if os.name != "nt":
        return int(x), int(y)  # for platform-independent offline tests only
    import ctypes
    from ctypes import wintypes
    import psutil
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        exe = psutil.Process(pid.value).name().lower()
    except (psutil.Error, OSError):
        return None
    if exe not in {p.lower() for p in allowed_processes}:
        return None
    bounds = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(bounds)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    xx, yy = int(x) - origin.x, int(y) - origin.y
    if not (0 <= xx < bounds.right and 0 <= yy < bounds.bottom):
        return None
    return xx, yy


def observation_dict(obs) -> dict:
    return {name: getattr(obs, name, None) for name in (
        "hp", "mana", "target_hp", "casting", "error", "error_seq",
        "shield_aura", "pain_aura", "success_spell", "success_seq", "target_seq")}


def _jsonl_write(file, obj):
    file.write(json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n")
    file.flush()


class SessionRecorder:
    """One session writer. Synchronizes UI hotkeys with the polling worker."""
    def __init__(self, base: Path, kind: str, *, screenshot_period_s: float = 1.0):
        if kind not in ("bot", "demonstration"):
            raise ValueError("Invalid session type")
        self.base = base
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:8]
        self.path = base / "sessions" / self.session_id
        (self.path / "frames").mkdir(parents=True, exist_ok=False)
        self.file = (self.path / "events.jsonl").open("w", encoding="utf-8")
        self.lock = threading.RLock()
        self.kind = kind
        self.closed = False
        self.last_frame_at = float("-inf")
        self.screenshot_period_s = min(screenshot_period_s, .20) if kind == "demonstration" else screenshot_period_s
        self.last_frame: str | None = None
        self.last_obs: dict | None = None
        self.last_frame_mono: float = float("-inf")
        # v0.22 visual-control intervals: separate temporal action heads,
        # rather than one mutually exclusive class for simultaneous movements.
        self._ctrl_last: float | None = None
        self._ctrl_durations: dict[str, float] = defaultdict(float)
        self._btn_durations: dict[str, float] = defaultdict(float)
        self._interval_mouse = [0, 0]
        self._previous_image: Image.Image | None = None
        self._previous_scene: list[dict] = []
        self._nameplate_tracker = NameplateTracker()
        self._previous_controls: dict = {}
        self._vision_intervals = 0
        self.pending_keys: dict[str, tuple[float, str, dict, bool]] = {}
        self.held_actions: set[str] = set()
        self.pending_mouse: dict | None = None  # RMB legacy movement label
        self.pending_left: dict | None = None
        self.held_buttons: set[str] = set()
        self.held_raw_keys: set[str] = set()
        self._mouse_button_starts: dict[str, dict] = {}
        self._mouse_last: tuple[int, int] | None = None
        self._both_buttons: dict | None = None
        self._last_mouse_event_at = float("-inf")
        self._accumulated_move = [0, 0]
        self.privacy_paused = False
        self.capture_paused = False
        self.session_mono: float | None = None
        self.mouse_to_finalize: dict | None = None
        self.stats = {"observations": 0, "decision_intents": 0, "manual_corrections": 0,
                      "mouse_corrections": 0, "input_events": 0,
                      "mouse_buttons": 0, "scroll_events": 0, "key_events": 0,
                      "privacy_suppressed": 0, "nontraining_inputs": 0,
                      "range_errors": 0, "los_errors": 0, "facing_errors": 0,
                      "confirmed_cast_events": 0, "visual_intervals": 0, "nameplate_candidates": 0}
        from .action_semantics import ActionSemanticTracker
        from .farming_demo import FarmingDemonstrations
        self.semantic = ActionSemanticTracker(emit=lambda event, **fields: self.log(event, **fields))
        self.farming = FarmingDemonstrations(self.path, emit=lambda event, **fields: self.log(event, **fields))
        self._previous_error_seq = None
        self._previous_success_seq = None
        self.log("session_start", kind=kind, schema=5, recording_scope="game_focused_only", vision="temporal_multi_control_v1")

    def log(self, event: str, **data):
        with self.lock:
            if not self.closed:
                _jsonl_write(self.file, {"time": _utc(), "event": event, **data})

    def _integrate_controls(self, mono: float):
        """Accumulate held-key/button occupancy, even for brief 50ms key holds."""
        if self._ctrl_last is None:
            self._ctrl_last = mono
            return
        duration = max(0.0, min(float(mono) - self._ctrl_last, 2.0))
        for action in self.held_actions:
            self._ctrl_durations[action] += duration
        for button in self.held_buttons:
            self._btn_durations[button] += duration
        self._ctrl_last = mono

    def _clear_visual_interval(self, *, clear_reference=False):
        self._ctrl_durations.clear()
        self._btn_durations.clear()
        self._interval_mouse[:] = [0, 0]
        if clear_reference:
            self._previous_image = None
            self._previous_scene = []
            self._nameplate_tracker.reset()
            self._ctrl_last = None
            self.last_frame_mono = float('-inf')
            self.last_frame = None

    def _visual_interval(self, image: Image.Image, mono: float, state: dict, current_frame: str):
        """Emit pre/post paired screenshots and simultaneous action occupancy.

        The INPUT of a learner is prior frames; the LABEL describes controls
        held between the prior frame and this one. Never use the resulting
        screenshot as input for predicting its preceding controls.
        """
        self._integrate_controls(mono)
        plates = [p.as_dict() for p in self._nameplate_tracker.update(detect_red_nameplates(image))]
        self.stats['nameplate_candidates'] += len(plates)
        if self.last_frame is not None and self._previous_image is not None:
            duration = mono - self.last_frame_mono
            if .05 <= duration <= 1.0 and not self.capture_paused and not self.privacy_paused:
                actions = {a: round(min(1.0, seconds/duration), 4)
                           for a, seconds in self._ctrl_durations.items() if seconds >= .025}
                buttons = {a: round(min(1.0, seconds/duration), 4)
                           for a, seconds in self._btn_durations.items() if seconds >= .025}
                flow = estimate_scene_shift(self._previous_image, image)
                self.log('control_interval',
                         before_frame=self.last_frame, after_frame=current_frame,
                         before_state=self.last_obs or {}, after_state=state,
                         before_nameplates=self._previous_scene, after_nameplates=plates,
                         duration_ms=round(duration*1000),
                         movement_occupancy=actions, mouse_occupancy=buttons,
                         mouse_dx=self._interval_mouse[0], mouse_dy=self._interval_mouse[1],
                         scene_shift=flow, previous_controls=self._previous_controls,
                         phase=self.farming.phase,
                         schema=1, label_source='observed_human_inputs_not_verified_outcome')
                self.stats['visual_intervals'] += 1
                self._vision_intervals += 1
        self._previous_controls = {'movement': dict(self._ctrl_durations),
                                   'mouse_buttons': dict(self._btn_durations),
                                   'mouse_dx': self._interval_mouse[0],
                                   'mouse_dy': self._interval_mouse[1]}
        self._previous_image = image.copy()
        self._previous_scene = plates
        self._clear_visual_interval()
        self._ctrl_last = mono

    def observe(self, obs, *, decision=None, image: Image.Image | None = None,
                mono: float | None = None, dry_run: bool = True):
        mono = time.monotonic() if mono is None else mono
        snapshot = observation_dict(obs)
        with self.lock:
            if self.closed:
                return
            if self.capture_paused or self.privacy_paused:
                # Chat and manually paused UI fields must NOT appear in frames.
                image = None
                self._clear_visual_interval(clear_reference=True)
            prior_state = self.last_obs
            if self.kind == 'demonstration':
                self.semantic.expire(mono)
            self.stats["observations"] += 1
            if decision is not None and decision.action:
                self.stats["decision_intents"] += 1
            error_seq = snapshot.get("error_seq")
            if error_seq is not None and self._previous_error_seq is not None and error_seq != self._previous_error_seq:
                event = str(snapshot.get("error"))
                field = {"range": "range_errors", "los": "los_errors", "facing": "facing_errors"}.get(event)
                if field:
                    self.stats[field] += 1
            self._previous_error_seq = error_seq
            success_seq = snapshot.get("success_seq")
            if success_seq is not None and self._previous_success_seq is not None and success_seq != self._previous_success_seq:
                self.stats["confirmed_cast_events"] += 1
            self._previous_success_seq = success_seq
            if image is not None and mono - self.last_frame_at >= self.screenshot_period_s:
                path = f"frames/{uuid.uuid4().hex[:16]}.jpg"
                # Downsample before saving: bounded disk space and no outside-game windows.
                image = image.copy()
                image.thumbnail((800, 450) if self.kind == 'demonstration' else (640, 360),
                                Image.Resampling.BILINEAR)
                image.save(self.path / path, quality=76 if self.kind == 'demonstration' else 70,
                           optimize=True)
                if self.kind == 'demonstration' and not self.capture_paused and not self.privacy_paused:
                    # Important: previous observation belongs to BEFORE frame.
                    state_after = snapshot
                    self.last_obs = prior_state
                    self._visual_interval(image, mono, state_after, path)
                self.last_frame = path
                if self.kind == 'demonstration' and not self.capture_paused and not self.privacy_paused:
                    self.farming.observe(path, snapshot, mono)
                self.last_frame_at = mono
                self.last_frame_mono = mono
            self.last_obs = snapshot
            self.log("observation", state=snapshot, frame=self.last_frame if mono - self.last_frame_mono <= 1.5 else None,
                     decision=decision.action if decision else None,
                     reason=decision.reason if decision else None,
                     dry_run=dry_run)
            # Attach an AFTER frame only when it was actually captured after release.
            if self.mouse_to_finalize and self.last_frame_mono >= self.mouse_to_finalize["released_at"]:
                self._finalize_mouse(after_frame=self.last_frame, after_state=snapshot)

    def _input(self, kind: str, mono: float, **data):
        """Timestamped game-only input timeline; no events from other applications."""
        if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
            return
        if self.session_mono is None:
            self.session_mono = mono
        self.stats["input_events"] += 1
        self.semantic.input(kind, mono, **data)
        from .action_semantics import wow_binding
        chord = wow_binding(data.get('chord') or data.get('key') or '')
        binding = self.semantic.bindings.get(chord)
        self.farming.input(kind, mono, data=data, binding=binding)
        self.log("input", kind=kind, t_ms=round(1000 * max(0, mono - self.session_mono)),
                 frame=self.last_frame if mono - self.last_frame_mono <= .85 else None,
                 held_keys=sorted(self.held_raw_keys), held_buttons=sorted(self.held_buttons), **data)

    @staticmethod
    def _mods(keys):
        normalized = {"ctrl" if k.startswith("ctrl") else "shift" if k.startswith("shift")
                      else "alt" if k.startswith("alt") else "win" for k in keys if k in MODIFIERS}
        return sorted(normalized)

    def raw_key(self, name: str, pressed: bool, mono: float, *, action: str | None = None, record: bool = True):
        """Capture key state/chords without recording keys typed into normal WoW chat.

        The app passes only calls vetted as foreground-WoW input. 'Enter' and '/'
        open a conservative chat privacy gate; Escape/Enter closes it. The UI
        provides an explicit pause control for other edit boxes.
        """
        name = str(name).lower().strip()
        if not name or name in SYSTEM_KEYS:
            return
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused:
                return
            if self.privacy_paused:
                self.stats["privacy_suppressed"] += 1
                if pressed and name in PRIVACY_END_KEYS:
                    self.privacy_paused = False
                    self.held_raw_keys.clear()
                    self.pending_keys.clear()
                    self.held_actions.clear()
                    self.log("privacy_guard", state="resume", reason="chat_close")
                return
            if pressed and name in PRIVACY_PAUSE_KEYS and not self._mods(self.held_raw_keys):
                self.privacy_paused = True
                self._clear_visual_interval(clear_reference=True)
                self.farming.interrupt('chat_privacy_gate')
                self.held_raw_keys.clear()
                self.pending_keys.clear()
                self.held_actions.clear()
                self.log("privacy_guard", state="pause", reason="chat_open")
                return
            repeat = name in self.held_raw_keys
            self._integrate_controls(mono)
            if pressed:
                self.held_raw_keys.add(name)
            else:
                self.held_raw_keys.discard(name)
            if repeat and pressed:
                return  # key repeat is not another key-down action
            if record:
                self.stats["key_events"] += 1
                mods = self._mods(self.held_raw_keys)
                chord = "+".join(mods + [name]) if name not in MODIFIERS else name
                self._input("key_down" if pressed else "key_up", mono,
                            key=name, chord=chord, mapped_action=action,
                            modifiers=mods)

    def set_capture_paused(self, paused: bool):
        with self.lock:
            self.capture_paused = bool(paused)
            self.pending_keys.clear()
            self.held_actions.clear()
            self.held_raw_keys.clear()
            self._clear_visual_interval(clear_reference=True)
            self.farming.interrupt('manual_capture_pause' if paused else 'capture_resumed')
            self.held_buttons.clear()
            self.pending_mouse = None
            self.pending_left = None
            self._both_buttons = None
            self._mouse_button_starts.clear()
            self.log("capture_control", state="paused" if paused else "resumed")

    def focus_lost(self):
        """Never connect an in-game gesture to a later off-game event."""
        with self.lock:
            was_holding = bool(self.held_buttons or self.held_raw_keys or self.pending_mouse or self.pending_keys)
            self.cancel_mouse()
            self._clear_visual_interval(clear_reference=True)
            self.farming.interrupt('focus_lost')
            if was_holding:
                self.log("focus_lost", discarded_incomplete_gestures=True)

    def key_down(self, action: str, mono: float):
        if action not in KEY_LABELS:
            return
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
                return
            # Track concurrent movement keys; never mislabel W+strafe as W-only.
            if action not in self.held_actions and self.held_actions:
                for held in list(self.pending_keys):
                    start, frame, state, _ = self.pending_keys[held]
                    self.pending_keys[held] = (start, frame, state, True)
            self._integrate_controls(mono)
            self.held_actions.add(action)
            if action in self.pending_keys:
                return
            if not self.last_frame or mono - self.last_frame_mono > .85:
                return
            overlapping = bool(self.held_buttons) or self.mouse_to_finalize is not None or len(self.held_actions) > 1
            self.pending_keys[action] = (mono, self.last_frame, dict(self.last_obs or {}), overlapping)
            if self.pending_mouse is not None:
                self.pending_mouse["keys_held"].add(action)
                if action == "move_forward":
                    self.pending_mouse["forward_overlap"] = True

    def key_up(self, action: str, mono: float):
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
                return
            self._integrate_controls(mono)
            self.held_actions.discard(action)
            pending = self.pending_keys.pop(action, None)
            if not pending:
                return
            start, frame, state, overlaps_mouse = pending
            duration = round(max(0, mono - start) * 1000)
            # Don't train W-only on a screenshot when W was part of a mouse turn.
            if 30 <= duration <= 5000 and not overlaps_mouse:
                self.stats["manual_corrections"] += 1
                self.log("correction", label=action, frame=frame, state=state,
                         duration_ms=duration, source="human_game_focused")

    def cancel_mouse(self):
        """Drop incomplete drags on focus loss; never learn desktop/browser gestures."""
        with self.lock:
            self.pending_mouse = None
            self.pending_left = None
            self._both_buttons = None
            self.held_buttons.clear()
            self._mouse_button_starts.clear()
            self._mouse_last = None
            self.held_raw_keys.clear()
            self.held_actions.clear()
            self.pending_keys.clear()

    def mouse_press(self, x: int, y: int, mono: float):
        """A right-button DOWN only. The GUI must validate WoW foreground first."""
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.pending_mouse is not None or self.capture_paused or self.privacy_paused:
                return
            if self.mouse_to_finalize:
                self._finalize_mouse()  # don't mix consecutive drags
            if not self.last_frame or mono - self.last_frame_mono > .85:
                return
            self.pending_mouse = {
                "start": mono, "before_frame": self.last_frame,
                "before_state": dict(self.last_obs or {}),
                "last_x": int(x), "last_y": int(y),
                "dx": 0, "dy": 0, "distance_px": 0,
                "samples": 0, "warp_samples": 0,
                "keys_held": set(self.held_actions),
                "forward_overlap": "move_forward" in self.held_actions,
            }

    def mouse_move(self, x: int, y: int, mono: float):
        """Record screen-coordinate pointer deltas WHILE RMB held.

        Raw-input cursor-lock games may suppress OS move events; this recorder
        deliberately does not claim to capture raw game-relative mouse deltas.
        """
        with self.lock:
            m = self.pending_mouse
            if self.closed or not m or self.capture_paused or self.privacy_paused:
                return
            dx, dy = int(x) - m["last_x"], int(y) - m["last_y"]
            m["last_x"], m["last_y"] = int(x), int(y)
            if abs(dx) > MAX_MOUSE_SAMPLE_PX or abs(dy) > MAX_MOUSE_SAMPLE_PX:
                m["warp_samples"] += 1
                return
            if dx == dy == 0:
                return
            m["dx"] += dx
            m["dy"] += dy
            m["distance_px"] += abs(dx) + abs(dy)
            m["samples"] += 1
            m["keys_held"].update(self.held_actions)
            if "move_forward" in self.held_actions:
                m["forward_overlap"] = True
            # A meaningful RMB drag means concurrent W is NOT a W-only label.
            if abs(m["dx"]) >= MIN_MOUSE_DRAG_PX:
                for action, (start, frame, state, overlap) in list(self.pending_keys.items()):
                    self.pending_keys[action] = (start, frame, state, True)

    def mouse_release(self, mono: float):
        with self.lock:
            m, self.pending_mouse = self.pending_mouse, None
            if self.closed or self.kind != "demonstration" or not m:
                return
            elapsed_ms = round(max(0, mono - m["start"]) * 1000)
            if not (30 <= elapsed_ms <= 5000) or m["samples"] < 1:
                return
            if abs(m["dx"]) < MIN_MOUSE_DRAG_PX:
                # Pure vertical motion or back-and-forth cannot be used to
                # label a horizontal facing direction safely.
                return
            direction = "right" if m["dx"] > 0 else "left"
            prefix = ("mouse_both_forward_turn_" if m.get("both_overlap") else
                      "move_forward_mouse_turn_" if m["forward_overlap"] else "mouse_turn_")
            self.mouse_to_finalize = {
                "label": prefix + direction,
                "frame": m["before_frame"], "state": m["before_state"],
                "duration_ms": elapsed_ms, "mouse_dx": m["dx"], "mouse_dy": m["dy"],
                "mouse_distance_px": m["distance_px"],
                "mouse_samples": m["samples"], "discarded_warp_samples": m["warp_samples"],
                "keys_held": sorted(m["keys_held"]), "right_mouse_held": True,
                "left_mouse_held": bool(m.get("both_overlap")),
                "released_at": mono, "source": "human_right_drag_wow_focused",
            }

    def mouse_button(self, button: str, pressed: bool, x: int, y: int,
                     mono: float):
        """Record left/right/middle/X buttons, clicks, simultaneous buttons and drags."""
        button = str(button).lower()
        if button not in {"left", "right", "middle", "x1", "x2", "unknown"}:
            button = "unknown"
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
                return
            if pressed and button in self.held_buttons:
                return
            if not pressed and button not in self.held_buttons:
                return
            self.stats["mouse_buttons"] += 1
            x, y = int(x), int(y)
            self._integrate_controls(mono)
            if pressed:
                if not self.held_buttons:
                    self._mouse_last = x, y
                self.held_buttons.add(button)
                self._mouse_button_starts[button] = {
                    "start": mono, "x": x, "y": y, "frame": self.last_frame,
                    "state": dict(self.last_obs or {}), "dragged": False,
                }
                if button == "right":
                    self.mouse_press(x, y, mono)
                elif button == "left" and self.last_frame and mono - self.last_frame_mono <= .85:
                    self.pending_left = {
                        "start": mono, "frame": self.last_frame,
                        "state": dict(self.last_obs or {}), "last_x": x, "last_y": y,
                        "dx": 0, "dy": 0, "samples": 0, "distance_px": 0,
                        "keys_held": set(self.held_actions),
                        "forward_overlap": "move_forward" in self.held_actions,
                        "both_overlap": "right" in self.held_buttons,
                    }
                if {"left", "right"}.issubset(self.held_buttons):
                    if self.pending_mouse:
                        self.pending_mouse["both_overlap"] = True
                    if self.pending_left:
                        self.pending_left["both_overlap"] = True
                    if self._both_buttons is None:
                        self._both_buttons = {
                            "start": mono, "frame": self.last_frame,
                            "state": dict(self.last_obs or {}),
                            "keys_held": set(self.held_actions),
                            "turned": False,
                        }
            else:
                self.held_buttons.remove(button)
            self._input("mouse_down" if pressed else "mouse_up", mono,
                        button=button, x=x, y=y,
                        modifiers=self._mods(self.held_raw_keys))
            if not pressed:
                start = self._mouse_button_starts.pop(button, None)
                if start is not None:
                    duration_ms = round(max(0, mono - start["start"]) * 1000)
                    if duration_ms >= 0:
                        self.stats["nontraining_inputs"] += 1
                        self.log("mouse_gesture", button=button,
                                 duration_ms=duration_ms,
                                 x_start=start["x"], y_start=start["y"],
                                 x_end=x, y_end=y, moved=start["dragged"],
                                 frame=start["frame"], state=start["state"],
                                 trainable=False)
                if button == "right":
                    self.mouse_release(mono)
                elif button == "left":
                    self._finish_left(mono)
                if self._both_buttons is not None and not {"left", "right"}.issubset(self.held_buttons):
                    both, self._both_buttons = self._both_buttons, None
                    if (self.mouse_to_finalize is None and not both.get("turned")
                            and 30 <= (mono - both["start"]) * 1000 <= 5000
                            and both.get("frame")):
                        self._queue_correction(
                            "mouse_both_forward", both["frame"], both["state"],
                            round((mono - both["start"]) * 1000), released_at=mono,
                            both_buttons_held=True,
                            keys_held=sorted(both["keys_held"]),
                            source="human_lmb_rmb_wow_focused")
            if pressed and {"left", "right"}.issubset(self.held_buttons):
                for action, (start, frame, state, _) in list(self.pending_keys.items()):
                    self.pending_keys[action] = (start, frame, state, True)

    def _queue_correction(self, label: str, frame: str, state: dict, duration_ms: int, **meta):
        if not frame or label not in LABELS or self.closed:
            return
        if self.mouse_to_finalize:
            self._finalize_mouse()  # previous action has no after-frame available
        self.mouse_to_finalize = {"label": label, "frame": frame, "state": state,
                                  "duration_ms": duration_ms, **meta}
        self.mouse_to_finalize.setdefault("released_at", float("inf"))

    def _finish_left(self, mono: float):
        m, self.pending_left = self.pending_left, None
        if m is None:
            return
        ms = round(max(0, mono - m["start"]) * 1000)
        if m.get("both_overlap") or not (30 <= ms <= 5000) or m["samples"] < 1:
            return  # simultaneous mouse motion belongs to the RMB facing label
        dx, dy = m["dx"], m["dy"]
        if max(abs(dx), abs(dy)) < MIN_MOUSE_DRAG_PX:
            return
        axis = "left" if dx < 0 else "right"
        if abs(dy) > abs(dx) * 1.5:
            axis = "up" if dy < 0 else "down"
        # Camera-only motion is never labeled as a character turn.
        prefix = "move_forward_camera_look_" if m["forward_overlap"] and axis in ("left", "right") else "camera_look_"
        self._queue_correction(prefix + axis, m["frame"], m["state"], ms,
                               released_at=mono, mouse_dx=dx, mouse_dy=dy,
                               mouse_distance_px=m["distance_px"],
                               mouse_samples=m["samples"],
                               left_mouse_held=True,
                               keys_held=sorted(m["keys_held"]),
                               source="human_left_drag_wow_focused",
                               interpretation="camera_look_assumed_default_bindings",
                               ui_interaction_unverified=True)

    def all_mouse_move(self, x: int, y: int, mono: float):
        """Batch move observations while mouse buttons are held; never log idle cursor trails."""
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
                return
            x, y = int(x), int(y)
            if self._mouse_last is None:
                self._mouse_last = x, y
            dx, dy = x - self._mouse_last[0], y - self._mouse_last[1]
            self._mouse_last = x, y
            if not self.held_buttons:
                # Mouseover/targeting without clicks matters, but capture at a
                # lower rate to keep sessions small. Never label as movement.
                if mono - self._last_mouse_event_at >= .10 and (dx or dy):
                    self._input("cursor_move", mono, x=x, y=y, dx=dx, dy=dy)
                    self._last_mouse_event_at = mono
                return
            if max(abs(dx), abs(dy)) > MAX_MOUSE_SAMPLE_PX:
                self._input("mouse_warp_ignored", mono, x=x, y=y)
                # Still let the legacy recorder count and discard the jump.
                if self.pending_mouse:
                    self.mouse_move(x, y, mono)
                if self.pending_left:
                    self.pending_left["last_x"] = x
                    self.pending_left["last_y"] = y
                return
            for start in self._mouse_button_starts.values():
                if abs(x - start["x"]) + abs(y - start["y"]) >= MIN_MOUSE_DRAG_PX:
                    start["dragged"] = True
            if self.pending_mouse:
                self.mouse_move(x, y, mono)
                if self._both_buttons is not None and abs(self.pending_mouse["dx"]) >= MIN_MOUSE_DRAG_PX:
                    self._both_buttons["turned"] = True
            if self.pending_left:
                left = self.pending_left
                left_dx, left_dy = x - left["last_x"], y - left["last_y"]
                left["last_x"], left["last_y"] = x, y
                if left_dx or left_dy:
                    left["dx"] += left_dx
                    left["dy"] += left_dy
                    left["distance_px"] += abs(left_dx) + abs(left_dy)
                    left["samples"] += 1
                    left["keys_held"].update(self.held_actions)
                    if "move_forward" in self.held_actions:
                        left["forward_overlap"] = True
                        for action, (start, frame, state, _) in list(self.pending_keys.items()):
                            self.pending_keys[action] = (start, frame, state, True)
            self._accumulated_move[0] += dx
            self._accumulated_move[1] += dy
            self._interval_mouse[0] += dx
            self._interval_mouse[1] += dy
            if mono - self._last_mouse_event_at >= 1 / MAX_EVENT_RATE_HZ:
                self._input("mouse_drag_delta", mono, x=x, y=y,
                            dx=self._accumulated_move[0], dy=self._accumulated_move[1])
                self._accumulated_move[:] = [0, 0]
                self._last_mouse_event_at = mono

    def scroll(self, x: int, y: int, dx: float, dy: float, mono: float):
        with self.lock:
            if self.closed or self.kind != "demonstration" or self.capture_paused or self.privacy_paused:
                return
            self.stats["scroll_events"] += 1
            self.stats["nontraining_inputs"] += 1
            self._input("scroll", mono, x=int(x), y=int(y),
                        dx=float(dx), dy=float(dy), modifiers=self._mods(self.held_raw_keys))

    def _finalize_mouse(self, *, after_frame=None, after_state=None):
        # Caller holds lock. AFTER frame must be captured on a subsequent tick.
        m, self.mouse_to_finalize = self.mouse_to_finalize, None
        if m is None:
            return
        m = dict(m)
        m.pop("released_at")
        m["frame_after"] = after_frame
        m["state_after"] = after_state
        self.stats["manual_corrections"] += 1
        self.stats["mouse_corrections"] += 1
        self.log("correction", **m)

    def ingest_semantic(self, packet, mono=None):
        with self.lock:
            if not self.closed and not self.capture_paused and not self.privacy_paused:
                now = time.monotonic() if mono is None else mono
                self.semantic.ingest(packet, now)
                self.farming.packet(packet, now)

    def farming_report(self):
        with self.lock:
            return self.farming.snapshot()

    def semantics_report(self):
        with self.lock:
            return self.semantic.snapshot()

    def close(self):
        with self.lock:
            if self.closed:
                return
            if self.mouse_to_finalize:
                self._finalize_mouse()
            self.pending_mouse = None
            self.pending_left = None
            self._both_buttons = None
            self.held_buttons.clear()
            self.held_raw_keys.clear()
            self._mouse_button_starts.clear()
            self.held_actions.clear()
            self.pending_keys.clear()
            self.log("session_end", kind=self.kind)
            self.farming.close()
            self.closed = True
            self.file.close()
            (self.path / "action_semantics.json").write_text(
                json.dumps(self.semantic.snapshot(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            (self.path / "summary.json").write_text(json.dumps({
                "session_id": self.session_id, "kind": self.kind,
                "counters": self.stats,
                "limitations": "Game-focused, opt-in input events; chat Enter/slash guarded (other UI fields need manual pause). "
                               "Mouse OS pointer movement may omit raw relative WoW camera data; "
                               "unrecognized mouse/keyboard actions stored but not trained. "
                               "Kill, loot, and targeting outcomes need explicit game event verification"
            }, indent=2) + "\n", encoding="utf-8")


def _image_features(path: Path, state: dict | None) -> np.ndarray:
    # Use actual game-scene pixels, plus numeric telemetry, not target IDs.
    with Image.open(path) as src:
        gray = src.convert("L").resize((FEAT_W, FEAT_H), Image.Resampling.BILINEAR)
        visual = np.asarray(gray, dtype=np.float32).reshape(-1) / 255.0
    state = state or {}
    nums = [float(state.get(k) or 0) for k in ("hp", "mana", "target_hp")]
    errs = [float(state.get("error") == k) for k in ("range", "los", "facing")]
    cast = [float(state.get("casting") is True)]
    return np.concatenate([visual, np.array(nums + errs + cast, dtype=np.float32)])


def load_corrections(base: Path):
    samples = []
    for event_file in sorted((base / "sessions").glob("*/events.jsonl")):
        try:
            with event_file.open(encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line)
                    if row.get("event") != "correction" or row.get("label") not in LABELS:
                        continue
                    rel = row.get("frame")
                    if not isinstance(rel, str) or not rel.startswith("frames/") or ".." in Path(rel).parts:
                        continue
                    frame = event_file.parent / rel
                    if frame.is_file():
                        samples.append((event_file.parent.name, row["label"], frame, row.get("state")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return samples


def training_coverage(base: Path, *, recommended_per_action: int = 20) -> dict:
    """Count *usable, screenshot-backed* human labels, not raw key events.

    Coverage is advisory and cannot change the deployment gate. Show actions
    with observations first, followed by a curated core movement practice set.
    """
    samples = load_corrections(base)
    counts = Counter(label for _, label, _, _ in samples)
    per_session = defaultdict(Counter)
    for session, label, _, _ in samples:
        per_session[session][label] += 1
    priority = ("move_forward", "mouse_turn_left", "mouse_turn_right",
                "move_forward_mouse_turn_left", "move_forward_mouse_turn_right",
                "strafe_left", "strafe_right")
    action_names = sorted(set(counts) | set(priority),
                          key=lambda a: (-counts[a], a not in priority, a))
    actions = []
    for action in action_names:
        count = counts[action]
        seen_sessions = sum(1 for ss in per_session.values() if ss[action])
        actions.append({"action": action, "samples": count,
                        "sessions": seen_sessions,
                        "minimum": MIN_EACH,
                        "training_shortfall": max(0, MIN_EACH - count),
                        "recommended": recommended_per_action,
                        "recommended_shortfall": max(0, recommended_per_action - count),
                        "training_supported": count >= MIN_EACH})
    eligible = [a for a in actions if a["training_supported"]]
    total_supported = sum(a["samples"] for a in eligible)
    notes = []
    if len(eligible) < 2:
        notes.append("Record at least two different movement actions with 8 usable screenshots each.")
    if total_supported < MIN_SAMPLES:
        notes.append(f"Collect at least {MIN_SAMPLES - total_supported} more eligible labels "
                     f"(currently {total_supported}/{MIN_SAMPLES}).")
    if len(per_session) < 2:
        notes.append("Record a separate demonstration session for independent evaluation; "
                     "the latest session must contain at least 12 labeled examples of trained actions.")
    else:
        last = sorted(per_session)[-1]
        holdout = per_session[last]
        older = Counter()
        for session, ct in per_session.items():
            if session != last:
                older.update(ct)
        covered_last = sum(n for label, n in holdout.items() if older[label] >= MIN_EACH)
        if covered_last < 12:
            notes.append("The latest independent session has only " + str(covered_last) +
                         "/12 eligible holdout examples with classes supported in earlier sessions. "
                         "Record 12+ examples of previously practiced actions in a new session.")
    if not notes:
        notes.append("Minimum label coverage reached. Evaluate the latest candidate on "
                     "a separate session; passing is not guaranteed.")
    return {"total_labels": len(samples), "usable_for_training": total_supported,
            "sessions": len(per_session), "action_count": len(eligible),
            "actions": actions, "next_steps": notes,
            "raw_inputs_not_training_labels": True}


def mouse_motion_profiles(base: Path) -> dict:
    """Descriptive training labels for candidate report; never used for inputs."""
    from statistics import median
    groups: dict[str, list] = {x: [] for x in MOUSE_LABELS}
    for event_file in sorted((base / "sessions").glob("*/events.jsonl")):
        try:
            with event_file.open(encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line)
                    if row.get("event") == "correction" and row.get("label") in groups:
                        if all(isinstance(row.get(k), (int, float))
                               for k in ("mouse_dx", "mouse_dy", "duration_ms")):
                            groups[row["label"]].append(row)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return {k: {"samples": len(rows),
                "median_dx_px": round(median(r["mouse_dx"] for r in rows), 1),
                "median_dy_px": round(median(r["mouse_dy"] for r in rows), 1),
                "median_duration_ms": round(median(r["duration_ms"] for r in rows))}
            for k, rows in groups.items() if rows}


def _class_scores(y_true: np.ndarray, y_pred: np.ndarray, count: int):
    cm = np.zeros((count, count), dtype=int)
    for true, pred in zip(y_true, y_pred):
        cm[int(true), int(pred)] += 1
    precisions, recalls, f1s = [], [], []
    for c in range(count):
        tp = cm[c, c]
        precision = tp / max(1, cm[:, c].sum())
        recall = tp / max(1, cm[c, :].sum())
        precisions.append(float(precision))
        recalls.append(float(recall))
        f1s.append(float(2 * precision * recall / max(1e-9, precision + recall)))
    return {"accuracy": float(np.mean(y_true == y_pred)),
            "macro_f1": float(np.mean(f1s)), "recall_by_class": recalls,
            "confusion_matrix": cm.tolist()}


def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    exp = np.exp(z)
    return exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-9)


def train_candidate(base: Path, *, epochs: int = 130, seed: int = 17) -> dict:
    """CPU-supervised imitation baseline. Human demonstrations ONLY.

    Train and validate on DIFFERENT sessions. If there aren't enough separate
    sessions, save a candidate but explicitly DO NOT pass the promotion gate.
    Auto training never changes the active model or the combat state machine.
    """
    samples = load_corrections(base)
    if len(samples) < MIN_SAMPLES:
        return {"status": "insufficient_data", "message": f"Need {MIN_SAMPLES} human corrections; have {len(samples)}."}
    counts = Counter(s[1] for s in samples)
    usable_labels = {label for label, n in counts.items() if n >= MIN_EACH}
    omitted_labels = {label: n for label, n in counts.items() if n < MIN_EACH}
    samples = [s for s in samples if s[1] in usable_labels]
    if len(samples) < MIN_SAMPLES:
        return {"status": "insufficient_data", "message":
                f"Need {MIN_SAMPLES} supported examples after excluding rare labels; have {len(samples)}."}
    if len(usable_labels) < 2:
        return {"status": "insufficient_data", "message": "Need at least two movement/camera actions with 8 examples each."}

    vectors, classes, sessions, samples_base_frames = [], [], [], []
    for session, label, frame, state in samples:
        try:
            vector = _image_features(frame, state)
        except (OSError, ValueError):
            continue
        vectors.append(vector)
        classes.append(label)
        sessions.append(session)
        samples_base_frames.append(frame)
    if len(vectors) < MIN_SAMPLES:
        return {"status": "insufficient_data", "message": "Insufficient readable game screenshots."}
    X = np.stack(vectors)
    names = sorted(set(classes))
    y = np.array([names.index(c) for c in classes], dtype=np.int64)
    distinct_sessions = sorted(set(sessions))
    # Hold out an entire session, not random adjacent frames from one fight.
    if len(distinct_sessions) >= 2:
        last = distinct_sessions[-1]
        valid = np.array([s == last for s in sessions], dtype=bool)
        train = ~valid
    else:
        valid = np.zeros(len(y), dtype=bool)
        train = ~valid
    proposed_train = int(train.sum())
    proposed_holdout = int(valid.sum())
    holdout_labels = {names[int(c)] for c in set(y[valid])}
    train_labels = {names[int(c)] for c in set(y[train])}
    split_checks = {
        "separate_session": len(distinct_sessions) >= 2,
        "holdout_at_least_12": proposed_holdout >= 12,
        "train_at_least_24": proposed_train >= 24,
        "holdout_classes_in_training": holdout_labels.issubset(train_labels),
        "all_classes_in_training": len(train_labels) == len(names),
    }
    # Never evaluate a holdout if one of its labels was absent in training.
    split_usable = (valid.sum() >= 12 and train.sum() >= 24 and
                    set(y[valid]).issubset(set(y[train])) and
                    len(set(y[train])) == len(names))
    if not split_usable:
        train = np.ones(len(y), dtype=bool)
        valid = ~train

    rng = np.random.default_rng(seed)
    mu = X[train].mean(0)
    sd = np.maximum(X[train].std(0), 0.1)
    Z = np.clip((X[train] - mu) / sd, -4, 4)
    D, C = X.shape[1], len(names)
    W = rng.normal(scale=0.01, size=(D, C)).astype(np.float32)
    b = np.zeros(C, dtype=np.float32)
    yt = y[train]
    onehot = np.eye(C, dtype=np.float32)[yt]
    counts = np.bincount(yt, minlength=C)
    sample_weights = 1.0 / np.maximum(counts[yt].astype(np.float32), 1)
    sample_weights /= sample_weights.mean()
    for i in range(max(1, epochs)):
        probs = _softmax(Z @ W + b)
        grad = (probs - onehot) * sample_weights[:, None] / len(Z)
        lr = 0.16 / (1 + 0.018 * i)
        W -= lr * (Z.T @ grad + 0.015 * W)
        b -= lr * grad.sum(0)

    evaluation = {"split_checks": split_checks, "proposed_holdout_samples": proposed_holdout,
                  "proposed_train_samples": proposed_train,
                  "evaluated": bool(split_usable), "promotion_eligible": False,
                  "holdout_session": distinct_sessions[-1] if split_usable else None,
                  "holdout_samples": int(valid.sum()), "train_samples": int(train.sum()),
                  "explanation": "Need a separate session containing at least 12 labeled examples across trained actions."}
    if split_usable:
        pred = np.argmax(_softmax(np.clip((X[valid] - mu) / sd, -4, 4) @ W + b), axis=1)
        met = _class_scores(y[valid], pred, C)
        probabilities = _softmax(np.clip((X[valid] - mu) / sd, -4, 4) @ W + b)
        valid_indices = np.flatnonzero(valid)
        examples = []
        for row_idx, prediction, probability in zip(valid_indices, pred, probabilities):
            # The UI resolves these only against learning_root; never an absolute path.
            try:
                frame_relative = str(samples_base_frames[int(row_idx)].relative_to(base))
            except (ValueError, IndexError):
                frame_relative = None
            examples.append({"session": sessions[int(row_idx)],
                             "truth": classes[int(row_idx)],
                             "predicted": names[int(prediction)],
                             "correct": bool(int(prediction) == int(y[int(row_idx)])),
                             "confidence": round(float(max(probability)), 4),
                             "frame": frame_relative})
        # Include misses first, plus representative correct examples. This is a
        # summary, not a hidden evaluation subsample: metrics use ALL holdout rows.
        misses = [x for x in examples if not x["correct"]]
        hits = [x for x in examples if x["correct"]]
        evaluation["examples"] = misses[:12] + hits[:8]
        evaluation["examples_total"] = len(examples)
        evaluation["examples_misclassified_total"] = len(misses)
        evaluation["per_action"] = []
        for cls_index, cls_name in enumerate(names):
            cm_values = (y[valid] == cls_index).sum()
            actual_correct = int(((y[valid] == cls_index) & (pred == cls_index)).sum())
            predicted_n = int((pred == cls_index).sum())
            prec = actual_correct / max(1, predicted_n)
            rec = actual_correct / max(1, int(cm_values))
            f1 = 2 * prec * rec / max(1e-9, prec + rec)
            evaluation["per_action"].append({"action": cls_name,
                "holdout_samples": int(cm_values), "correct": actual_correct,
                "wrong": int(cm_values) - actual_correct,
                "precision": round(prec, 4), "recall": round(rec, 4),
                "f1": round(f1, 4)})
        majority_label = int(np.bincount(y[train], minlength=C).argmax())
        majority = float(np.mean(y[valid] == majority_label))
        # Explicit gate: genuine holdout, exceeds majority baseline, precision
        # across actions. Never promote from training-set accuracy alone.
        passed = (met["accuracy"] >= max(0.65, majority + .05) and
                  met["macro_f1"] >= .60 and
                  all(met["recall_by_class"][i] >= .40 for i in set(y[valid])))
        evaluation.update(met)
        evaluation["gate_checks"] = {
            "accuracy_at_least_65_pct": met["accuracy"] >= 0.65,
            "beats_majority_by_5_points": met["accuracy"] >= majority + 0.05,
            "macro_f1_at_least_60_pct": met["macro_f1"] >= 0.60,
            "every_tested_action_recall_at_least_40_pct": all(
                met["recall_by_class"][i] >= 0.40 for i in set(y[valid]))}
        evaluation.update({"baseline_accuracy": majority, "promotion_eligible": bool(passed),
                           "explanation": ("Eligible for explicit ADVISORY-only activation" if passed else
                                           "Holdout metrics below the safety gate")})
    candidate_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    candidate_dir = base / "candidates" / candidate_id
    candidate_dir.mkdir(parents=True)
    np.savez_compressed(candidate_dir / "model.npz", weights=W, bias=b, mean=mu, scale=sd)
    report = {"candidate_id": candidate_id, "created_at": _utc(),
              "model": "linear_softmax_visual_imitation_baseline_v1",
              "classes": names, "training": {"samples": len(y), "sessions": len(distinct_sessions),
                                          "source": "manual corrections only", "epochs": epochs},
              "evaluation": evaluation,
              "mouse_motion_profiles": mouse_motion_profiles(base),
        "omitted_rare_actions": omitted_labels,
              "deployment": "candidate_only_no_game_inputs"}
    (candidate_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (base / "latest_candidate.json").write_text(json.dumps({"candidate_id": candidate_id}) + "\n", encoding="utf-8")
    return {"status": "candidate_created", **report}


def latest_report(base: Path) -> dict | None:
    try:
        key = json.loads((base / "latest_candidate.json").read_text(encoding="utf-8"))["candidate_id"]
        if not isinstance(key, str) or not key.replace('-', '').isalnum():
            return None
        return json.loads((base / "candidates" / key / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def promote_advisory(base: Path, candidate_id: str) -> None:
    """Explicit gate. The promoted model is a read-only ADVISOR, not a controller."""
    report = latest_report(base)
    if not report or report["candidate_id"] != candidate_id:
        raise ValueError("Candidate missing or not latest")
    if not report["evaluation"]["evaluated"] or not report["evaluation"]["promotion_eligible"]:
        raise ValueError("Candidate did not pass independent evaluation")
    path = base / "candidates" / candidate_id / "model.npz"
    if not path.is_file():
        raise ValueError("Model weights missing")
    tmp = base / "active_advisory.json.tmp"
    tmp.write_text(json.dumps({"candidate_id": candidate_id, "mode": "advisory_only"}) + "\n", encoding="utf-8")
    os.replace(tmp, base / "active_advisory.json")


class Advisory:
    def __init__(self, base: Path):
        try:
            cfg = json.loads((base / "active_advisory.json").read_text(encoding="utf-8"))
            candidate_id = cfg["candidate_id"]
            report = json.loads((base / "candidates" / candidate_id / "report.json").read_text(encoding="utf-8"))
            if cfg.get("mode") != "advisory_only" or not report["evaluation"]["promotion_eligible"]:
                raise ValueError("No approved advisory")
            with np.load(base / "candidates" / candidate_id / "model.npz", allow_pickle=False) as f:
                self.W, self.b = f["weights"], f["bias"]
                self.mu, self.sd = f["mean"], f["scale"]
            self.names = report["classes"]
        except (OSError, KeyError, ValueError):
            self.names = []

    def predict(self, image: Image.Image, state: dict) -> tuple[str, float] | None:
        if not self.names:
            return None
        arr = np.asarray(image.convert("L").resize((FEAT_W, FEAT_H), Image.Resampling.BILINEAR),
                         dtype=np.float32).reshape(-1) / 255
        nums = [float(state.get(k) or 0) for k in ("hp", "mana", "target_hp")]
        errs = [float(state.get("error") == k) for k in ("range", "los", "facing")]
        x = np.concatenate([arr, np.array(nums + errs + [float(state.get("casting") is True)], np.float32)])
        probs = _softmax(np.clip(((x-self.mu)/self.sd),-4,4).reshape(1,-1) @ self.W + self.b)[0]
        i = int(np.argmax(probs))
        return self.names[i], float(probs[i])
