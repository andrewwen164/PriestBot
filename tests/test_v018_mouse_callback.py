"""App callbacks must never turn off-game mouse events into training data."""
from types import SimpleNamespace
import json

from PIL import Image

from priestbot.app import App
from priestbot.engine import Observation
from priestbot.learning import SessionRecorder
import priestbot.input_control as ic


def test_rmb_callback_only_when_game_focused(monkeypatch, tmp_path):
    r=SessionRecorder(tmp_path, 'demonstration', screenshot_period_s=.01)
    r.observe(Observation(.9, .9, 1), image=Image.new('RGB',(100,100)), mono=10)
    stub=SimpleNamespace(demo_recorder=r,
                         cfg=SimpleNamespace(learning_record_mouse=True,
                             learning_record_corrections=True,allowed_processes=['wow.exe']))
    focus=[True]
    monkeypatch.setattr(ic, 'game_has_focus', lambda allowed: focus[0])
    # Real callbacks use time.monotonic; fake a time base close to snapshot.
    import priestbot.app as ap
    t=[10.1]
    monkeypatch.setattr(ap.time,'monotonic',lambda: t[0])
    right=SimpleNamespace(name='right')
    App._demo_mouse_click(stub,200,200,right,True)
    t[0]=10.15
    App._demo_mouse_moved(stub,230,200)
    focus[0]=False
    t[0]=10.2
    App._demo_mouse_click(stub,230,200,right,False)
    r.close()
    logs=[json.loads(x) for x in (r.path/'events.jsonl').read_text().splitlines()]
    assert not [x for x in logs if x['event']=='correction']
