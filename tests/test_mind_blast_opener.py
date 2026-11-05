"""Mind Blast -> Pain -> Shoot, plus fallbacks and addon signaling."""
import pytest

from priestbot.config import Config
from priestbot.engine import Observation, PriestEngine
from priestbot.bridge import decode_bridge
from priestbot.keybindings import validate_bindings
from test_v08_aura_success import panel_v08


def obs(*, hp=1, mana=1, target=1, casting=False, success=None, sseq=0,
        tseq=0, err=None, eseq=0, pain='absent'):
    return Observation(hp, mana, target, casting, err, eseq,
                       None, pain, success, sseq, tseq)


def engine(**overrides):
    return PriestEngine(Config(main_damage='mind_blast_wand', use_shield=False,
                               stuck_timeout_s=100, target_timeout_s=100,
                               **overrides))


def test_strict_opening_and_no_artificial_spell_gaps():
    e = engine()
    assert e.update(obs(), 0).action == 'mind_blast'
    assert e.update(obs(casting=True), .3).action is None
    assert e.update(obs(casting=True), 1.2).action is None
    # The client confirms MB succeeded: Pain is next with no 1.7s gap.
    r = e.update(obs(success='mind_blast', sseq=1), 1.5)
    assert r.action == 'pain'
    assert e.update(obs(success='mind_blast', sseq=1), 1.8).action is None
    assert e.update(obs(success='mind_blast', sseq=1), 2.9).action is None
    assert e.update(obs(success='pain', sseq=2, pain='estimated'), 3.1).action == 'wand'
    assert e.update(obs(success='pain', sseq=2, pain='estimated'), 4).action is None


def test_mind_blast_only_once_per_target_and_pain_refresh_keeps_wand():
    e = engine()
    assert e.update(obs(), 0).action == 'mind_blast'
    assert e.update(obs(success='mind_blast', sseq=1), 1.6).action == 'pain'
    assert e.update(obs(success='pain', sseq=2, pain='estimated'), 1.9).action is None
    assert e.update(obs(success='pain', sseq=2, pain='estimated'), 3.2).action == 'wand'
    e.update(obs(success='pain', sseq=2, pain='estimated'), 3.5)
    assert e.update(obs(target=.65, pain='present', success='pain', sseq=2), 6).action is None
    assert e.mb_opener_state == 'done'
    assert e.mb_attempts == 1


def test_new_target_opener_respects_previous_cooldown():
    e = engine()
    assert e.update(obs(tseq=0), 0).action == 'mind_blast'
    assert e.update(obs(success='mind_blast', sseq=1), 1.5).action == 'pain'
    assert e.update(obs(success='pain', sseq=2), 1.8).action is None
    assert e.update(obs(success='pain', sseq=2), 3.1).action == 'wand'
    # Death / new target; two distinct targets can each have full HP.
    e.update(obs(target=0, tseq=1, sseq=2), 3.4)
    r=e.update(obs(target=1, tseq=2, sseq=2), 4.8)
    assert r.action is None and 'cooldown' in r.reason
    r=e.update(obs(target=1, tseq=2, sseq=2), 9.6)
    assert r.action == 'mind_blast'


def test_fallback_without_confirmed_cast_event_waits_for_cast_duration():
    e = engine()
    assert e.update(obs(sseq=None), 0).action == 'mind_blast'
    assert e.update(obs(sseq=None), 1.6).action is None
    assert e.update(obs(sseq=None), 2.1).action == 'pain'
    assert e.update(obs(sseq=None), 2.4).action is None
    assert e.update(obs(sseq=None), 3.7).action == 'wand'


def test_failure_retries_mind_blast_before_pain_and_stops_after_limit():
    e = engine()
    assert e.update(obs(), 0).action == 'mind_blast'
    assert e.update(obs(err='failed', eseq=1), .3).action is None
    assert e.update(obs(eseq=1), 1.7).action is None
    assert e.update(obs(eseq=1), 2.3).action == 'mind_blast'
    assert e.update(obs(err='failed', eseq=2), 2.6).action is None
    assert e.update(obs(eseq=2), 4.6).action == 'mind_blast'
    assert e.update(obs(err='failed', eseq=3), 4.9).action == 'clear_target'
    assert e.mb_opener_state == 'pending'


def test_low_mana_skips_mind_blast_without_blocking_wand():
    e = engine()
    # Pain costs more mana in config, so both offensive casts are skipped.
    assert e.update(obs(mana=.12), 0).action == 'wand'


def test_healing_overrides_casting_and_does_not_repeat_mind_blast():
    e=engine()
    assert e.update(obs(),0).action=='mind_blast'
    e.update(obs(success='mind_blast',sseq=1),1.5)
    assert e.update(obs(hp=.35,success='mind_blast',sseq=1),1.8).action=='heal'
    assert e.update(obs(hp=.9,success='mind_blast',sseq=1),3.6).action is None
    # After the slower heal, a stale/absent Pain aura may be retried before
    # Shoot, but the completed Mind Blast opener must never fire twice.
    assert e.update(obs(hp=.9,success='mind_blast',sseq=1),5.0).action in ('pain', 'wand')


def test_bridge_decodes_mind_blast_success_color():
    from PIL import Image
    import numpy as np
    rgb=panel_v08(success='smite',seq=4)
    # panel marker is located at x70 y60 and success pixel is x48 y84.
    rgb[60+84:60+94,70+48:70+58]=(255,128,0)
    got=decode_bridge(rgb).observation
    assert got.success_spell=='mind_blast' and got.success_seq==4


def test_old_key_config_gets_mind_blast_default_and_is_editable():
    old=Config.from_dict({'keys': {'smite':'q','wand':'e','pain':'r'}})
    assert old.keys['mind_blast']=='8'
    keys=validate_bindings({**old.keys,'mind_blast':'b'})
    assert keys['mind_blast']=='b'


def test_old_custom_binding_using_key_8_is_preserved():
    old=Config.from_dict({'keys': {'heal':'8','smite':'4','pain':'3','wand':'7'}})
    assert old.keys['heal']=='8'
    assert old.keys['mind_blast']=='9'
    validate_bindings(old.keys)
