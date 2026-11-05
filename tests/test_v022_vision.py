"""v0.22: temporal vision/multi-label reliability, independent session gate."""
import json
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw
import pytest

from priestbot.scene_vision import (detect_red_nameplates, NameplateTracker,
                                    estimate_scene_shift)
from priestbot.learning import SessionRecorder
from priestbot.temporal_vision import (_labels, _state_features, load_temporal_intervals,
                                        temporal_coverage, HEADS, _images,
                                        train_temporal_candidate)

@dataclass
class Obs:
    hp:float=.95; mana:float=.8; target_hp:float=1.0
    error:str|None=None; error_seq:int=1;target_seq:int=1
    casting:bool=False;shield_aura:str='unknown';pain_aura:str='unknown'
    success_spell:str|None=None;success_seq:int=1


def scene(dx=0, dy=0):
    im=Image.new('RGB',(640,360),(60,80,65))
    d=ImageDraw.Draw(im)
    for i in range(12):
        x=60+i*40+dx
        y=50+(i%4)*35+dy
        d.ellipse((x,y,x+14,y+14),fill=(120,130,93))
    d.rectangle((265+dx,84+dy,375+dx,90+dy), fill=(185,30,18))
    return im


def test_nameplate_tracking_and_conservative_filter():
    plates=detect_red_nameplates(scene())
    assert plates
    assert any(.40 <= p.x <= .60 and p.y<.50 for p in plates)
    t=NameplateTracker()
    first=t.update(plates)
    second=t.update(detect_red_nameplates(scene(dx=10)))
    assert first[0].track_id==second[0].track_id
    t.reset()
    assert t.previous==[]
    plain=Image.new('RGB',(640,360),(30,40,20))
    assert detect_red_nameplates(plain)==[]


def test_estimated_scene_translation():
    before=scene(0,0)
    after=scene(15,0)
    flow=estimate_scene_shift(before,after,max_shift=6)
    assert flow['dx']>0 and flow['confidence']>0
    assert estimate_scene_shift(Image.new('RGB',(640,360),'black'),after)['confidence'] == 0


def test_multi_labels_keep_strafe_and_mouse_turn_together():
    row={'movement_occupancy':{'strafe_left':.9,'move_forward':.1},
         'mouse_occupancy':{'right':1.0},'mouse_dx':-81,'mouse_dy':10}
    label,delta,drag=_labels(row)
    assert label[HEADS.index('strafe_left')]==1
    assert label[HEADS.index('character_drag')]==1
    assert label[HEADS.index('mouse_right')]==1
    assert label[HEADS.index('move_forward')]==0
    assert drag == 1
    assert delta[0] < 0
    # Left-drag camera and A strafe can overlap too.
    row['mouse_occupancy']={'left':1.0}
    label,_,_=_labels(row)
    assert label[HEADS.index('camera_drag')]==1
    assert label[HEADS.index('strafe_left')]==1
    assert label[HEADS.index('character_drag')]==0


def test_real_recorder_intervals_and_no_future_frame_leakage(tmp_path):
    rec=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.20)
    # Actions must be simultaneous while the interval passes; prior image is the input.
    rec.observe(Obs(),image=scene(),mono=5.0)
    rec.key_down('strafe_left',5.02)
    rec.mouse_button('right',True,200,150,5.04)
    rec.all_mouse_move(175,150,5.12)
    rec.observe(Obs(target_hp=.9),image=scene(dx=5),mono=5.26)
    rec.mouse_button('right',False,175,150,5.29)
    rec.key_up('strafe_left',5.30)
    rec.observe(Obs(target_hp=.8),image=scene(dx=10),mono=5.54)
    rec.observe(Obs(target_hp=.8),image=scene(dx=12),mono=5.82)
    rec.close()
    rows=[json.loads(x) for x in (rec.path/'events.jsonl').read_text().splitlines()]
    intervals=[r for r in rows if r['event']=='control_interval']
    assert len(intervals)==3
    first=intervals[0]
    assert first['before_frame'] != first['after_frame']
    assert first['movement_occupancy']['strafe_left']>.5
    assert first['mouse_occupancy']['right']>.5
    assert first['mouse_dx']<0
    training=load_temporal_intervals(tmp_path)
    assert len(training)==3
    assert training[0]['frames'][0]==training[0]['frames'][2]
    assert training[0]['frames'][2] == rec.path / first['before_frame']
    assert training[1]['frames'][-1] == rec.path / intervals[1]['before_frame']
    assert training[1]['frames'][-1] != rec.path / intervals[1]['after_frame']
    assert training[0]['actions'][HEADS.index('strafe_left')]==1
    assert training[0]['actions'][HEADS.index('character_drag')]==1
    assert _images(training[0]).shape==(9,180,320)
    assert temporal_coverage(tmp_path)['usable_intervals']==3


def test_focus_lost_and_privacy_dont_make_training_intervals(tmp_path):
    rec=SessionRecorder(tmp_path,'demonstration')
    rec.observe(Obs(),image=scene(),mono=0)
    rec.key_down('move_forward',.01)
    rec.focus_lost()
    rec.observe(Obs(),image=scene(),mono=.24)
    rec.raw_key('enter', True,.25)
    rec.observe(Obs(),image=scene(),mono=.49)
    rec.raw_key('enter',True,.50)
    rec.observe(Obs(),image=scene(),mono=.73)
    rec.close()
    rows=[json.loads(x) for x in (rec.path/'events.jsonl').read_text().splitlines()]
    assert not any(r['event']=='control_interval' for r in rows)
    assert sum(1 for r in rows if r['event']=='privacy_guard')==2


def test_vision_no_automatic_deployment(tmp_path):
    status=train_temporal_candidate(tmp_path,epochs=1)
    assert status['status'] in ('insufficient_data','missing_torch')
    assert not (tmp_path/'active_advisory.json').exists()


def test_torch_model_end_to_end_heldout_session_smoke(tmp_path,monkeypatch):
    import priestbot.temporal_vision as tv
    if not tv.torch_status()['installed']:
        pytest.skip('optional PyTorch not present')
    import torch
    torch.set_num_threads(min(2,torch.get_num_threads()))
    monkeypatch.setattr(tv,'MIN_INTERVALS',8)
    monkeypatch.setattr(tv,'HOLDOUT_MIN',4)
    from priestbot.learning import _jsonl_write
    for session_id in ('20261105T010001','20261105T010002'):
        folder=tmp_path/'sessions'/session_id
        (folder/'frames').mkdir(parents=True)
        imgs=[]
        for i in range(9):
            filename=f'frames/{i:03}.jpg'
            scene(dx=i*3).save(folder/filename)
            imgs.append(filename)
        with (folder/'events.jsonl').open('w') as stream:
            _jsonl_write(stream,{'event':'session_start','kind':'demonstration'})
            for i in range(8):
                _jsonl_write(stream,{'event':'control_interval','schema':1,
                                    'before_frame':imgs[i],'after_frame':imgs[i+1],
                                    'duration_ms':240,
                                    'movement_occupancy':{'strafe_left':1} if i%2 else {'move_forward':1},
                                    'mouse_occupancy':{'right':1} if i%2 else {},
                                    'mouse_dx': -30 if i%2 else 0, 'mouse_dy':0,
                                    'before_state':{'hp':.9,'mana':.8,'target_hp':1},
                                    'after_state':{'hp':.9,'mana':.8,'target_hp':.9},
                                    'before_nameplates':[], 'scene_shift':{'dx':1,'confidence':.5}})
    rows=tv.load_temporal_intervals(tmp_path)
    assert len(rows)==16
    assert rows[2]['frames'][0].name=='000.jpg'
    assert rows[2]['frames'][1].name=='001.jpg'
    assert rows[2]['frames'][2].name=='002.jpg'
    result=tv.train_temporal_candidate(tmp_path,epochs=1,batch_size=4)
    assert result['status']=='candidate_created'
    assert result['evaluation']['evaluated'] is True
    assert result['evaluation']['promotion_eligible'] is False
    assert result['deployment']=='candidate_only_NO_GAME_INPUTS'
    assert (tmp_path/'vision_candidates'/result['candidate_id']/'temporal_model.pt').is_file()
    assert not (tmp_path/'active_advisory.json').exists()
