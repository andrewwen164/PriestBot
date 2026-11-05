"""Opt-in background keyboard message transport for a visible WoW window.

Posts WM_KEYDOWN/WM_KEYUP *only* to an explicitly verified WoW HWND. Never
activates the game, sends global SendInput, hooks the game, or accesses memory.
A successful PostMessage means queued, NOT that WoW acted on the command.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys
import time
from typing import Callable

from .keybindings import parse_binding

WM_KEYDOWN = 0x100
WM_KEYUP = 0x101
WM_SYSKEYDOWN = 0x104
WM_SYSKEYUP = 0x105
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
MODIFIER_VKS = {"ctrl": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT}
SPECIAL_VKS = {
    "tab": 0x09, "esc": 0x1B, "space": 0x20, "enter": 0x0D,
    "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "home": 0x24, "end": 0x23, "pgup": 0x21,
    "pgdn": 0x22, "insert": 0x2D, "delete": 0x2E,
}
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    pid: int
    exe: str
    title: str


def virtual_key(key: str, api) -> int:
    if len(key) == 1 and (key.isalpha() and key.isascii() or key.isdigit()):
        return ord(key.upper())
    if key in SPECIAL_VKS:
        return SPECIAL_VKS[key]
    if key.startswith('f') and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        return 0x70 + int(key[1:]) - 1
    if len(key) == 1:
        mapped = api.vk_for_char(key)
        if mapped < 0 or (mapped >> 8) & 0xFF:
            raise ValueError(f"Key {key!r} needs implicit keyboard modifiers; use an explicit compatible binding")
        return mapped & 0xFF
    raise ValueError(f"No Windows virtual-key mapping for {key!r}")


def key_lparam(vk: int, api, *, is_up: bool, alt_context: bool = False) -> int:
    scan = api.scan_code(vk)
    if not scan:
        raise RuntimeError(f"No scan code for virtual key {vk}")
    return (1 | ((scan & 0xFF) << 16) |
            ((1 if vk in EXTENDED_VKS else 0) << 24) |
            ((1 if alt_context else 0) << 29) |
            ((1 if is_up else 0) << 30) |
            ((1 if is_up else 0) << 31))


def choose_game_window(allowed_processes: list[str], api=None) -> GameWindow:
    """Pin one visible, unminimized game HWND; refuse ambiguous client choices."""
    api = api or WindowsMessages()
    allowed = {name.lower().strip() for name in allowed_processes}
    candidates = [w for w in api.windows() if w.exe.casefold() in allowed and api.valid(w)]
    if not candidates:
        raise RuntimeError("No visible WoW window found. Keep the game open and unminimized.")
    foreground = api.foreground_hwnd()
    focused = [w for w in candidates if w.hwnd == foreground]
    if focused:
        return focused[0]
    if len(candidates) != 1:
        raise RuntimeError("Multiple WoW windows found. Focus the intended game window and start with F8.")
    return candidates[0]


def target_is_valid(target: GameWindow, allowed_processes: list[str], api=None) -> bool:
    api = api or WindowsMessages()
    return (target.exe.casefold() in {n.strip().casefold() for n in allowed_processes}
            and api.valid(target))


def post_game_key(binding: str, target: GameWindow, allowed_processes: list[str], *,
                  api=None, cancelled: Callable[[], bool] | None = None,
                  press_s: float = 0.045) -> None:
    """Post one chord to the pinned game window, with guaranteed release attempts.

    Does NOT use foreground input as a fallback. For testing, inject an API fake.
    """
    api = api or WindowsMessages()
    modifiers, base = parse_binding(binding)
    base_vk = virtual_key(base, api)
    held: list[int] = []
    if not target_is_valid(target, allowed_processes, api):
        raise RuntimeError("Bound WoW window was closed, hidden, minimized or changed; no key sent")

    def send(vk: int, is_up: bool, alt_down: bool):
        msg = ((WM_SYSKEYUP if is_up else WM_SYSKEYDOWN)
               if (vk == VK_MENU or alt_down) else
               (WM_KEYUP if is_up else WM_KEYDOWN))
        params = key_lparam(vk, api, is_up=is_up, alt_context=alt_down)
        api.post(target.hwnd, msg, vk, params)

    alt_down = False
    primary_down = False
    try:
        for mod in modifiers:
            if cancelled and cancelled():
                raise RuntimeError("Input cancelled before key was posted")
            if not target_is_valid(target, allowed_processes, api):
                raise RuntimeError("Bound WoW window no longer valid")
            vk = MODIFIER_VKS[mod]
            send(vk, is_up=False, alt_down=alt_down)
            held.append(vk)
            if vk == VK_MENU:
                alt_down = True
        if cancelled and cancelled():
            raise RuntimeError("Input cancelled before key was posted")
        if not target_is_valid(target, allowed_processes, api):
            raise RuntimeError("Bound WoW window no longer valid")
        send(base_vk, is_up=False, alt_down=alt_down)
        primary_down = True
        time.sleep(max(0, min(0.12, press_s)))
    finally:
        # Even if another step failed or F9 was pressed, try to release every key
        # on the same *pinned* HWND; never redirect to a different application.
        # If the HWND was destroyed/reused, posting releases would risk reaching
        # another application. Never send messages to a stale target.
        if target_is_valid(target, allowed_processes, api):
            if primary_down:
                try: send(base_vk, is_up=True, alt_down=alt_down)
                except Exception: pass
            for vk in reversed(held):
                if vk == VK_MENU:
                    alt_down = False
                try: send(vk, is_up=True, alt_down=alt_down)
                except Exception: pass


class WindowsMessages:
    """Minimal ctypes Win32 adapter, loaded lazily and only on Windows."""

    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('Background input requires Windows')
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        u = self.u
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindow.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsIconic.restype = wintypes.BOOL
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = wintypes.HWND
        u.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        u.MapVirtualKeyW.restype = wintypes.UINT
        u.VkKeyScanW.argtypes = [wintypes.WCHAR]
        u.VkKeyScanW.restype = ctypes.c_short
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.PostMessageW.restype = wintypes.BOOL
        self._enumproc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u.EnumWindows.argtypes = [self._enumproc_type, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL

    def _pid(self, hwnd):
        pid = self.wintypes.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        return pid.value

    def valid(self, target: GameWindow) -> bool:
        u = self.u
        h = target.hwnd
        if not (u.IsWindow(h) and u.IsWindowVisible(h) and not u.IsIconic(h)):
            return False
        if self._pid(h) != target.pid:
            return False
        try:
            import psutil
            if psutil.Process(target.pid).name().casefold() != target.exe.casefold():
                return False
        except (OSError, psutil.Error):
            return False
        rect = self.wintypes.RECT()
        if not u.GetWindowRect(h, self.ctypes.byref(rect)):
            return False
        return (rect.right - rect.left > 300 and rect.bottom - rect.top > 200)

    def windows(self) -> list[GameWindow]:
        import psutil
        results: list[GameWindow] = []

        def callback(hwnd, _):
            if not self.u.IsWindowVisible(hwnd) or self.u.IsIconic(hwnd):
                return True
            count = self.u.GetWindowTextLengthW(hwnd)
            if not count:
                return True
            buf = self.ctypes.create_unicode_buffer(count + 1)
            self.u.GetWindowTextW(hwnd, buf, count + 1)
            pid = self._pid(hwnd)
            try:
                exe = psutil.Process(pid).name().lower()
            except (psutil.Error, OSError):
                return True
            results.append(GameWindow(int(hwnd), pid, exe, buf.value))
            return True

        callback_c = self._enumproc_type(callback)
        if not self.u.EnumWindows(callback_c, 0):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return results

    def foreground_hwnd(self):
        return int(self.u.GetForegroundWindow() or 0)

    def vk_for_char(self, char: str) -> int:
        return int(self.u.VkKeyScanW(char))

    def scan_code(self, vk: int) -> int:
        return int(self.u.MapVirtualKeyW(vk, 0))

    def post(self, hwnd: int, message: int, vk: int, lparam: int) -> None:
        if not self.u.PostMessageW(hwnd, message, vk, lparam):
            raise self.ctypes.WinError(self.ctypes.get_last_error())


def post_game_hold(binding: str, target: GameWindow, allowed_processes: list[str],
                   *, seconds: float, api=None,
                   cancelled: Callable[[], bool] | None = None) -> None:
    """Hold a movement key on the pinned HWND, never sending global input.

    Experimental: PostMessage success does not prove the game handled the key.
    """
    api = api or WindowsMessages()
    mods, base = parse_binding(binding)
    if mods:
        raise ValueError('Movement binds must be unmodified single keys')
    if not .05 <= seconds <= 1.5:
        raise ValueError('Movement pulse outside 0.05-1.5s safety limits')
    if cancelled and cancelled():
        raise RuntimeError('Movement cancelled')
    if not target_is_valid(target, allowed_processes, api):
        raise RuntimeError('WoW window unavailable; movement not started')
    vk = virtual_key(base, api)
    api.post(target.hwnd, WM_KEYDOWN, vk, key_lparam(vk, api, is_up=False))
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                raise RuntimeError('Movement cancelled')
            if not target_is_valid(target, allowed_processes, api):
                raise RuntimeError('WoW window lost during movement')
            time.sleep(min(.03, max(0.0, deadline - time.monotonic())))
    finally:
        if target_is_valid(target, allowed_processes, api):
            api.post(target.hwnd, WM_KEYUP, vk, key_lparam(vk, api, is_up=True))
