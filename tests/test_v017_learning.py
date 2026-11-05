"""Learning Mode: isolated session I/O, no game window or real key injection."""
import json
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from priestbot.config import Config
from priestbot.engine import Decision, Observation, PriestEngine
from priestbot.learning import (
    SessionRecorder, Advisory, latest_report, promote_advisory,
    train_candidate, game_frame, load_corrections,
)


def frame_for(label):
    # Spatial features the CPU baseline should learn from different sessions.
    a = np.full((100, 180, 3), 20, dtype=np.uint8)
    if label == 'move_forward':
        a[15:65, 65:115, :] = 240
    elif label == 'turn_left':
        a[15:65, 5:55, :] = 240
    else:
        a[15:65, 125:175, :] = 240
    return Image.fromarray(a)


def test_gameplay_recording_has_observation_screenshot_and_summary(tmp_path):
    rec = SessionRecorder(tmp_path, 'bot', screenshot_period_s=.1)
    obs = Observation(hp=.75,mana=.5,target_hp=.95,error='range',error_seq=2)
    rec.observe(obs, decision=Decision('move_forward','getting closer'),
                image=frame_for('move_forward'), mono=10, dry_run=False)
    rec.observe(Observation(.76,.5,.8,error='range',error_seq=3), mono=10.3)
    rec.close()
    rows = [json.loads(line) for line in (rec.path/'events.jsonl').read_text().splitlines()]
    assert rows[1]['decision'] == 'move_forward'
    assert rows[1]['frame'].startswith('frames/')
    assert (rec.path/rows[1]['frame']).is_file()
    stat = json.loads((rec.path/'summary.json').read_text())['counters']
    assert stat['observations'] == 2 and stat['range_errors'] == 1
    assert stat['decision_intents'] == 1


def test_demonstrations_capture_only_whitelisted_fresh_action(tmp_path):
    r = SessionRecorder(tmp_path, 'demonstration', screenshot_period_s=.1)
    r.key_down('move_forward', 10)  # no screenshot yet, ignored
    r.key_up('move_forward',10.4)
    r.observe(Observation(.9,1,1), image=frame_for('move_forward'), mono=11)
    r.key_down('move_forward',11.2)
    r.key_down('move_forward',11.3) # auto repeated key must not become 2 labels
    r.key_up('move_forward',11.6)
    r.key_down('mind_blast',11.7)  # never record typed spell key
    r.key_up('mind_blast',11.8)
    r.close()
    rows = [json.loads(l) for l in (r.path/'events.jsonl').read_text().splitlines()]
    actions = [x for x in rows if x['event']=='correction']
    assert len(actions) == 1
    assert actions[0]['label']=='move_forward'
    assert actions[0]['duration_ms']==400
    assert load_corrections(tmp_path)[0][1]=='move_forward'


def test_candidate_requires_real_evaluation_before_activation(tmp_path):
    assert train_candidate(tmp_path)['status'] == 'insufficient_data'
    with pytest.raises(ValueError):
        promote_advisory(tmp_path, 'fake')
    r = SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.05)
    for i in range(50):
        label = ('move_forward','turn_left')[i % 2]
        now = i * .25
        r.observe(Observation(.9,.9,1),image=frame_for(label),mono=now)
        r.key_down(label,now+.01)
        r.key_up(label,now+.11)
    r.close()
    result = train_candidate(tmp_path, epochs=25)
    assert result['status']=='candidate_created'
    assert result['evaluation']['evaluated'] is False
    assert result['evaluation']['promotion_eligible'] is False
    assert not (tmp_path/'active_advisory.json').exists()
    with pytest.raises(ValueError,match='evaluation'):
        promote_advisory(tmp_path,result['candidate_id'])


def test_multi_session_training_and_explicit_advisory_gate(tmp_path):
    for j in range(2):
        r = SessionRecorder(tmp_path, 'demonstration', screenshot_period_s=.05)
        for i in range(90):
            label = ('move_forward','turn_left','turn_right')[i % 3]
            t = i * .17
            r.observe(Observation(.9,.9,1), image=frame_for(label), mono=t)
            r.key_down(label,t+.01)
            r.key_up(label,t+.09)
        r.close()
    result=train_candidate(tmp_path, epochs=160)
    assert result['status']=='candidate_created'
    assert result['evaluation']['evaluated'] is True
    assert result['evaluation']['holdout_samples'] >= 12
    assert result['evaluation']['promotion_eligible'] is True, result['evaluation']
    assert not (tmp_path/'active_advisory.json').exists() # NEVER auto-promote
    promote_advisory(tmp_path,result['candidate_id'])
    advisor=Advisory(tmp_path)
    label,confidence=advisor.predict(frame_for('turn_left'), {'hp':.9,'mana':.9,'target_hp':1})
    assert label=='turn_left' and confidence>=.6


def test_old_config_migrates_without_touching_combat_or_keys():
    c=Config.from_dict({'keys':{'shield':'shift+e','wand':'7'},
                        'main_damage':'mind_blast_wand'})
    assert c.main_damage=='mind_blast_wand'
    assert c.keys['shield']=='shift+e'
    assert c.learning_record_gameplay and c.learning_record_corrections and c.learning_auto_train
    assert c.learning_demo_keys['move_forward']=='w'
    assert Config().dry_run is True


def test_nonwindows_never_captures_desktop():
    import os
    if os.name != 'nt':
        assert game_frame(object(), ['wow.exe']) is None
