"""Regression checks for the privacy-scoped, combined keyboard/mouse recorder."""
import json

import numpy as np
from PIL import Image

from priestbot.config import Config
from priestbot.engine import Observation
from priestbot.learning import SessionRecorder, load_corrections, mouse_motion_profiles, train_candidate


def img(kind):
    a=np.full((90, 150, 3), 35, dtype=np.uint8)
    a[:, (30 if 'left' in kind else 95): (50 if 'left' in kind else 120)] = 200
    return Image.fromarray(a)


def events(r):
    return [json.loads(v) for v in (r.path/'events.jsonl').read_text().splitlines()]


def test_rmb_drag_records_before_after_and_mouse_vector(tmp_path):
    r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    r.observe(Observation(.9,.7,1),image=img('right'),mono=10)
    before=r.last_frame
    r.mouse_press(100,150,10.1)
    r.mouse_move(130,150,10.2)
    r.mouse_move(180,158,10.28)
    r.mouse_release(10.35)
    r.observe(Observation(.9,.7,1),image=img('left'),mono=10.60)
    r.close()
    corrections=[x for x in events(r) if x['event']=='correction']
    assert len(corrections)==1
    c=corrections[0]
    assert c['label']=='mouse_turn_right'
    assert c['mouse_dx']==80 and c['mouse_dy']==8
    assert c['frame']==before
    assert c['frame_after'] and c['frame_after'] != before
    assert c['duration_ms']==250
    assert c['right_mouse_held'] is True
    assert r.stats['mouse_corrections']==1
    assert load_corrections(tmp_path)[0][1]=='mouse_turn_right'


def test_w_plus_rmb_is_combined_label_not_mislabeled_as_w_only(tmp_path):
    r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    r.observe(Observation(.9,.7,1),image=img('left'),mono=1)
    r.key_down('move_forward',1.02)
    r.mouse_press(300,300,1.05)
    r.mouse_move(260,301,1.13)
    r.key_up('move_forward',1.20)
    r.mouse_release(1.30)
    r.observe(Observation(.9,.7,1),image=img('right'),mono=1.60)
    r.close()
    c=[x for x in events(r) if x['event']=='correction']
    assert [x['label'] for x in c] == ['move_forward_mouse_turn_left']
    assert c[0]['keys_held']==['move_forward']
    assert c[0]['mouse_dx']==-40


def test_forward_key_started_mid_drag_is_included(tmp_path):
    r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    r.observe(Observation(.9,.7,1),image=img('right'),mono=5)
    r.mouse_press(200,200,5.05)
    r.key_down('move_forward',5.10)
    r.mouse_move(240,200,5.15)
    r.mouse_release(5.30)
    r.key_up('move_forward',5.32)
    r.close()
    assert [x['label'] for x in events(r) if x['event']=='correction'] == ['move_forward_mouse_turn_right']


def test_mouse_releases_discarded_on_focus_loss_and_jitter(tmp_path):
    r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    r.observe(Observation(.9,.7,1),image=img('left'),mono=0)
    r.mouse_press(200,200,.05)
    r.mouse_move(500,200,.10)
    r.cancel_mouse()  # triggered on non-WoW foreground
    r.mouse_release(.25)
    r.mouse_press(200,200,.30)
    r.mouse_move(204,201,.40)  # tiny drift, no label
    r.mouse_release(.45)
    r.close()
    assert not [x for x in events(r) if x['event']=='correction']


def test_warp_not_used_as_motion_label(tmp_path):
    r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    r.observe(Observation(.9,.7,1),image=img('left'),mono=0)
    r.mouse_press(200,200,.05)
    r.mouse_move(1400,200,.10)  # pointer warp / obvious jump
    r.mouse_release(.25)
    r.close()
    assert r.stats['mouse_corrections']==0


def test_motion_profiles_and_trainable_mouse_class(tmp_path):
    for j in range(2):
        r=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.01)
        for i in range(48):
            label=['mouse_turn_right','mouse_turn_left'][i%2]
            t=i*.30
            r.observe(Observation(.9,.7,1),image=img(label),mono=t)
            r.mouse_press(200,200,t+.01)
            r.mouse_move(230 if 'right' in label else 170,201,t+.05)
            r.mouse_release(t+.15)
            r.observe(Observation(.9,.7,1),image=img(label),mono=t+.2)
        r.close()
    profiles=mouse_motion_profiles(tmp_path)
    assert profiles['mouse_turn_right']['samples']==48
    assert profiles['mouse_turn_right']['median_dx_px']==30
    result=train_candidate(tmp_path,epochs=120)
    assert result['status']=='candidate_created'
    assert set(result['classes'])=={'mouse_turn_left','mouse_turn_right'}
    assert result['evaluation']['evaluated'] is True
    assert 'mouse_motion_profiles' in result
    assert not (tmp_path/'active_advisory.json').exists()


def test_old_config_inherits_mouse_opt_in():
    cfg=Config.from_dict({'learning_record_corrections': True,
                          'keys': {'shield': 'shift+e'}})
    assert cfg.learning_record_mouse is True
    assert cfg.keys['shield']=='shift+e'
