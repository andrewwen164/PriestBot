"""Normalize and validate WoW spell/action keybindings.

Accept individual keys and simple modifier chords (e.g. shift+e). An action
always generates one discrete keypress, never an automatic held-key repeat.
"""
from __future__ import annotations
import re

ACTION_LABELS = {
    "shield": "Power Word: Shield",
    "heal": "Heal / Lesser Heal",
    "renew": "Renew (self-cast HoT)",
    "pain": "Shadow Word: Pain",
    "smite": "Smite",
    "mind_blast": "Mind Blast (opener)",
    "wand": "Shoot (wand)",
    "melee": "Melee / Start Attack",
    "drink": "Drink water",
    "next_target": "Target next enemy",
    "clear_target": "Clear target",
    "move_forward": "Walk forward (hold)",
    "turn_right": "Turn right (hold)",
}

RESERVED = {"f6", "f7", "f8", "f9"}
MODIFIERS = ("ctrl", "alt", "shift")  # consistent order for normalized config + key down
MODIFIER_ALIASES = {"control": "ctrl", "ctl": "ctrl", "option": "alt"}
SINGLE_KEYS = (
    set("abcdefghijklmnopqrstuvwxyz0123456789")
    | {"tab", "esc", "space", "enter", "backspace", "up", "down", "left", "right", "home", "end",
       "pgup", "pgdn", "insert", "delete", "num_lock", "caps_lock", "scroll_lock", "-", "=", "[", "]", ";", "'", ",", ".", "/", "\\"}
    | {f"f{i}" for i in range(1, 13)}
)
# Prevent OS shortcuts accidentally closing the game or switching focus.
UNSAFE = {"alt+f4", "alt+tab", "ctrl+shift+esc", "ctrl+alt+delete"}


def parse_binding(binding: str) -> tuple[tuple[str, ...], str]:
    """Return (modifiers, base key) in canonical order, or reject invalid chords."""
    raw = str(binding).strip().lower()
    # Accept user's 'shift - e' notation, as well as conventional 'shift+e'.
    raw = re.sub(r"(?<=\w)\s*-\s*(?=\w)", "+", raw)
    parts = [p.strip() for p in raw.split("+")]
    if not parts or any(not p for p in parts):
        raise ValueError(f"Invalid keybinding {binding!r}; use e.g. 'shift+e' or '3'.")
    parts = [MODIFIER_ALIASES.get(p, p) for p in parts]
    base = parts[-1]
    mods = parts[:-1]
    if base not in SINGLE_KEYS:
        raise ValueError(f"Invalid keybinding {binding!r}; base key must be a supported key (e.g. e, 3, tab).")
    if any(m not in MODIFIERS for m in mods) or len(mods) != len(set(mods)):
        raise ValueError(f"Invalid keybinding {binding!r}; modifiers may be ctrl, alt, shift (each once).")
    canonical = tuple(m for m in MODIFIERS if m in mods)
    if base in RESERVED:
        raise ValueError(f"{base.upper()} is reserved for bot controls, including modifier combinations.")
    if "+".join((*canonical, base)) in UNSAFE:
        raise ValueError(f"{binding!r} is a protected system shortcut; choose another key.")
    return canonical, base


def normalize_binding(binding: str) -> str:
    mods, base = parse_binding(binding)
    return "+".join((*mods, base))


def validate_bindings(bindings: dict[str, str]) -> dict[str, str]:
    """Normalize and validate each binding; reject collisions and reserved shortcuts."""
    expected = set(ACTION_LABELS)
    if set(bindings) != expected:
        raise ValueError("Bindings must include exactly: " + ", ".join(ACTION_LABELS))
    result: dict[str, str] = {}
    seen: dict[str, str] = {}
    for action in ACTION_LABELS:
        try:
            key = normalize_binding(bindings[action])
        except ValueError as exc:
            raise ValueError(f"Invalid key for {ACTION_LABELS[action]}: {exc}") from exc
        if key in seen:
            raise ValueError(f"'{key}' is assigned to both {seen[key]} and {ACTION_LABELS[action]}. Give each action a unique key.")
        seen[key] = ACTION_LABELS[action]
        result[action] = key
    return result
