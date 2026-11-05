from pathlib import Path
import pytest
from priestbot.config import Config
from priestbot.keybindings import validate_bindings


def test_custom_spell_and_target_keys_saved_and_loaded(tmp_path: Path):
    cfg = Config()
    edits = dict(cfg.keys, smite="q", pain="e", heal="r", wand="f2", next_target="t")
    cfg.keys = validate_bindings(edits)
    cfg.save(tmp_path / "config.json")
    loaded = Config.load(tmp_path / "config.json")
    assert loaded.keys["smite"] == "q"
    assert loaded.keys["pain"] == "e"
    assert loaded.keys["wand"] == "f2"
    assert loaded.keys["next_target"] == "t"


def test_reserves_hotkeys_and_rejects_collisions():
    defaults = Config().keys
    with pytest.raises(ValueError, match="reserved"):
        validate_bindings({**defaults,"smite":"f8"})
    with pytest.raises(ValueError, match="both"):
        validate_bindings({**defaults,"smite":"3"})
    with pytest.raises(ValueError, match="reserved"):
        validate_bindings({**defaults, "smite": "shift+f8"})
