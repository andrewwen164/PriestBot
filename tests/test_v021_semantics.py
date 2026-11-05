"""Protocol and evidence checks for v0.21 Action Semantics."""
import json
import numpy as np
from pathlib import Path
from PIL import Image

from priestbot.semantic_bridge import decode_bytes, decode_pixels, encode_for_test, monitor_semantics
from priestbot.action_semantics import ActionSemanticTracker, wow_binding
from priestbot.learning import SessionRecorder


def fake_packet(text, seq):
    return decode_bytes(encode_for_test(text, seq))


def make_frame(packet_bytes, scale=1.0):
    im = np.zeros((round(130*scale), round(290*scale),3), dtype=np.uint8)
    def square(x,y,w,h,rgb):
        left,top=round(x*scale),round(y*scale)
        im[top:round((y+h)*scale),left:round((x+w)*scale)]=tuple(rgb)
    square(180,0,8,8,(0,191,89))
    square(196,0,8,8,(191,102,0))
    for i in range(32):
        col,row=i%8,i//8
        square(180+col*10,20+row*10,8,8,packet_bytes[i*3:i*3+3])
    return im


def test_protocol_round_trip_and_errors():
    for value in ('B|1|2|ACTIONBUTTON2|item|117|Tough Jerky',
                  'B|1|SHIFT-G|ACTIONBUTTON7|macro|12|Bandage > Heavy Linen Bandage',
                  'S|8092|Mind Blast', 'A|Food|present'):
        packet=fake_packet(value, 65535)
        assert packet.sequence==65535 and packet.payload==value
        corrupted=bytearray(encode_for_test(value,12))
        corrupted[8]^=1
        assert decode_bytes(bytes(corrupted)) is None
        assert decode_bytes(bytes([1])*96) is None
    assert fake_packet('P|0', 0).kind=='P'


def test_sidecar_scale_variants_and_old_addon():
    raw=encode_for_test('B|3|2|ACTIONBUTTON2|item|117|Food',4)
    for scale in (0.9, 1.0, 1.17, 1.5, 1.75):
        image=make_frame(raw,scale)
        packet=decode_pixels(image,0,0,scale)
        assert packet is not None and packet.kind=='B', scale
    old=np.zeros((130,290,3),dtype=np.uint8)
    assert decode_pixels(old,0,0,1) is None


def test_bindings_and_success_are_distinct():
    events=[]
    track=ActionSemanticTracker(emit=lambda ev,**kw:events.append((ev,kw)))
    track.ingest(fake_packet('R|2|2',1),mono=0.0)
    track.ingest(fake_packet('B|2|2|ACTIONBUTTON2|item|117|Food',2),mono=.2)
    track.ingest(fake_packet('B|2|SHIFT-G|ACTIONBUTTON7|macro|9|Bandage > Heavy Linen Bandage',3),mono=.4)
    track.input('key_down',1,key='2',chord='2')
    assert track.counts['attempts']==1 and track.counts['confirmed']==0
    track.ingest(fake_packet('A|Food|present',4),mono=2)
    assert track.counts['confirmed']==1
    track.input('key_down',3,key='g',chord='shift+g')
    assert track.counts['confirmed']==1
    track.ingest(fake_packet('A|Recently Bandaged|present',5),mono=4)
    assert track.counts['confirmed']==2
    assert track.bindings['SHIFT-G'].ambiguous is True
    assert any(ev=='semantic_outcome' for ev,_ in events)


def test_failed_cast_and_unknown_macro():
    t=ActionSemanticTracker()
    t.ingest(fake_packet('R|1|1',1),0)
    t.ingest(fake_packet('B|1|SHIFT-E|ACTIONBUTTON8|spell|17|Power Word: Shield',2),0.2)
    t.input('key_down',1,key='e',chord='shift+e')
    t.ingest(fake_packet('F|17|Power Word: Shield',3),2)
    assert t.counts['failed']==1
    t.input('key_down',3,key='e',chord='shift+e')
    t.ingest(fake_packet('S|17|Power Word: Shield',4),4)
    assert t.counts['confirmed']==1
    t.ingest(fake_packet('B|2|SHIFT-G|ACTIONBUTTON9|macro|6|Bandage',5),5)
    assert t.counts['confirmed']==1  # remapping alone must never verify usage
    assert t.generation==2 and 'SHIFT-E' not in t.bindings


def test_semantics_record_saved_and_no_model_control(tmp_path):
    rec=SessionRecorder(tmp_path, 'demonstration')
    rec.ingest_semantic(fake_packet('B|1|2|ACTIONBUTTON2|item|117|Food',2),mono=0.1)
    rec.raw_key('2', True, mono=.4)
    rec.ingest_semantic(fake_packet('A|Food|present',3),mono=.7)
    rec.close()
    data=json.loads((rec.path/'action_semantics.json').read_text())
    assert data['bindings'][0]['key']=='2'
    assert data['counts']['confirmed']==1
    lines=(rec.path/'events.jsonl').read_text()
    assert 'semantic_attempt' in lines and 'semantic_outcome' in lines
    # Advisory-only engine and training gate remain unchanged.
    from priestbot.learning import promote_advisory
    import pytest
    with pytest.raises((RuntimeError,FileNotFoundError,ValueError)):
        promote_advisory(tmp_path,'unapproved')


def test_wow_binding_chords_and_uncertainty():
    assert wow_binding('shift+g')=='SHIFT-G'
    assert wow_binding('ctrl+shift+e')=='CTRL-SHIFT-E'
    assert wow_binding('2')=='2'
    assert wow_binding('shift_l')==''
    track=ActionSemanticTracker()
    track.input('key_down',1,key='2',chord='2')
    track.ingest(fake_packet('S|8092|Mind Blast',1),mono=2)
    assert track.counts['confirmed']==0  # cannot prove unrelated unmatched spell
    assert track.counts['unmatched_events']==1
