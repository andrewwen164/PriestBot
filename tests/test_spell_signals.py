"""v0.7 spell signals: synthetic panel and deterministic gameplay decisions."""
from __future__ import annotations
import numpy as np
import pytest
from PIL import Image
from priestbot.bridge import decode_bridge, BridgeNotFound
from priestbot.engine import Observation, PriestEngine
from priestbot.config import Config
from test_bridge import mock_panel


def status_panel(casting=False, error=None, seq=0, scale=1):
    p = np.zeros((78, 160, 3), np.uint8)
    p[0:12,0:12] = (255, 0, 255)
    p[0:12,16:28] = (0, 255, 255)
    p[0:12,32:44] = (255, 255, 0)
    p[0:8,48:56] = (0, 204, 102)
    p[0:10,60:70] = (0,255,0) if casting else (77,77,77)
    colors = {None:(77,77,77),'range':(255,128,0),'los':(179,0,255),'facing':(0,179,255),'failed':(255,0,0)}
    p[0:10,76:86] = colors[error]
    for i, x in enumerate((96,108,120,132)):
        p[0:8,x:x+8] = (255,255,255) if seq & (1<<i) else (64,64,64)
    for index, color in enumerate(((0,255,0),(0,97,255),(255,0,0))):
        y=20+20*index
        p[y:y+12,:] = (25,25,25)
        p[y:y+12,:int((.9,.8,.7)[index]*160)] = color
    full = np.zeros((800,1100,3),np.uint8)
    full[:]=(20,25,30)
    stretched = np.asarray(Image.fromarray(p).resize((160*scale,78*scale),Image.Resampling.NEAREST))
    full[40:40+78*scale,55:55+160*scale]=stretched
    return full


@pytest.mark.parametrize('casting', [True,False])
@pytest.mark.parametrize('err', [None,'range','los','facing','failed'])
@pytest.mark.parametrize('seq', [0,1,8,15])
@pytest.mark.parametrize('scale', [1,2,3])
def test_decode_signals(casting,err,seq,scale):
    obs = decode_bridge(status_panel(casting,err,seq,scale)).observation
    assert obs.casting is casting
    assert obs.error == err
    assert obs.error_seq == seq
    assert abs(obs.hp-.9)<.02
    assert abs(obs.mana-.8)<.02
    assert abs(obs.target_hp-.7)<.02


def test_v06_addon_fallback_has_no_signals():
    obs=decode_bridge(mock_panel()).observation
    assert obs.casting is None and obs.error is None and obs.error_seq is None


def test_casting_blocks_additional_actions():
    e=PriestEngine(Config(main_damage='smite',use_shield=False))
    assert e.update(Observation(1,1,1,False,None,0),0).action=='pain'
    assert e.update(Observation(1,.9,1,True,None,0),3).action is None
    assert e.update(Observation(1,.9,.95,False,None,0),3.1).action=='smite'


def test_out_of_range_skips_immediately_after_attack():
    e=PriestEngine(Config(main_damage='smite',use_shield=False))
    assert e.update(Observation(1,1,1,False,None,2),0).action=='pain'
    r=e.update(Observation(1,.8,1,False,'range',3),.3)
    assert r.action=='clear_target' and 'range' in r.reason.lower()
    assert e.failed_targets==1
    # The same still-visible error may not be replayed.
    assert e.update(Observation(1,.8,0,False,'range',3),.6).action is None


def test_los_skips_immediately_after_attack():
    e=PriestEngine(Config(main_damage='wand',use_shield=False))
    assert e.update(Observation(1,1,1,False,None,0),0).action=='pain'
    r=e.update(Observation(1,.9,1,False,'los',1),.4)
    assert r.action=='clear_target' and 'sight' in r.reason.lower()


def test_unrelated_old_error_ignored():
    e=PriestEngine(Config(main_damage='wand',use_shield=False))
    e.update(Observation(1,1,0,False,'range',8),0)
    r=e.update(Observation(1,1,1,False,'range',8),2)
    assert r.action=='pain'
    r=e.update(Observation(1,.95,1,False,'range',9),8)
    assert r.action!='clear_target'  # outside four-second association window


def test_generic_spell_fail_does_not_skip_target():
    e=PriestEngine(Config(main_damage='wand',use_shield=False))
    e.update(Observation(1,1,1,False,None,0),0)
    assert e.update(Observation(1,.9,1,False,'failed',1),.4).action != 'clear_target'


def test_missing_signals_preserves_prior_behavior():
    e=PriestEngine(Config(main_damage='wand',use_shield=False))
    assert e.update(Observation(1,1,1),0).action=='pain'
    assert e.update(Observation(1,1,1),.3).action is None
    assert e.update(Observation(1,1,1),1.6).action=='wand'


def test_signal_pixel_corruption_fails_closed():
    rgb = status_panel()
    rgb[40:50,55+76:55+86] = (1,240,230)
    with pytest.raises(BridgeNotFound): decode_bridge(rgb)
