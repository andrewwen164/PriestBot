"""Farming episodes must preserve input/vision and uncertainty boundaries."""
import json
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from priestbot.learning import SessionRecorder
from priestbot.action_semantics import ActionSemanticTracker
from priestbot.semantic_bridge import decode_bytes, encode_for_test
from priestbot.farming_demo import FarmingDemonstrations


def pkt(s, i):
    return decode_bytes(encode_for_test(s, i))


@dataclass
class Obs:
    hp: float = .9
    mana: float = .8
    target_hp: float = 0
    casting: bool = False
    error: str | None = None
    error_seq: int = 0
    success_seq: int = 0
    target_seq: int = 0
    pain_aura: str = 'unknown'
    shield_aura: str = 'unknown'
    success_spell: str = ''


def im(color):
    return Image.new('RGB', (640, 360), color)


def test_target_search_spell_sequence_and_loot_have_distinct_evidence(tmp_path):
    rec = SessionRecorder(tmp_path, 'demonstration', screenshot_period_s=.20)
    rec.observe(Obs(), image=im('red'), mono=1.0)
    rec.raw_key('tab', True, 1.02)
    rec.raw_key('tab', False, 1.04)
    rec.ingest_semantic(pkt('G|1|hostile|alive|Wolf',1), mono=1.08)
    rec.observe(Obs(target_hp=1, target_seq=1), image=im('blue'), mono=1.27)
    rec.ingest_semantic(pkt('B|1|8|ACTIONBUTTON8|spell|8092|Mind Blast',2), mono=1.30)
    rec.raw_key('8',True,1.32)
    rec.ingest_semantic(pkt('T|8092|Mind Blast',3),mono=1.34)
    rec.ingest_semantic(pkt('S|8092|Mind Blast',4),mono=1.46)
    rec.observe(Obs(target_hp=.5,target_seq=1,success_seq=1),image=im('green'),mono=1.54)
    # A loot window opened as a result of a later manual corpse interaction.
    rec.mouse_button('right',True,150,140,1.60)
    rec.mouse_button('right',False,150,140,1.62)
    rec.ingest_semantic(pkt('L|opened|1',5),mono=1.66)
    rec.ingest_semantic(pkt('L|slot_cleared|1',6),mono=1.72)
    rec.ingest_semantic(pkt('L|closed|0',7),mono=1.75)
    rec.observe(Obs(target_hp=0,target_seq=2),image=im('yellow'),mono=1.82)
    rec.close()
    report=json.loads((rec.path/'farming_report.json').read_text())
    assert report['counts']['target_search_attempt']==1
    assert report['counts']['target_selected']==1
    assert report['counts']['rotation_input']==1
    assert report['counts']['spell_start']==1
    assert report['counts']['spell_success']==1
    assert report['counts']['loot_opened']==1
    assert report['counts']['loot_slot_cleared']==1
    assert report['counts']['loot_closed']==1
    assert report['loot_sessions'][0]['outcome']=='slot_cleared_observed'
    examples=[json.loads(l) for l in (rec.path/'farming_examples.jsonl').read_text().splitlines()]
    # At least one valid PRE/POST window for search, combat and looting.
    assert any(e['category']=='target_selected' and e['image_pair_complete'] for e in examples)
    assert any(e['category']=='spell_success' and e['image_pair_complete'] for e in examples)
    assert any(e['category']=='loot_opened' and e['image_pair_complete'] for e in examples)
    assert not (tmp_path/'active_advisory.json').exists()


def test_opening_loot_without_clearing_is_not_a_confirmed_loot(tmp_path):
    d=tmp_path/'session';d.mkdir()
    t=FarmingDemonstrations(d)
    t.packet(pkt('L|opened|2',1),1)
    t.packet(pkt('L|closed|0',2),2)
    t.close()
    result=json.loads((d/'farming_report.json').read_text())
    assert result['loot_sessions']==[{'cleared_slots':0,'outcome':'unknown'}]
    assert result['counts'].get('loot_slot_cleared',0)==0


def test_client_focus_loss_breaks_input_frame_pair(tmp_path):
    rec=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.2)
    rec.observe(Obs(),image=im('white'),mono=1)
    rec.raw_key('tab',True,1.1)
    rec.focus_lost()
    rec.observe(Obs(),image=im('black'),mono=1.3)
    rec.close()
    examples=[json.loads(l) for l in (rec.path/'farming_examples.jsonl').read_text().splitlines()]
    event=next(row for row in examples if row['category']=='target_search_attempt')
    assert not event['image_pair_complete']
    assert event['after_frame'] is None


def test_raw_simultaneous_strafe_and_mouse_movement_still_saved(tmp_path):
    rec=SessionRecorder(tmp_path,'demonstration',screenshot_period_s=.2)
    rec.observe(Obs(),image=im('white'),mono=2)
    rec.key_down('strafe_left',2.01)
    rec.mouse_button('right',True,130,130,2.02)
    rec.all_mouse_move(100,130,2.06)
    rec.observe(Obs(),image=im('black'),mono=2.26)
    rec.mouse_button('right',False,100,130,2.28)
    rec.key_up('strafe_left',2.29)
    rec.close()
    rows=[json.loads(l) for l in (rec.path/'events.jsonl').read_text().splitlines()]
    interval=next(x for x in rows if x['event']=='control_interval')
    assert interval['movement_occupancy']['strafe_left']>.7
    assert interval['mouse_occupancy']['right']>.7
    assert interval['phase'] in ('search','engage')


def test_protocol_accepts_native_target_and_loot_packets():
    for i,s in enumerate(('G|2|hostile|alive|Wolf','L|opened|3','L|slot_cleared|1',
                          'L|closed|0','D|combat_start','D|combat_end'),1):
        p=pkt(s,i)
        assert p and p.payload==s


def test_corpse_click_link_is_candidate_not_verified(tmp_path):
    d=tmp_path/'s';d.mkdir()
    t=FarmingDemonstrations(d)
    t.observe('frames/before.jpg',{'hp':.8,'target_hp':0},1.0)
    t.input('mouse_down',1.1,data={'button':'right','x':230,'y':170})
    t.packet(pkt('L|opened|2',1),1.55)
    t.observe('frames/after.jpg',{'hp':.8,'target_hp':0},1.7)
    t.close()
    rows=[json.loads(x) for x in (d/'farming_examples.jsonl').read_text().splitlines()]
    loot=next(r for r in rows if r['category']=='loot_opened')
    assert loot['image_pair_complete']
    assert loot['candidate_interaction']['x']==230
    assert loot['candidate_interaction']['association']=='temporal_candidate_unverified'
    assert not t.counters['loot_slot_cleared']


def test_chat_gate_never_creates_spell_input_label(tmp_path):
    rec=SessionRecorder(tmp_path,'demonstration')
    rec.observe(Obs(),image=im('white'),mono=1)
    rec.raw_key('enter',True,1.1)
    rec.raw_key('tab',True,1.12)
    rec.raw_key('enter',True,1.2)
    rec.close()
    summary=json.loads((rec.path/'farming_report.json').read_text())
    assert summary['counts'].get('target_search_attempt',0)==0
