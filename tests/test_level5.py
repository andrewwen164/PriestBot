from priestbot.config import Config
from priestbot.engine import PriestEngine, Observation


def test_level5_rotation_pain_then_smite_repeat_and_low_mana_melee():
    c = Config()
    assert c.main_damage == "smite" and not c.use_shield
    e = PriestEngine(c)
    assert e.update(Observation(1, .95, 1), 0).action == "pain"
    assert e.update(Observation(1, .85, .95), 2).action == "smite"
    assert e.update(Observation(1, .80, .8), 3).action is None
    assert e.update(Observation(1, .73, .7), 5).action == "smite"
    assert e.update(Observation(1, .25, .55), 8).action == "melee"
    assert e.update(Observation(1, .25, .45), 10).action is None


def test_level5_lesser_heal_priority():
    e = PriestEngine(Config())
    assert e.update(Observation(.43, .85, 1), 0).action == "heal"
    assert e.update(Observation(.85, .75, .9), 2).action is None
    assert e.update(Observation(.85, .75, .9), 3.2).action == "pain"


def test_shield_off_by_default_on_at_level6():
    c = Config(use_shield=True)
    e = PriestEngine(c)
    assert e.update(Observation(1, 1, 1), 0).action == "shield"
    assert e.update(Observation(1, .9, .95), 2).action == "pain"


def test_switch_to_wand_when_available():
    e = PriestEngine(Config(main_damage="wand"))
    assert e.update(Observation(1, .85, 1), 0).action == "pain"
    assert e.update(Observation(1, .8, .95), 2).action == "wand"
    assert e.update(Observation(1, .8, .88), 4).action is None


def test_mana_rest_without_water():
    e = PriestEngine(Config())
    assert e.update(Observation(1, .16, 0), 0).action is None
    assert e.update(Observation(1, .16, 0), 0).stop is False
    assert e.update(Observation(1, .35, 0), 3).action is None
    assert e.update(Observation(1, .80, 0), 4).action == "next_target"


def test_old_key_config_migrates():
    c = Config.from_dict({"keys":{"shield":"1","heal":"2","pain":"3","wand":"4","drink":"5","next_target":"tab","clear_target":"esc"}})
    assert c.keys["smite"] == "4"
    assert c.keys["wand"] == "7"
    assert c.keys["melee"] == "6"
