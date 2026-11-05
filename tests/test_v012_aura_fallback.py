"""Regression cases: Forever secret aura lookups can return nil during combat."""
from priestbot.config import Config
from priestbot.engine import PriestEngine, Observation
from pathlib import Path


def obs(*, target=1., pain='absent', shield='absent', success=None, seq=0, tseq=0):
    return Observation(1., 1., target, False, None, 0, shield, pain, success, seq, tseq)


def test_pain_success_is_not_overridden_by_false_absence():
    cfg = Config(use_shield=False, main_damage='wand', stuck_timeout_s=100, target_timeout_s=100)
    e = PriestEngine(cfg)
    assert e.update(obs(),0).action == 'pain'
    e.update(obs(success='pain',seq=1),.3)
    # False "absent" readings must not cause reattempts every 2.6 seconds.
    for t in (3,5,9,12,17):
        assert e.update(obs(seq=1),t).action != 'pain', t
    assert e.update(obs(seq=1),19).action == 'pain'


def test_shield_success_unknown_uses_timer():
    cfg = Config(use_shield=True, use_pain=False, main_damage='wand',
                 stuck_timeout_s=100, target_timeout_s=100)
    e = PriestEngine(cfg)
    assert e.update(obs(),0).action == 'shield'
    e.update(obs(shield='unknown',success='shield',seq=1),.3)
    for t in (4,16,21):
        assert e.update(obs(shield='unknown',seq=1),t).action != 'shield', t
    assert e.update(obs(shield='unknown',seq=1),31).action == 'shield'


def test_target_change_discards_old_pain_estimate():
    cfg = Config(use_shield=False, main_damage='wand', stuck_timeout_s=100,target_timeout_s=100)
    e = PriestEngine(cfg)
    e.update(obs(),0)
    e.update(obs(success='pain',seq=1),.3)
    assert e.update(obs(seq=1,tseq=1),3).action == 'pain'


def test_lua_does_not_claim_nil_is_absent():
    lua = (Path(__file__).resolve().parents[1]/'addons'/'PriestBridge'/'PriestBridge.lua').read_text()
    assert "if name == nil then return 'unknown' end" in lua
    assert "if name == nil then return 'absent' end" not in lua


def test_new_install_defaults_to_addon_without_overriding_saved_manual():
    assert Config().telemetry_source == 'addon'
    assert Config.from_dict({'telemetry_source':'manual'}).telemetry_source == 'manual'
