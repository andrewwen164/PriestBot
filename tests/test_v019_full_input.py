"""v0.19: full foreground game-input trace, supervised movement/camera classes and privacy."""
import json
from PIL import Image
from priestbot.engine import Observation
from priestbot.learning import SessionRecorder, load_corrections, game_client_point
from priestbot.config import Config


def rows(rec):
    return [json.loads(s) for s in (rec.path/'events.jsonl').read_text().splitlines()]


def ready(tmp_path, t=1):
    r = SessionRecorder(tmp_path, 'demonstration', screenshot_period_s=.01)
    r.observe(Observation(.9,.8,1), image=Image.new('RGB',(320,180)), mono=t)
    return r


def test_left_drag_camera_only_not_character_turn(tmp_path):
    r=ready(tmp_path)
    r.mouse_button('left',True,80,50,1.01)
    r.all_mouse_move(110,55,1.06)
    r.all_mouse_move(160,60,1.10)
    r.mouse_button('left',False,160,60,1.25)
    r.close()
    labels=[x['label'] for x in rows(r) if x['event']=='correction']
    assert labels == ['camera_look_right']
    assert load_corrections(tmp_path)[0][1]=='camera_look_right'
    assert not any('mouse_turn' in x for x in labels)


def test_left_click_and_right_click_raw_and_coordinates(tmp_path):
    r=ready(tmp_path)
    for button,t in [('left',1.02),('right',1.30),('middle',1.60),('x1',1.90),('x2',2.20)]:
        r.observe(Observation(.9,.8,1),image=Image.new('RGB',(320,180)),mono=t)
        r.mouse_button(button,True,25,42,t+.01)
        r.mouse_button(button,False,25,42,t+.08)
    r.close()
    events=[x for x in rows(r) if x['event']=='input' and x['kind'].startswith('mouse_') and 'button' in x]
    assert len(events)==10
    assert {x['button'] for x in events}=={'left','right','middle','x1','x2'}
    assert all((x['x'], x['y'])==(25,42) for x in events)
    assert not [x for x in rows(r) if x['event']=='correction']


def test_both_mouse_buttons_are_forward_and_not_camera_only(tmp_path):
    r=ready(tmp_path)
    r.mouse_button('right',True,100,100,1.01)
    r.mouse_button('left',True,100,100,1.05)
    r.mouse_button('left',False,100,100,1.35)
    r.mouse_button('right',False,100,100,1.37)
    r.close()
    assert [x['label'] for x in rows(r) if x['event']=='correction']==['mouse_both_forward']


def test_lmb_rmb_with_right_turn_labeled_once(tmp_path):
    r=ready(tmp_path)
    r.mouse_button('left',True,100,100,1.01)
    r.mouse_button('right',True,100,100,1.04)
    r.all_mouse_move(145,100,1.10)
    r.mouse_button('right',False,145,100,1.20)
    r.mouse_button('left',False,145,100,1.25)
    r.observe(Observation(.9,.8,1),image=Image.new('RGB',(320,180)),mono=1.40)
    r.close()
    labels=[x['label'] for x in rows(r) if x['event']=='correction']
    assert labels==['mouse_both_forward_turn_right']


def test_w_and_left_drag_does_not_create_forward_only(tmp_path):
    r=ready(tmp_path)
    r.key_down('move_forward',1.01)
    r.mouse_button('left',True,30,30,1.04)
    r.all_mouse_move(70,30,1.07)
    r.key_up('move_forward',1.12)
    r.mouse_button('left',False,70,30,1.20)
    r.close()
    labels=[x['label'] for x in rows(r) if x['event']=='correction']
    assert labels==['move_forward_camera_look_right']


def test_keyboard_chord_spells_and_scroll_logged_but_not_trained(tmp_path):
    r=ready(tmp_path)
    r.raw_key('shift_l',True,1.01)
    r.raw_key('e',True,1.02,action=None)
    r.raw_key('e',True,1.03)  # key-repeat ignored
    r.raw_key('e',False,1.05)
    r.raw_key('shift_l',False,1.06)
    r.scroll(12,13,0,2,1.07)
    r.scroll(12,13,1,-1,1.08)
    r.close()
    inputs=[x for x in rows(r) if x['event']=='input']
    assert [x['kind'] for x in inputs].count('key_down')==2
    assert any(x.get('chord')=='shift+e' for x in inputs)
    assert [x['dy'] for x in inputs if x['kind']=='scroll']==[2.0,-1.0]
    assert not [x for x in rows(r) if x['event']=='correction']


def test_chat_privacy_suppresses_typed_keys(tmp_path):
    r=ready(tmp_path)
    r.raw_key('enter',True,1.02)
    r.raw_key('p',True,1.03)
    r.raw_key('a',True,1.04)
    r.key_down('turn_left',1.05)  # shouldn't train letter typed in chat
    r.raw_key('enter',True,1.06)
    r.raw_key('x',True,1.07)
    r.raw_key('x',False,1.08)
    r.close()
    data=(r.path/'events.jsonl').read_text()
    assert '"key":"p"' not in data and '"key":"a"' not in data
    assert '"key":"x"' in data
    assert [x['state'] for x in rows(r) if x['event']=='privacy_guard']==['pause','resume']
    assert not [x for x in rows(r) if x['event']=='correction']


def test_explicit_pause_discards_in_progress_input(tmp_path):
    r=ready(tmp_path)
    r.mouse_button('right',True,100,100,1.01)
    r.all_mouse_move(150,100,1.04)
    r.set_capture_paused(True)
    r.raw_key('e',True,1.05)
    r.mouse_button('right',False,150,100,1.07)
    r.set_capture_paused(False)
    r.close()
    assert not [x for x in rows(r) if x['event']=='correction']
    assert len([x for x in rows(r) if x['event']=='capture_control'])==2


def test_focus_loss_cancels_drag_and_pressed_keys(tmp_path):
    r=ready(tmp_path)
    r.key_down('move_forward',1.01)
    r.mouse_button('right',True,100,100,1.03)
    r.all_mouse_move(160,100,1.06)
    r.focus_lost()
    r.mouse_button('right',False,160,100,1.08)
    r.key_up('move_forward',1.1)
    r.close()
    assert not [x for x in rows(r) if x['event']=='correction']


def test_idle_cursor_moves_sampled_without_training(tmp_path):
    r=ready(tmp_path)
    r.all_mouse_move(100,120,1.01)
    r.all_mouse_move(105,120,1.04)
    r.all_mouse_move(115,120,1.15)
    r.close()
    assert any(x.get('kind')=='cursor_move' for x in rows(r))
    assert not [x for x in rows(r) if x['event']=='correction']


def test_upgrade_default_full_keys_and_game_client_test_point():
    c=Config.from_dict({'learning_record_mouse':True,'keys':{'shield':'shift+e'}})
    assert c.learning_record_all_keys and c.learning_demo_keys['jump']=='space'
    assert c.keys['shield']=='shift+e'
    import os
    if os.name != 'nt':
        assert game_client_point(10,12,['wow.exe'])==(10,12)
