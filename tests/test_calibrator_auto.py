import tkinter as tk
import pytest
from PIL import Image, ImageDraw
from priestbot.calibrator import BarCalibrator


def test_auto_suggestion_requires_explicit_save(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('no graphical Tk display')
    root.withdraw()
    image = Image.new('RGB', (1280,720), (24,24,32))
    d = ImageDraw.Draw(image)
    d.rectangle((80,70,260,82), fill=(12,205,34))
    d.rectangle((80,91,260,102),fill=(20,80,215))
    d.rectangle((510,70,690,82), fill=(210,20,20))
    saved=[]
    from priestbot import calibrator
    monkeypatch.setattr(calibrator.messagebox, 'showinfo', lambda *args,**kwargs: None)
    dialog = BarCalibrator(root, image, -1280, 0, complete=saved.append)
    dialog.update()
    dialog.auto_suggest()
    assert len(dialog.selections)==3
    assert saved==[]
    dialog.preview_readings()
    assert '100%' in dialog.reading_status.get()
    dialog.save()
    assert len(saved)==1
    assert saved[0]['player_health'].left < 0
    root.destroy()
