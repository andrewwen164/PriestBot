"""An observed Shadow miss may retry Pain once per GCD, never infinitely."""
from priestbot.bridge import decode_bridge
from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine


def obs(*, target=1., mana=1., aura='unknown', err=None, eseq=0,
        success=None, sseq=0, tseq=0):
    return Observation(1., mana, target, False, err, eseq,
                       pain_aura=aura, success_spell=success,
                       success_seq=sseq, target_seq=tseq)


def engine():
    return PriestEngine(Config(main_damage='wand', use_pain=True,
                               use_shield=False, action_delay_s=1.7,
                               stuck_timeout_s=100, target_timeout_s=100))


def test_resisted_pain_retry_starts_at_exact_default_gcd():
    e = engine()
    assert e.update(obs(aura='unknown'), 0).action == 'pain'
    # Cast success does NOT prove that a debuff actually landed.
    r = e.update(obs(aura='estimated', err='pain_resist', eseq=1,
                     success='pain', sseq=1), .2)
    assert r.action is None
    assert e.confirmed_pain_until == float('-inf')
    assert e.update(obs(aura='estimated', err='pain_resist', eseq=1, success='pain', sseq=1), 1.49).action is None
    decision = e.update(obs(aura='estimated', err='pain_resist', eseq=1, success='pain', sseq=1), 1.5)
    assert decision.action == 'pain'
    assert 'miss/resist' in decision.reason
    # Stale error counter cannot trigger a third Pain.
    assert e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), 1.8).action is None


def test_repeated_resists_cap_recasts_and_finish_with_wand():
    e = engine()
    assert e.update(obs(), 0).action == 'pain'
    e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), .1)
    assert e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), 1.5).action == 'pain'
    e.update(obs(err='pain_resist', eseq=2, success='pain', sseq=2), 1.6)
    assert e.update(obs(err='pain_resist', eseq=2, success='pain', sseq=2), 3.0).action == 'pain'
    e.update(obs(err='pain_resist', eseq=3, success='pain', sseq=3), 3.1)
    assert e.pain_suppressed_for_target
    assert e.update(obs(err='pain_resist', eseq=3, success='pain', sseq=3), 4.5).action == 'wand'
    assert e.update(obs(err='pain_resist', eseq=3, success='pain', sseq=3), 6).action is None


def test_proven_debuff_cancels_false_resist_without_recast():
    e = engine()
    assert e.update(obs(aura='unknown'), 0).action == 'pain'
    e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), .2)
    assert e.update(obs(err='pain_resist', eseq=1, aura='present'), 1.5).action == 'wand'


def test_ignored_stale_resist_and_target_change():
    e = engine()
    assert e.update(obs(aura='unknown'), 0).action == 'pain'
    # After the correlation window, do not infer this target's Pain missed.
    assert e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), 2.0).action == 'wand'
    assert e.pain_retry_pending is False
    assert e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), 2.1).action is None
    e.update(obs(target=0, tseq=1), 3)
    assert not e.pain_retry_pending and not e.pain_suppressed_for_target


def test_low_mana_does_not_stall_or_retry_pain():
    e = engine()
    assert e.update(obs(), 0).action == 'pain'
    e.update(obs(err='pain_resist', eseq=1, success='pain', sseq=1), .1)
    r = e.update(obs(mana=.1, err='pain_resist', eseq=1), 1.5)
    assert r.action == 'wand'
    assert e.pain_suppressed_for_target


def test_existing_config_default_gcd_migrates():
    assert Config().wand_gcd_retry_s == 1.5
    assert Config.from_dict({'wand_gcd_retry_s':1.6}).wand_gcd_retry_s == 1.5
    assert Config.from_dict({'wand_gcd_retry_s':1.7}).wand_gcd_retry_s == 1.7


def test_decoder_recognizes_new_yellow_pain_resist_signal():
    from test_spell_signals import status_panel
    panel = status_panel()
    panel[40:50, 55+76:55+86] = (255, 255, 0)
    assert decode_bridge(panel).observation.error == 'pain_resist'

