"""v0.20: transparent learning coverage and read-only evaluation reporting."""
from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from priestbot.engine import Observation
from priestbot.learning import SessionRecorder, train_candidate, training_coverage
from priestbot.learning_dashboard import gate_summary, per_action_rows, safely_resolve_frame


def example_image(label):
    img = Image.new('RGB', (160, 100), (25, 25, 25))
    draw = ImageDraw.Draw(img)
    xy = (10, 15, 50, 60) if label == 'move_forward' else (110, 15, 150, 60)
    draw.rectangle(xy, fill=(240, 240, 240))
    return img


def make_demo(base, labels):
    rec = SessionRecorder(base, 'demonstration', screenshot_period_s=.05)
    for i, label in enumerate(labels):
        t = .2*i
        rec.observe(Observation(.9, .9, 1), image=example_image(label), mono=t)
        rec.key_down(label, t+.01)
        rec.key_up(label, t+.11)
    rec.close()
    return rec


def test_coverage_reports_labeled_not_raw_event_count(tmp_path):
    make_demo(tmp_path, ['move_forward']*10 + ['strafe_left']*3)
    cover=training_coverage(tmp_path)
    rows={x['action']:x for x in cover['actions']}
    assert cover['total_labels']==13
    assert cover['sessions']==1
    assert cover['action_count']==1
    assert cover['usable_for_training']==10
    assert rows['strafe_left']['training_shortfall']==5
    assert rows['move_forward']['recommended_shortfall']==10
    assert any('separate demonstration' in note for note in cover['next_steps'])


def test_candidate_report_includes_holdout_predictions_and_gates(tmp_path):
    make_demo(tmp_path, ['move_forward', 'turn_left']*24)
    make_demo(tmp_path, ['move_forward', 'turn_left']*12)
    result = train_candidate(tmp_path, epochs=45)
    assert result['status']=='candidate_created'
    ev=result['evaluation']
    assert ev['evaluated'] is True
    assert ev['split_checks']['holdout_at_least_12'] is True
    assert ev['examples_total']==24
    assert ev['examples']
    assert sum(x['holdout_samples'] for x in per_action_rows(result)) == 24
    assert len(ev['per_action']) == 2
    assert all(x['confidence']>=0 and x['confidence']<=1 for x in ev['examples'])
    assert all(safely_resolve_frame(tmp_path,x['frame']).is_file() for x in ev['examples'])
    summary=gate_summary(result)
    assert len(summary['checks'])==3
    assert summary['state'] in ('ELIGIBLE — ADVISORY ONLY', 'EVALUATED — DID NOT PASS')


def test_no_holdout_explains_why_and_never_passes(tmp_path):
    make_demo(tmp_path, ['move_forward','turn_left']*25)
    result=train_candidate(tmp_path,epochs=10)
    ev=result['evaluation']
    assert ev['evaluated'] is False and ev['promotion_eligible'] is False
    summary=gate_summary(result)
    assert summary['state']=='NOT EVALUATED'
    assert ('A separate demonstration session exists',False) in summary['checks']
    assert not ev.get('examples')
    assert per_action_rows(result)[0]['holdout_samples']==0


def test_example_paths_are_limited_to_learning_session_frames(tmp_path):
    frame=tmp_path/'sessions'/'session-a'/'frames'/'0001.jpg'
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b'a')
    assert safely_resolve_frame(tmp_path,'sessions/session-a/frames/0001.jpg')==frame
    assert safely_resolve_frame(tmp_path,'../../etc/passwd') is None
    assert safely_resolve_frame(tmp_path,'sessions/session-a/events.jsonl') is None
    assert safely_resolve_frame(tmp_path,'sessions/session-a/frames/../events.jsonl') is None
    assert safely_resolve_frame(tmp_path,'sessions/other/frames/missing.jpg') is None


def test_legacy_candidate_remains_readable():
    old={'classes':['move_forward','turn_left'],
         'training':{'samples':50,'sessions':2},
         'evaluation':{'evaluated':False,'promotion_eligible':False,'train_samples':50,'holdout_samples':0}}
    summary=gate_summary(old)
    assert summary['state']=='NOT EVALUATED'
    assert per_action_rows(old)[0]['holdout_samples']==0


def test_tk_dashboard_can_open_with_and_without_report(tmp_path):
    import tkinter as tk
    from priestbot.learning_dashboard import LearningDashboard
    try:
        root=tk.Tk()
    except tk.TclError:
        pytest.skip('No graphical Tk display')
    root.withdraw()
    try:
        dashboard=LearningDashboard(root,None,training_coverage(tmp_path),base=tmp_path,starting_tab='coverage')
        root.update()
        assert len(dashboard.tabs.tabs())==4
        assert dashboard.tabs.select()==str(dashboard.coverage_frame)
        dashboard.window.destroy()
        report={'candidate_id':'example','classes':['move_forward'],'training':{'samples':50},
                'evaluation':{'evaluated':False,'promotion_eligible':False,'holdout_samples':0,'train_samples':50}}
        dashboard=LearningDashboard(root,report,training_coverage(tmp_path),base=tmp_path)
        root.update()
        dashboard.window.destroy()
    finally:
        root.destroy()
