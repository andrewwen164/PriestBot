"""Tests for v0.8 aura-state and spell-success telemetry: synthetic pixels only."""
from __future__ import annotations
import numpy as np
import pytest
from priestbot.bridge import decode_bridge, BridgeNotFound
from priestbot.config import Config
from priestbot.engine import PriestEngine, Observation
from test_spell_signals import status_panel


STATE_COLORS = dict(present=(0,255,0), absent=(255,0,0), estimated=(255,179,0), unknown=(77,77,77))
SUCCESS_COLORS = {None:(77,77,77),'shield':(0,255,0),'pain':(255,0,255),'smite':(255,255,255),'heal':(0,255,255)}


def panel_v08(shield='unknown',pain='unknown',success=None,seq=0,target_seq=0,scale=1):
    # Uses all legacy v0.7 rows, then appends the new v0.8 protocol at y84.
    from PIL import Image
    base = status_panel(scale=1)[40:40+78,55:55+160].copy()
    pixels = np.zeros((102,160,3), dtype=np.uint8)
    pixels[:78] = base
    pixels[84:92,0:8] = (0,179,179)
    pixels[84:94,16:26] = STATE_COLORS[shield]
    pixels[84:94,32:42] = STATE_COLORS[pain]
    pixels[84:94,48:58] = SUCCESS_COLORS[success]
    for i,x in enumerate((64,76,88,100)):
        pixels[84:92,x:x+8] = (255,255,255) if seq & (1<<i) else (64,64,64)
    for i,x in enumerate((112,124,136,148)):
        pixels[84:92,x:x+8] = (255,255,255) if target_seq & (1<<i) else (64,64,64)
    full = np.zeros((900,1300,3),np.uint8)
    full[:] = (20,25,30)
    scaled=np.asarray(Image.fromarray(pixels).resize((160*scale,102*scale),Image.Resampling.NEAREST))
    full[60:60+102*scale,70:70+160*scale]=scaled
    return full


@pytest.mark.parametrize('shield',['unknown','estimated','present','absent'])
@pytest.mark.parametrize('pain',['unknown','estimated','present','absent'])
@pytest.mark.parametrize('success',[None,'shield','pain','smite','heal'])
@pytest.mark.parametrize('scale',[1,2])
def test_roundtrip_v08(shield,pain,success,scale):
    obs=decode_bridge(panel_v08(shield,pain,success,13,9,scale)).observation
    assert obs.shield_aura==shield and obs.pain_aura==pain
    assert obs.success_spell==success and obs.success_seq==13 and obs.target_seq==9


def test_v07_fallback():
    obs=decode_bridge(status_panel()).observation
    assert obs.success_seq is None and obs.pain_aura is None


def test_corrupt_v08_fails_closed():
    rgb=panel_v08()
    rgb[84+60:94+60,70+16:70+26] = (50,100,200)
    with pytest.raises(BridgeNotFound): decode_bridge(rgb)


def observe(*,hp=1,mana=1,target=1,shield=None,pain=None,success=None,sseq=None,tseq=None):
    return Observation(hp,mana,target,False,None,0,shield,pain,success,sseq,tseq)


def test_verified_present_auras_skip_recast():
    cfg=Config(use_shield=True,main_damage='wand', use_pain=True,stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    r=e.update(observe(shield='present',pain='present',sseq=0,tseq=0),0)
    assert r.action=='wand'
    assert e.update(observe(shield='present',pain='present',sseq=0,tseq=0),40).action is None


def test_confirmed_pain_estimate_then_recast():
    cfg=Config(use_shield=False,main_damage='wand',stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    assert e.update(observe(shield='unknown',pain='unknown',sseq=0,tseq=0),0).action=='pain'
    e.update(observe(shield='unknown',pain='unknown',success='pain',sseq=1,tseq=0),.3)
    assert e.update(observe(shield='unknown',pain='unknown',sseq=1,tseq=0),17).action != 'pain'
    assert e.update(observe(shield='unknown',pain='unknown',sseq=1,tseq=0),19).action == 'pain'


def test_target_change_zeros_pain_estimate_even_with_full_hp():
    cfg=Config(use_shield=False,main_damage='wand',stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    assert e.update(observe(sseq=0,tseq=0),0).action=='pain'
    e.update(observe(sseq=1,tseq=0,success='pain'),.3)
    r=e.update(observe(sseq=1,tseq=1),3)
    assert r.action=='pain'


def test_absent_aura_not_spammed_during_gcd():
    cfg=Config(use_shield=False,main_damage='wand',stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    assert e.update(observe(pain='absent',sseq=0,tseq=0),0).action=='pain'
    assert e.update(observe(pain='absent',sseq=0,tseq=0),.3).action is None
    assert e.update(observe(pain='absent',sseq=0,tseq=0),1.6).action=='wand'
    assert e.update(observe(pain='absent',sseq=0,tseq=0),1).action is None
    assert e.update(observe(pain='absent',sseq=0,tseq=0),3.4).action=='pain'


def test_legacy_timers_work():
    cfg=Config(use_shield=False,main_damage='wand',stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    assert e.update(observe(),0).action=='pain'
    assert e.update(observe(),.3).action is None
    assert e.update(observe(),1.6).action=='wand'


def test_smite_success_allows_next_cast_after_confirmation():
    cfg = Config(use_shield=False,use_pain=False,main_damage='smite')
    e = PriestEngine(cfg)
    assert e.update(observe(sseq=0,tseq=0),0).action=='smite'
    # Starts casting and stops new inputs; then a confirmed success arrives.
    assert e.update(Observation(1,1,1,True,None,0,None,None,None,0,0),1.0).action is None
    assert e.update(observe(success='smite',sseq=1,tseq=0),1.5).action is None
    assert e.update(observe(sseq=1,tseq=0),1.8).action=='smite'


def test_confirmed_shield_waits_weakened_soul_lockout():
    cfg=Config(use_shield=True,use_pain=False,main_damage='wand',stuck_timeout_s=100,target_timeout_s=100)
    e=PriestEngine(cfg)
    assert e.update(observe(shield='absent',sseq=0,tseq=0),0).action=='shield'
    e.update(observe(shield='absent',success='shield',sseq=1,tseq=0),1)
    # Shield was absorbed early, but cannot be reapplied while Weakened Soul persists.
    assert e.update(observe(shield='absent',sseq=1,tseq=0),10).action!='shield'
    assert e.update(observe(shield='absent',sseq=1,tseq=0),16.1).action=='shield'
