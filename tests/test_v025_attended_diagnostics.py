"""v0.25 attended farming: no-blind-chase decisions + uploadable reports."""
import json
from zipfile import ZipFile

from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine
from priestbot.diagnostics import generate_report, run_decision_tests, run_telemetry_tests


def state(target=.3, hp=1, mana=1, error=None, seq=0, target_seq=0):
    return Observation(hp, mana, target, False, error, seq, target_seq=target_seq)


def attended(**extra):
    return PriestEngine(Config(main_damage='smite', use_pain=False,
                               enable_stationary_tracking=True, **extra))


def test_stationary_flee_turn_and_stale_event_not_repeated():
    e = attended()
    assert e.update(state(), 0).action == 'smite'
    assert e.update(state(error='facing', seq=1), .3).action is None
    assert e.update(state(error='facing', seq=1), 2).action == 'turn_right'
    assert e.turn_pulses == 1
    assert e.update(state(error='facing', seq=1), 2.5).action is None
    assert e.turn_pulses == 1


def test_no_flee_turn_on_healthy_target_or_unreliable_semantics():
    e = attended()
    assert e.update(state(target=.8), 0).action == 'smite'
    assert e.update(state(target=.8, error='facing', seq=1), .3).action == 'clear_target'
    e = attended()
    e.update(state(target=.3), 0)
    unknown = Observation(1, 1, .3, False, 'facing', 1, target_seq=None)
    assert e.update(unknown, .3).action == 'clear_target'


def test_stationary_never_walks_even_with_old_approach_enabled_on_flee():
    e = attended(enable_movement=True)
    e.update(state(), 0)
    assert e.update(state(error='range', seq=1), .3).action == 'clear_target'
    assert e.approach_pulses == 0


def test_bounded_turns_stop_and_clear_target():
    e = attended(turn_max_pulses=1)
    e.update(state(), 0)
    e.update(state(error='facing', seq=1), .3)
    assert e.update(state(error='facing', seq=1), 2).action == 'turn_right'
    decision = e.update(state(error='facing', seq=2), 2.7)
    assert decision.action == 'clear_target'
    assert 'limit' in decision.reason.lower()


def test_los_suppresses_inputs_and_expires_without_pursuit():
    e = attended(los_wait_s=4)
    assert e.update(state(), 0).action == 'smite'
    assert e.update(state(error='los', seq=1), .3).action is None
    assert e.update(state(error='los', seq=1), 1).action is None
    assert e.update(state(error='los', seq=1), 2.31).action == 'smite'
    decision = e.update(state(error='los', seq=1), 4.31)
    assert decision.action == 'clear_target'
    assert 'no pursuit' in decision.reason.lower()
    assert e.approach_pulses == 0


def test_waiting_for_los_never_blocks_urgent_self_healing():
    e = attended(los_wait_s=8)
    e.update(state(), 0)
    e.update(state(error='los', seq=1), .3)
    decision = e.update(state(hp=.52, error='los', seq=1), 2.0)
    assert decision.action == 'heal'
    assert 'healing' in decision.reason.lower()


def test_los_resets_on_damage_progress_or_target_change():
    e = attended()
    e.update(state(), 0)
    e.update(state(error='los', seq=1), .3)
    assert e.los_blocked_since == .3
    e.update(state(target=.25, error='los', seq=1), 1)
    assert e.los_blocked_since is None
    e.update(state(error='los', seq=2), 2)
    assert e.los_blocked_since == 2
    e.update(state(target_seq=1, target=.9), 2.2)
    assert e.los_blocked_since is None


def test_repeated_los_failures_capped_without_loops():
    e = attended(los_max_retries=1)
    e.update(state(), 0)
    e.update(state(error='los', seq=1), .3)
    e.update(state(error='los', seq=1), 2.31)
    result = e.update(state(error='los', seq=2), 2.7)
    assert result.action == 'clear_target'
    assert 'line of sight' in result.reason.lower()


def test_config_is_opt_in_and_backward_compatible():
    old = Config.from_dict({'keys': {'shield': 'shift+e'}, 'enable_movement': False})
    assert old.enable_stationary_tracking is False
    assert old.flee_target_hp_below == .40
    assert old.keys['shield'] == 'shift+e'


def test_self_contained_offline_report_and_private_zip(tmp_path):
    assert all(r['passed'] for r in run_decision_tests())
    assert all(r['passed'] for r in run_telemetry_tests())
    path = generate_report(tmp_path)
    assert path.suffix == '.zip'
    with ZipFile(path) as z:
        assert set(z.namelist()) == {'report.md', 'report.json'}
        doc = z.read('report.md').decode('utf-8')
        report = json.loads(z.read('report.json'))
    assert report['summary']['failed'] == 0
    assert report['summary']['total'] >= 14
    assert report['live_telemetry'] is None
    assert 'fleeing' in doc.lower() and 'line of sight' in doc.lower()
    assert str(tmp_path) not in doc
    assert 'screenshots' in doc and 'upload' in doc.lower()
