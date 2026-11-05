"""Windows-only focus-guarded keyboard sending. No hidden/background inputs."""
from __future__ import annotations
import os
import sys


def foreground_process() -> tuple[str, str]:
    """Return (executable base name, window title) for actual foreground window."""
    if sys.platform != "win32":
        raise OSError("Live keyboard mode requires Windows")
    import ctypes
    import psutil
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    # Explicit Win64 pointer types: ctypes default c_int truncates HWND on 64-bit Windows.
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        exe = psutil.Process(pid.value).name().lower()
    except (psutil.Error, OSError):
        exe = ""
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length+1)
    user32.GetWindowTextW(hwnd, buffer, length+1)
    return exe, buffer.value


def game_has_focus(allowed_processes: list[str]) -> bool:
    exe, title = foreground_process()
    return bool(title) and exe.casefold() in {v.strip().casefold() for v in allowed_processes}


def press_game_key(key: str, allowed_processes: list[str]):
    if not game_has_focus(allowed_processes):
        raise RuntimeError("Game lost focus; no key was sent")
    from .keybindings import parse_binding
    import pydirectinput
    modifiers, base = parse_binding(key)
    # No scripted mouse movement, keyboard hook evasion, or injected DLLs.
    # Hold each modifier only for the discrete spell keypress. Always release it,
    # even if pressing the key fails or foreground focus changes unexpectedly.
    held = []
    try:
        for modifier in modifiers:
            pydirectinput.keyDown(modifier)
            held.append(modifier)
        if not game_has_focus(allowed_processes):
            raise RuntimeError("Game lost focus during modifier input; spell key was not sent")
        pydirectinput.press(base)
    finally:
        for modifier in reversed(held):
            pydirectinput.keyUp(modifier)


def hold_game_key(key: str, allowed_processes: list[str], *,
                  seconds: float, cancelled=None):
    """Hold a movement key briefly; release even on focus loss or F9.

    Unlike a spell keypress, walking/turning needs a key *hold*.  The hold
    cannot continue when another app takes focus, to avoid typing into it.
    """
    from .keybindings import parse_binding
    import pydirectinput
    import time
    mods, base = parse_binding(key)
    if mods:
        raise ValueError('Movement binds must be single keys without modifiers')
    if not .05 <= seconds <= 1.5:
        raise ValueError('Movement pulse outside 0.05-1.5s safety limits')
    if not game_has_focus(allowed_processes):
        raise RuntimeError('Game lost focus; cannot move')
    if cancelled and cancelled():
        raise RuntimeError('Movement cancelled')
    pydirectinput.keyDown(base)
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                raise RuntimeError('Movement cancelled')
            if not game_has_focus(allowed_processes):
                raise RuntimeError('Game lost focus during movement; key released')
            time.sleep(min(.03, max(0.0, deadline - time.monotonic())))
    finally:
        pydirectinput.keyUp(base)
