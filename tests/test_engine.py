from priestbot.engine import PriestEngine,Observation
from priestbot.config import Config


def test_combat_rotation_and_kill():
    c=Config(main_damage="wand", use_shield=True)
    e=PriestEngine(c)
    assert e.update(Observation(1,.95,0),0).action=="shield"  # new pre-pull policy
    assert e.update(Observation(1,.95,1),2).action=="pain"
    assert e.update(Observation(1,.80,1),4).action=="wand"
    assert e.update(Observation(1,.70,.95),6).action is None
    assert e.update(Observation(1,.70,.8),8).action is None
    assert e.update(Observation(.4,.70,.65),10).action=="heal"
    assert e.update(Observation(.8,.60,.55),12).action is None
    assert e.update(Observation(.8,.60,.55),13.3).action=="wand"
    assert e.update(Observation(.8,.60,0, target_dead=True),16).action=="next_target"


def test_low_mana_rests_without_drinking():
    e=PriestEngine(Config())
    r=e.update(Observation(.9,.17,0),0)
    assert not r.stop and r.action is None and "mana" in r.reason.lower()


def test_drinking_enabled():
    c=Config(enable_drink=True)
    e=PriestEngine(c)
    assert e.update(Observation(1,.18,0),0).action=="drink"
    assert e.update(Observation(1,.60,0),2).action is None
    assert e.update(Observation(1,.80,0),26).action=="next_target"


def test_health_emergency():
    e=PriestEngine(Config())
    assert e.update(Observation(.1,.05,0),0).stop


def test_stuck_target_skips():
    c=Config(stuck_timeout_s=9, main_damage="wand", use_shield=True)
    e=PriestEngine(c)
    assert e.update(Observation(1,1,1),0).action=="shield"
    assert e.update(Observation(1,.9,1),2).action=="pain"
    assert e.update(Observation(1,.8,1),4).action=="wand"
    assert e.update(Observation(1,.8,1),11).action=="clear_target"


def test_shield_recast_interval():
    e=PriestEngine(Config(main_damage="wand", use_shield=True))
    e.update(Observation(1,1,1),0)
    e.update(Observation(1,.9,.95),2)
    e.update(Observation(1,.8,.90),4)
    # After shield 19s, should refresh; target HP progresses.
    assert e.update(Observation(.8,.6,.70),20).action=="shield"


def test_wait_for_respawns_and_retry():
    c=Config(max_failed_targets=2, respawn_wait_s=20, max_no_target_s=300)
    e=PriestEngine(c)
    assert e.update(Observation(1,1,0),0).action=="next_target"
    assert e.update(Observation(1,1,0),2).action=="next_target"
    assert e.update(Observation(1,1,0),4).action is None
    assert e.update(Observation(1,1,0),20).action is None
    assert e.update(Observation(1,1,0),25).action=="next_target"
    assert e.update(Observation(1,1,0),301).stop


def test_low_hp_target_is_not_abandoned():
    """Even 0.001% optical HP is still a living target."""
    e = PriestEngine(Config(main_damage="wand", use_shield=False, use_pain=False))
    assert e.update(Observation(1, 1, 1), 0).action == "wand"
    assert e.update(Observation(1, 1, 0.00001), 2).action is None
    assert e.update(Observation(1, 1, 0.00000001), 4).action is None


def test_zero_optical_hp_during_fight_fails_closed():
    e = PriestEngine(Config(main_damage="wand", use_shield=False, use_pain=False))
    assert e.update(Observation(1, 1, 1), 0).action == "wand"
    uncertain = e.update(Observation(1, 1, 0), 2)
    assert uncertain.action is None and not uncertain.stop
    timed_out = e.update(Observation(1, 1, 0), 4.1)
    assert timed_out.stop and timed_out.action is None


def test_explicit_alive_signal_overrides_rounded_zero_hp():
    e = PriestEngine(Config(main_damage="wand", use_shield=False, use_pain=False))
    assert e.update(Observation(1, 1, 1), 0).action == "wand"
    result = e.update(Observation(1, 1, 0, target_exists=True, target_dead=False), 2)
    assert not result.stop and result.action != "next_target"
