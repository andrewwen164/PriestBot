"""Optional GUI smoke test: run via pytest on a machine with Tk display/Xvfb."""
import tkinter as tk
import pytest
from PIL import Image
from priestbot.calibrator import BarCalibrator


def test_zoomable_calibrator_saves_exact_source_pixels():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No graphical Tk display")
    root.withdraw()
    result = []
    dialog = BarCalibrator(root, Image.new("RGB", (600, 300), "gray"), -1920, 0,
                           complete=result.append)
    dialog.update()
    boxes = (("player_health", (100, 40, 300, 50)),
             ("player_mana", (100, 70, 300, 80)),
             ("target_health", (350, 40, 500, 55)))
    for name, bounds in boxes:
        dialog._set_selection(name, bounds)
    dialog.save()
    assert len(result) == 1
    assert result[0]["player_health"].left == -1820
    assert result[0]["player_health"].width == 200
    assert result[0]["player_mana"].height == 10
    assert result[0]["target_health"].left == -1570
    root.destroy()
