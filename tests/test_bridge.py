"""End-to-end rendering/decoding tests with synthetic pixel telemetry."""
import numpy as np
import pytest
from PIL import Image
from priestbot.bridge import decode_bridge, BridgeNotFound


def mock_panel(hp=1.0, mana=.72, target=.42, scale=1, x=55, y=37, corrupted=False):
    canvas = np.zeros((380, 600, 3), dtype=np.uint8)
    canvas[:] = (37, 44, 55)
    panel = np.zeros((78, 160, 3), dtype=np.uint8)
    panel[0:12, 0:12] = (255, 0, 255)
    panel[0:12, 16:28] = (0, 255, 255)
    panel[0:12, 32:44] = (255, 255, 0)
    colors = [(0, 255, 0), (0, 97, 255), (255, 0, 0)]
    for i, percent in enumerate((hp, mana, target)):
        yy = 20+i*20
        panel[yy:yy+12, :160] = (25, 25, 25)
        panel[yy:yy+12, :round(160*percent)] = colors[i]
    if corrupted:
        panel[40:52, :160] = (125, 125, 125)
    panel_image = Image.fromarray(panel).resize((160*scale, 78*scale), Image.Resampling.NEAREST)
    canvas[y:min(y+78*scale, 380), x:min(x+160*scale, 600)] = np.asarray(panel_image)[:max(0, min(380-y, 78*scale)), :max(0, min(600-x, 160*scale))]
    return canvas


@pytest.mark.parametrize('scale', [1,2,3])
@pytest.mark.parametrize('hp,mana,target', [(.85,.70,.20),(1,1,0),(.33,.05,.99)])
def test_decode_scaled_hp_mana_target(hp,mana,target,scale):
    image=mock_panel(hp,mana,target,scale)
    actual=decode_bridge(image)
    assert abs(actual.observation.hp - hp) < .01
    assert abs(actual.observation.mana - mana) < .01
    assert abs(actual.observation.target_hp - target) < .01
    assert (actual.marker_x, actual.marker_y)==(55,37)
    assert actual.scale==scale


def test_no_marker_fails_closed():
    with pytest.raises(BridgeNotFound):
        decode_bridge(np.zeros((100,150,3),dtype=np.uint8))


def test_bad_bar_fails_closed():
    with pytest.raises(BridgeNotFound):
        decode_bridge(mock_panel(corrupted=True))


def test_offscreen_marker_fails_closed():
    image = mock_panel(x=490)
    # Make sure a truncated panel is not mistaken for complete telemetry.
    with pytest.raises(BridgeNotFound):
        decode_bridge(image)
