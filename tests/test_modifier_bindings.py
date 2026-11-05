"""Ensure the bot sends single discrete chord inputs and releases modifiers."""
import sys
import types
from pathlib import Path
from unittest.mock import Mock
import pytest

from priestbot.config import Config
from priestbot.keybindings import normalize_binding, parse_binding, validate_bindings
from priestbot import input_control


def test_shift_e_spell_key_persists(tmp_path: Path):
    cfg = Config()
    cfg.keys = validate_bindings({**cfg.keys, "shield": "Shift - E"})
    assert cfg.keys["shield"] == "shift+e"
    cfg.save(tmp_path / "config.json")
    loaded = Config.load(tmp_path / "config.json")
    assert loaded.keys["shield"] == "shift+e"


@pytest.mark.parametrize("original,normal", [
    ("SHIFT+E", "shift+e"), ("shift - e", "shift+e"),
    ("Control+1", "ctrl+1"), ("alt+q", "alt+q"),
    ("Shift+CTRL+r", "ctrl+shift+r"), ("7", "7"),
])
def test_canonical_modifiers(original, normal):
    assert normalize_binding(original) == normal


def test_same_chord_rejected_even_with_modifier_order_changed():
    cfg = Config().keys
    with pytest.raises(ValueError, match="both"):
        validate_bindings({**cfg, "shield": "shift+ctrl+r", "heal": "ctrl+shift+r"})


@pytest.mark.parametrize("chord", ["shift+f8", "ctrl+f9", "shift+shift+e", "e+q", "alt+tab", "alt+f4", "ctrl+shift+esc", "ctrl+alt+delete", "win+q", "shift+"])
def test_invalid_or_reserved(chord):
    with pytest.raises(ValueError):
        parse_binding(chord)


def test_holds_and_releases_shift_for_one_press(monkeypatch):
    events = []
    mock = types.SimpleNamespace(
        keyDown=lambda x: events.append(("down", x)),
        press=lambda x: events.append(("press", x)),
        keyUp=lambda x: events.append(("up", x)),
    )
    monkeypatch.setitem(sys.modules, "pydirectinput", mock)
    monkeypatch.setattr(input_control, "game_has_focus", lambda _: True)
    input_control.press_game_key("shift+e", ["wow.exe"])
    assert events == [("down", "shift"), ("press", "e"), ("up", "shift")]


def test_multi_modifier_reversed_release(monkeypatch):
    events = []
    mock = types.SimpleNamespace(
        keyDown=lambda x: events.append(("down", x)),
        press=lambda x: events.append(("press", x)),
        keyUp=lambda x: events.append(("up", x)),
    )
    monkeypatch.setitem(sys.modules, "pydirectinput", mock)
    monkeypatch.setattr(input_control, "game_has_focus", lambda _: True)
    input_control.press_game_key("shift+ctrl+r", ["wow.exe"])
    assert events == [("down", "ctrl"), ("down", "shift"), ("press", "r"), ("up", "shift"), ("up", "ctrl")]


def test_release_modifier_on_exception(monkeypatch):
    events = []
    def broken_press(x):
        events.append(("press", x))
        raise OSError("simulated keyboard failure")
    mock = types.SimpleNamespace(
        keyDown=lambda x: events.append(("down", x)),
        press=broken_press,
        keyUp=lambda x: events.append(("up", x)),
    )
    monkeypatch.setitem(sys.modules, "pydirectinput", mock)
    monkeypatch.setattr(input_control, "game_has_focus", lambda _: True)
    with pytest.raises(OSError, match="simulated"):
        input_control.press_game_key("shift+e", ["wow.exe"])
    assert events == [("down", "shift"), ("press", "e"), ("up", "shift")]


def test_no_game_focus_sends_nothing(monkeypatch):
    mock = types.SimpleNamespace(keyDown=Mock(), press=Mock(), keyUp=Mock())
    monkeypatch.setitem(sys.modules, "pydirectinput", mock)
    monkeypatch.setattr(input_control, "game_has_focus", lambda _: False)
    with pytest.raises(RuntimeError, match="lost focus"):
        input_control.press_game_key("shift+e", ["wow.exe"])
    mock.keyDown.assert_not_called()
    mock.press.assert_not_called()


def test_focus_loss_between_down_and_press_releases(monkeypatch):
    events = []
    mock = types.SimpleNamespace(
        keyDown=lambda x: events.append(("down", x)),
        press=lambda x: events.append(("press", x)),
        keyUp=lambda x: events.append(("up", x)),
    )
    monkeypatch.setitem(sys.modules, "pydirectinput", mock)
    checks = iter((True, False))
    monkeypatch.setattr(input_control, "game_has_focus", lambda _: next(checks))
    with pytest.raises(RuntimeError, match="during modifier"):
        input_control.press_game_key("shift+e", ["wow.exe"])
    assert events == [("down", "shift"), ("up", "shift")]
