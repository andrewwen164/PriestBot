"""Regression coverage for the failure observed in a real farming session."""
from pathlib import Path
from priestbot.action_semantics import ActionSemanticTracker
from priestbot.semantic_bridge import encode_for_test, decode_bytes


def packet(msg, seq):
    return decode_bytes(encode_for_test(msg, seq))


def test_semantic_packet_diagnostics_and_key_resolution():
    t = ActionSemanticTracker()
    t.ingest(packet('R|3|2', 1), 1)
    t.ingest(packet('B|3|2|ACTIONBUTTON2|item|117|Food', 2), 1.1)
    t.ingest(packet('B|3|SHIFT-G|ACTIONBUTTON7|macro|9|Bandage', 3), 1.2)
    snap=t.snapshot()
    assert snap['declared_bindings']==2
    assert snap['binding_records_seen']==2
    assert snap['packet_types']['B']==2
    assert snap['packet_types']['R']==1
    assert len(snap['bindings'])==2
    t.input('key_down',1.3,key='2',chord='2')
    assert t.counts['attempts']==1
    assert t.attempts[-1]['action_type']=='item'


def test_primary_key_scan_does_not_start_at_secondary():
    addon=(Path(__file__).resolve().parents[1]/'addons/PriestBridge/PriestBridge.lua').read_text()
    assert 'for j=3,r.n do' in addon
    assert 'for j=4,r.n do' not in addon
    assert 'local r=pack(pcall(GetBinding,i))' in addon
    assert 'semEventStreak' in addon
    assert 'sendBinding = haveBindings' in addon


def test_no_false_resolution_when_event_packets_only():
    t=ActionSemanticTracker()
    t.ingest(packet('S|8092|Mind Blast',1),1)
    t.ingest(packet('L|opened|2',2),2)
    snap=t.snapshot()
    assert snap['bindings']==[]
    assert snap['packet_types']['S']==1
    assert snap['binding_records_seen']==0
