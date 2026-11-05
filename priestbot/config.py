from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"

@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

@dataclass
class Config:
    # Foreground process, not just title: avoids sending keystrokes to Codex.
    allowed_processes: list[str] = field(default_factory=lambda: ["wow.exe", "wowclassic.exe", "wowt.exe", "wowb.exe"])
    telemetry_source: str = "addon"  # addon default; manual remains optional
    input_mode: str = "foreground"  # foreground | background; opt-in only
    player_health: Rect | None = None
    player_mana: Rect | None = None
    target_health: Rect | None = None
    # Bind in game: 1 shield, 2 heal, 3 Pain, 4 Smite, 5 drink, 6 melee,
    # 7 wand, 8 Mind Blast, 9 Renew. Renew is opt-in until its key is verified.
    keys: dict[str, str] = field(default_factory=lambda: {
        "shield": "1", "heal": "2", "pain": "3", "smite": "4",
        "drink": "5", "melee": "6", "wand": "7", "mind_blast": "8", "renew": "9",
        "next_target": "tab", "clear_target": "esc",
        "move_forward": "w", "turn_right": "right"})
    # v0.16: opt-in, bounded motor movement (does not know enemy bearing).
    enable_movement: bool = False
    approach_pulse_s: float = 0.45   # hold W for one short pulse
    approach_max_pulses: int = 6     # max ~2.7s of forward motion per target
    turn_pulse_s: float = 0.22       # hold turn-right for one short pulse
    turn_max_pulses: int = 10        # no unlimited spinning
    movement_probe_delay_s: float = 0.25
    # The level-5 default uses Shadow Word: Pain + Smite + Lesser Heal.
    # Change main_damage to "wand" once you obtain a wand, or "melee" for auto-attacks.
    main_damage: str = "smite"  # smite | wand | mind_blast_wand | melee
    use_shield: bool = False  # train at level 6
    use_pain: bool = True
    use_heal: bool = True
    use_renew: bool = False  # opt-in: verify self-cast action-bar key first
    melee_when_oom: bool = True
    mind_blast_mana_min: float = 0.20  # skip MB opener if mana is too low
    mind_blast_cooldown_s: float = 8.0  # adjustable for Improved Mind Blast talent
    mind_blast_cast_fallback_s: float = 2.1  # cast duration + margin when events are unavailable
    mind_blast_retry_delay_s: float = 2.0
    mind_blast_max_attempts: int = 3
    smite_mana_min: float = 0.30  # don't spam Smite with almost no mana
    smite_interval_s: float = 2.7  # fallback if no successful-cast event is available
    smite_post_success_s: float = 0.20  # small margin after confirmed cast completion
    heal_below: float = 0.60  # cast Heal/Lesser Heal only at or below 60% HP
    heal_cast_fallback_s: float = 3.2  # protect slower Heal ranks if casting telemetry is unavailable
    renew_below: float = 0.80  # between pulls only; never at 90-100% HP
    renew_mana_min: float = 0.35
    renew_interval_s: float = 15.0  # conservative HoT refresh/attempt spacing
    danger_below: float = 0.18
    heal_mana_min: float = 0.16
    shield_mana_min: float = 0.25
    prepull_shield_mana_min: float = 0.50  # reserve mana for an emergency casted heal
    dot_mana_min: float = 0.34
    drink_below: float = 0.28
    resume_mana: float = 0.77
    shield_interval_s: float = 19.0
    pain_interval_s: float = 16.0
    # Aura durations are estimates ONLY when the client restricts direct reads.
    pain_duration_s: float = 18.0
    shield_duration_s: float = 30.0
    shield_lockout_s: float = 15.0  # Weakened Soul: don't repeatedly try to shield
    aura_retry_s: float = 2.6
    stuck_timeout_s: float = 13.0
    target_timeout_s: float = 38.0
    max_failed_targets: int = 12
    respawn_wait_s: float = 20.0
    max_no_target_s: float = 300.0
    max_cast_per_minute: int = 36
    action_delay_s: float = 1.7
    # v0.13: press Shoot ONCE, after Pain's global cooldown; no blind second
    # input. Name retained so existing config.json upgrades preserve tuning.
    pain_to_wand_delay_s: float = 0.0
    wand_gcd_retry_s: float = 1.6
    # Between-mob healing gets a short retry guard rather than spamming the
    # heal key every generic action interval while a cast is failing.
    between_heal_retry_s: float = 4.0
    scan_period_s: float = 0.3
    # v0.14: pause all inputs on first unreadable addon frame, then stop if
    # telemetry does not regain two consecutive clean readings within 1.5s.
    telemetry_grace_s: float = 1.5
    telemetry_recovery_frames: int = 2
    capture_monitor: int = 0  # full virtual desktop coordinates used in calibration
    enable_drink: bool = False  # off until a suitable water item is bound
    enable_autoloot: bool = False  # not supported in this stationary v1
    # v0.17: recording and training are opt-in by the owning user and persist.
    learning_record_gameplay: bool = True
    learning_record_corrections: bool = True
    learning_record_mouse: bool = True  # game-only LMB/RMB/middle/X/scroll
    learning_record_all_keys: bool = True  # opt-in demo, game-only; chat guard
    learning_auto_train: bool = True
    learning_demo_keys: dict[str, str] = field(default_factory=lambda: {
        "move_forward": "w", "turn_left": "left", "turn_right": "right",
        "move_backward": "s", "strafe_left": "q", "strafe_right": "e",
        "jump": "space", "auto_run": "num_lock"})
    dry_run: bool = True  # deliberately requires a manual checkbox before live keys

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        copy = dict(data)
        # v0.24.1: installed config.json preserves the old default across ZIP
        # upgrades. Migrate that default to the requested 60% while respecting
        # explicitly customized thresholds other than 45%.
        if copy.get('heal_below') == 0.45:
            copy['heal_below'] = 0.60
        for key in ("player_health", "player_mana", "target_health"):
            if isinstance(copy.get(key), dict):
                copy[key] = Rect(**copy[key])
        if isinstance(copy.get("keys"), dict):
            original = copy["keys"]
            copy["keys"] = dict(cls().keys)
            copy["keys"].update(original)
            # v0.10 adds Mind Blast without replacing existing custom keys.
            # Pick an unused key if the user's old layout already occupies 8.
            if "mind_blast" not in original:
                occupied = {str(v).strip().lower() for v in original.values()}
                copy["keys"]["mind_blast"] = next(
                    k for k in ("8", "9", "0", "q", "e", "r", "t", "y", "u", "b", "v", "f10", "f11", "f12")
                    if k not in occupied
                )
            # Add Renew without changing any of the user's existing bindings.
            # Keep it opt-in: an unverified action-bar slot must not be pressed.
            if "renew" not in original:
                occupied = {str(v).strip().lower() for action, v in copy["keys"].items()
                            if action != "renew"}
                choice = next((k for k in ("9", "0", "r", "t", "y", "u", "b", "v", "f10", "f11", "f12",
                                          "shift+9", "ctrl+9", "shift+r") if k not in occupied), None)
                if choice is None:
                    raise ValueError('No unused key for Renew; configure one before enabling it')
                copy["keys"]["renew"] = choice
            # New movement keys must not silently collide with an existing
            # user's customized spell bindings. They are not used unless the
            # user explicitly opts into movement.
            occupied = {str(v).strip().lower() for k,v in copy["keys"].items()
                        if k not in ("move_forward", "turn_right")}
            for kind, options in (("move_forward", ("w", "up", "i", "g", "b")),
                                  ("turn_right", ("right", "d", "l", "h", "j"))):
                if kind not in original:
                    choice = next((v for v in options if v not in occupied), None)
                    if choice is None:
                        raise ValueError(f"No unused default key for {kind}; set it manually")
                    copy["keys"][kind] = choice
                occupied.add(str(copy["keys"][kind]).lower())
            # v0.1 used key 4 for wand, but v0.2 uses key 4 for Smite.
            if "smite" not in original and original.get("wand") == "4":
                copy["keys"]["wand"] = "7"
        if isinstance(copy.get("learning_demo_keys"), dict):
            merged = dict(cls().learning_demo_keys)
            merged.update(copy["learning_demo_keys"])
            copy["learning_demo_keys"] = merged
        # Existing installations acquire movement keys without disturbing older
        # customized spell keys. Explicit conflicts are still rejected in UI.
        if copy.get("input_mode", "foreground") not in ("foreground", "background"):
            copy["input_mode"] = "foreground"  # fail safe on unknown config
        keys = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in copy.items() if k in keys})

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
