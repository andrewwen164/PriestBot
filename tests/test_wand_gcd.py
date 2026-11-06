"""v0.13: one Shoot activation after Pain's GCD (no blind retry)."""
from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine


def o(hp=1, mana=.85, target=1, **kwargs):
    return Observation(hp, mana, target, **kwargs)


def test_single_wand_press_after_gcd_and_no_repeat():
    e = PriestEngine(Config(main_damage="wand", use_shield=False))
    assert e.update(o(), 0).action == "pain"
    assert e.wand_start_at == 1.5
    for t in (.3, 1.2, 1.49):
        assert e.update(o(), t).action is None
    r = e.update(o(), 1.6)
    assert r.action == "wand" and "GCD" in r.reason
    assert e.wand_start_at is None
    for t in (1.9, 3.4, 4.2, 6.0):
        assert e.update(o(target=.75), t).action != "wand"


def test_pain_confirmed_does_not_cause_second_wand_press():
    e = PriestEngine(Config(main_damage="wand", use_shield=False))
    assert e.update(o(success_spell=None, success_seq=0), 0).action == 'pain'
    assert e.update(o(success_spell='pain', success_seq=1), .3).action is None
    assert e.update(o(success_spell='pain', success_seq=1), 1.6).action == 'wand'
    assert e.update(o(success_spell='pain', success_seq=1), 3.2).action is None


def test_healing_cancels_pending_wand_start():
    e = PriestEngine(Config(main_damage="wand", use_shield=False))
    assert e.update(o(), 0).action == 'pain'
    assert e.update(o(hp=.4), .3).action == 'heal'
    assert e.wand_start_at is None
    assert e.update(o(hp=.9,target=.8), 2.1).action is None
    assert e.update(o(hp=.9,target=.8), 3.6).action == 'wand'


def test_target_change_cancels_pending_wand_start():
    e = PriestEngine(Config(main_damage="wand", use_shield=False))
    assert e.update(o(), 0).action == 'pain'
    assert e.update(o(target=0), .6).action == 'next_target'
    assert e.wand_start_at is None
    assert e.update(o(target=0), 2.3).action == 'next_target'
    assert e.update(o(target=1), 4.0).action == 'pain'
    assert e.update(o(target=1), 4.3).action is None
    assert e.update(o(target=1), 5.6).action == 'wand'


def test_between_mob_heal_guard():
    c = Config(use_shield=False, main_damage='wand')
    e = PriestEngine(c)
    assert e.update(o(hp=.55,target=0), 0).action == 'heal'
    assert e.update(o(hp=.55,target=0), 1.7).action is None
    assert e.update(o(hp=.55,target=0), 3).action is None
    assert e.update(o(hp=.55,target=0), 4).action == 'heal'


def test_smite_mode_keeps_existing_general_delay():
    e = PriestEngine(Config(main_damage="smite"))
    obs = o()
    assert e.update(obs, 0).action == "pain"
    assert e.update(obs, .3).action is None
    assert e.update(obs, 1.7).action == "smite"
