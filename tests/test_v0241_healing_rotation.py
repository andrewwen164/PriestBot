"""User-requested Priest survival rotation, tested without live game inputs."""
import pytest

from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine
from priestbot.keybindings import validate_bindings


def observation(hp=1.0, mana=1.0, target=0.0, *, shield=None, casting=None, target_exists=None):
    return Observation(hp, mana, target, casting=casting, shield_aura=shield, target_exists=target_exists)


@pytest.mark.parametrize('target', (0.0, 1.0))
def test_casted_heal_threshold_is_consistently_60_percent(target):
    cfg = Config(use_shield=False, use_renew=False)
    assert cfg.heal_below == .60
    assert PriestEngine(cfg).update(observation(.60, .90, target), 0).action == 'heal'
    assert PriestEngine(cfg).update(observation(.599, .90, target), 0).action == 'heal'
    assert PriestEngine(cfg).update(observation(.601, .90, target), 0).action != 'heal'


def test_renew_requires_opt_in_and_is_not_cast_at_90_to_100_percent():
    cfg = Config(use_renew=True, use_shield=False)
    assert Config().use_renew is False
    assert cfg.renew_below == .80
    for hp in (.80, .90, .99, 1.00):
        assert PriestEngine(cfg).update(observation(hp, .95), 0).action == 'next_target'
    assert PriestEngine(cfg).update(observation(.79, .95), 0).action == 'renew'
    assert PriestEngine(Config(use_renew=False)).update(observation(.79, .95), 0).action == 'next_target'


def test_renew_is_only_between_pulls_and_has_refresh_spacing():
    engine = PriestEngine(Config(use_renew=True, use_shield=False, main_damage='wand'))
    assert engine.update(observation(.70, .9), 0).action == 'renew'
    # It must not spam another instant Renew while the existing HoT can tick.
    assert engine.update(observation(.70, .9), 2).action == 'next_target'
    assert engine.update(observation(.70, .9, 1), 4).action == 'pain'
    assert engine.update(observation(.70, .9, 1), 6).action != 'renew'
    # A finished pull does not refresh Renew before its interval expires.
    assert engine.update(observation(.70, .9, 0, target_exists=False), 8).action == 'next_target'


def test_renew_reserves_mana_and_does_not_interrupt_casts():
    cfg = Config(use_renew=True, use_shield=False)
    assert PriestEngine(cfg).update(observation(.70, .30), 0).action == 'next_target'
    assert PriestEngine(cfg).update(observation(.70, .20), 0).action is None
    assert PriestEngine(cfg).update(observation(.70, .95, casting=True), 0).action is None


def test_casted_heal_waits_for_conservative_completion_without_cast_flag():
    cfg = Config(use_shield=False, use_renew=False)
    engine = PriestEngine(cfg)
    assert engine.update(observation(.55, .9, 1, casting=False), 0).action == 'heal'
    assert engine.update(observation(.90, .85, 1, casting=False), 1.8).action is None
    assert engine.update(observation(.90, .85, 1, casting=False), 3.2).action == 'pain'


def test_shield_prepares_next_pull_without_refreshing_active_aura():
    cfg = Config(use_shield=True, use_renew=False)
    engine = PriestEngine(cfg)
    assert engine.update(observation(1, 1), 0).action == 'shield'
    assert engine.update(observation(1, .9, shield='present'), 2).action == 'next_target'
    # Do not spend mana on pre-pull shield when reserves are needed for healing.
    assert PriestEngine(cfg).update(observation(1, .49), 0).action == 'next_target'
    assert PriestEngine(cfg).update(observation(1, .20), 0).action is None
    assert PriestEngine(Config(use_shield=False)).update(observation(1, 1), 0).action == 'next_target'


def test_preparation_does_not_repeat_during_failed_target_searches():
    engine = PriestEngine(Config(use_shield=True, use_renew=True))
    assert engine.update(observation(.72, 1), 0).action == 'renew'
    assert engine.update(observation(.72, .9), 2).action == 'shield'
    assert engine.update(observation(.72, .85), 4).action == 'next_target'
    # The bot is still trying to find an enemy. Do not cast prep buffs again.
    assert engine.update(observation(.72, .85, shield='absent'), 20).action == 'next_target'


def test_heal_then_renew_then_shield_when_both_enabled():
    engine = PriestEngine(Config(use_heal=True, use_renew=True, use_shield=True))
    assert engine.update(observation(.55, 1), 0).action == 'heal'
    assert engine.update(observation(.72, .95), 5).action == 'renew'
    assert engine.update(observation(.72, .88), 7).action == 'shield'
    assert engine.update(observation(.72, .80, shield='present'), 9).action == 'next_target'


def test_legacy_custom_keys_migrate_renew_without_overwriting_existing_binds():
    cfg = Config.from_dict({'keys': {
        'shield': '1', 'heal': '8', 'pain': '3', 'wand': '7', 'drink': '5',
        'smite': '4', 'melee': '6', 'next_target': 'tab', 'clear_target': 'esc',
    }})
    assert cfg.keys['heal'] == '8'
    assert cfg.keys['mind_blast'] == '9'
    assert cfg.keys['renew'] == '0'
    assert not cfg.use_renew
    assert validate_bindings(cfg.keys)['renew'] == '0'


def test_old_installed_heal_threshold_migrates_but_custom_threshold_survives():
    assert Config.from_dict({'heal_below': .45}).heal_below == .60
    assert Config.from_dict({'heal_below': .52}).heal_below == .52
    assert Config.from_dict({}).heal_below == .60
