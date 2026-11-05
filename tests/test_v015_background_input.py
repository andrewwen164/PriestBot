"""Background input posts only to an authenticated WoW window; no global input."""
from pathlib import Path
import pytest
from priestbot.config import Config
from priestbot.background_input import (
    GameWindow, choose_game_window, target_is_valid, post_game_key,
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    VK_MENU, VK_SHIFT, key_lparam, virtual_key,
)


class FakeWindows:
    def __init__(self, windows=None, foreground=0):
        self.game = GameWindow(0xDEADBEAF, 124, 'wow.exe', 'World of Warcraft')
        self.windows_present = [self.game] if windows is None else windows
        self.focus = foreground
        self.valid_hwnds = {w.hwnd for w in self.windows_present}
        self.posts = []
        self.raise_on_post = None

    def windows(self):
        return self.windows_present

    def valid(self, w):
        return w.hwnd in self.valid_hwnds and w in self.windows_present

    def foreground_hwnd(self):
        return self.focus

    def scan_code(self, vk):
        return vk & 0xFF

    def vk_for_char(self, char):
        return {'-': 0xBD, '=': 0xBB, ';': 0xBA, '[': 0xDB}.get(char, -1)

    def post(self, hwnd, msg, vk, lparam):
        if self.raise_on_post == len(self.posts):
            self.raise_on_post = None  # transient failure; permit release
            raise OSError('posting rejected')
        self.posts.append((hwnd, msg, vk, lparam))


def test_target_selection_visible_nonfocused():
    api = FakeWindows(foreground=73)
    assert choose_game_window(['wow.exe'], api) == api.game


def test_wrong_process_never_selected():
    api = FakeWindows(foreground=73)
    with pytest.raises(RuntimeError, match='No visible'):
        choose_game_window(['firefox.exe'], api)


def test_ambiguous_game_windows_refused_when_browser_focused():
    api = FakeWindows(windows=[GameWindow(1, 124, 'wow.exe', 'WoW 1'), GameWindow(2, 125, 'wow.exe', 'WoW 2')], foreground=777)
    with pytest.raises(RuntimeError, match='Multiple WoW'):
        choose_game_window(['wow.exe'], api)
    api.focus = 2
    assert choose_game_window(['wow.exe'], api).hwnd == 2


def test_target_lost_prevents_any_input():
    api = FakeWindows()
    w = api.game
    api.valid_hwnds.clear()
    with pytest.raises(RuntimeError, match='Bound WoW window'):
        post_game_key('8', w, ['wow.exe'], api=api, press_s=0)
    assert not api.posts


def test_wrong_allowlist_prevents_any_input():
    api = FakeWindows()
    with pytest.raises(RuntimeError):
        post_game_key('8', api.game, ['notepad.exe'], api=api)
    assert not api.posts


def test_foreground_app_untouched_even_when_browser_focused():
    api = FakeWindows(foreground=98765)
    post_game_key('tab', api.game, ['wow.exe'], api=api, press_s=0)
    assert [(m, vk) for _, m, vk, _ in api.posts] == [(WM_KEYDOWN, 0x9), (WM_KEYUP, 0x9)]
    assert all(hwnd == api.game.hwnd for hwnd, _, _, _ in api.posts)
    assert api.foreground_hwnd() == 98765


def test_shift_e_down_and_up_order():
    api = FakeWindows()
    post_game_key('shift+e', api.game, ['wow.exe'], api=api, press_s=0)
    assert [(m, vk) for _, m, vk, _ in api.posts] == [
        (WM_KEYDOWN, VK_SHIFT), (WM_KEYDOWN, ord('E')),
        (WM_KEYUP, ord('E')), (WM_KEYUP, VK_SHIFT),
    ]
    assert api.posts[1][3] & (0x3 << 30) == 0
    assert api.posts[2][3] & (0x3 << 30) == 0x3 << 30


def test_alt_q_uses_system_key_messages():
    api = FakeWindows()
    post_game_key('alt+q', api.game, ['wow.exe'], api=api, press_s=0)
    assert [(m, vk) for _, m, vk, _ in api.posts] == [
        (WM_SYSKEYDOWN, VK_MENU), (WM_SYSKEYDOWN, ord('Q')),
        (WM_SYSKEYUP, ord('Q')), (WM_SYSKEYUP, VK_MENU),
    ]


def test_ctrl_shift_r_release_reverse_order():
    api = FakeWindows()
    post_game_key('ctrl+shift+r', api.game, ['wow.exe'], api=api, press_s=0)
    assert [m[2] for m in api.posts] == [0x11, 0x10, ord('R'), ord('R'), 0x10, 0x11]


def test_failure_after_modifier_attempts_modifier_release():
    api = FakeWindows()
    api.raise_on_post = 1
    with pytest.raises(OSError):
        post_game_key('shift+e', api.game, ['wow.exe'], api=api, press_s=0)
    assert api.posts[0][2] == VK_SHIFT
    assert api.posts[1][1] == WM_KEYUP and api.posts[1][2] == VK_SHIFT


def test_cancellation_sends_no_keys():
    api = FakeWindows()
    with pytest.raises(RuntimeError, match='cancelled'):
        post_game_key('8', api.game, ['wow.exe'], api=api, cancelled=lambda: True)
    assert not api.posts


def test_config_migration_defaults_safe_foreground(tmp_path: Path):
    cfg = Config.from_dict({'telemetry_source': 'addon', 'main_damage': 'mind_blast_wand'})
    assert cfg.input_mode == 'foreground'
    cfg.input_mode = 'background'
    cfg.keys['shield'] = 'shift+e'
    cfg.save(tmp_path/'config.json')
    loaded = Config.load(tmp_path/'config.json')
    assert loaded.input_mode == 'background'
    assert loaded.keys['shield'] == 'shift+e'
    assert Config.from_dict({'input_mode': 'garbage'}).input_mode == 'foreground'


@pytest.mark.parametrize('name, vk', [('1',49), ('a',65), ('f12',0x7B), ('tab',9), ('esc',0x1B), ('-',0xBD)])
def test_key_conversion(name,vk):
    assert virtual_key(name, FakeWindows()) == vk
