"""Compact PriestBridge protocol: synthetic optical tests, no WoW client needed."""
import numpy as np
import pytest
from PIL import Image

from priestbot.bridge import BridgeNotFound, decode_bridge
from priestbot.semantic_bridge import decode_pixels, encode_for_test, monitor_semantics


def compact_panel(hp=.76, mana=.48, target=.34, packet=None, scale=1,
                  resample=Image.Resampling.NEAREST, bottom_right=False):
    panel = np.full((48, 350, 3), (27, 37, 48), dtype=np.uint8)

    def tile(x, y, w, h, rgb):
        panel[y:y+h, x:x+w] = rgb

    # Unchanged three-block sentinel, spell status and counters.
    for x, color in ((0, (255, 0, 255)), (16, (0, 255, 255)),
                     (32, (255, 255, 0))):
        tile(x, 0, 12, 12, color)
    tile(48, 0, 8, 8, (0, 204, 102))
    tile(60, 0, 10, 10, (77, 77, 77))
    tile(76, 0, 10, 10, (77, 77, 77))
    for x in (96, 108, 120, 132):
        tile(x, 0, 8, 8, (64, 64, 64))
    tile(156, 0, 8, 8, (38, 230, 102))  # compact-only sentinel

    for y, value, color in ((14, hp, (0, 255, 0)),
                            (21, mana, (0, 97, 255)),
                            (28, target, (255, 0, 0))):
        tile(0, y, 160, 4, (25, 25, 25))
        tile(0, y, round(160 * value), 4, color)

    tile(0, 37, 8, 8, (0, 179, 179))
    for x in (16, 32, 48):
        tile(x, 37, 10, 10, (77, 77, 77))
    for x in (64, 76, 88, 100, 112, 124, 136, 148):
        tile(x, 37, 8, 8, (64, 64, 64))

    tile(180, 0, 8, 8, (0, 191, 89))
    tile(196, 0, 8, 8, (191, 102, 0))
    if packet is not None:
        for i in range(32):
            col, row = i % 16, i // 16
            tile(180 + col*10, 14 + row*10, 8, 8,
                 tuple(packet[i*3:i*3+3]))

    width, height = round(350*scale), round(48*scale)
    resized = np.asarray(Image.fromarray(panel).resize(
        (width, height), resample))
    if bottom_right:
        canvas = np.full((600, 1000, 3), (20, 40, 60), dtype=np.uint8)
        x, y = canvas.shape[1] - width - 12, canvas.shape[0] - height - 12
    else:
        canvas = np.full((190, 810, 3), (20, 40, 60), dtype=np.uint8)
        x, y = 37, 23
    canvas[y:y+height, x:x+width] = resized
    return canvas


@pytest.mark.parametrize('scale', (.9, 1, 1.17, 1.5, 2))
@pytest.mark.parametrize('resample', (Image.Resampling.NEAREST, Image.Resampling.BILINEAR))
def test_compact_bar_and_semantic_round_trip(scale, resample):
    packet_bytes = encode_for_test('B|3|2|ACTIONBUTTON2|spell|585|Smite', 47)
    image = compact_panel(packet=packet_bytes, scale=scale, resample=resample)
    reading = decode_bridge(image)
    assert reading.layout == 'compact'
    assert (reading.marker_x, reading.marker_y) == (37, 23)
    assert abs(reading.scale - scale) < .08
    assert abs(reading.observation.hp - .76) < .01
    assert abs(reading.observation.mana - .48) < .01
    assert abs(reading.observation.target_hp - .34) < .01
    packet = decode_pixels(image, reading.marker_x, reading.marker_y,
                           reading.scale, layout=reading.layout)
    assert packet is not None
    assert packet.kind == 'B' and packet.sequence == 47
    assert packet.fields[2] == 'ACTIONBUTTON2'


def test_missing_compact_marker_does_not_silently_read_wrong_bars():
    image = compact_panel()
    image[23:31, 37+156:37+164] = (20, 40, 60)
    with pytest.raises(BridgeNotFound):
        decode_bridge(image)


def test_corrupted_compact_bar_fails_closed():
    image = compact_panel()
    image[23+21:23+25, 37:37+160] = (130, 130, 130)
    with pytest.raises(BridgeNotFound):
        decode_bridge(image)


def test_wrong_sidecar_layout_is_not_accepted():
    image = compact_panel(packet=encode_for_test('S|8092|Mind Blast', 3))
    assert decode_pixels(image, 37, 23, 1, layout='normal') is None


def test_monitor_semantics_grabs_the_new_compact_geometry():
    image = compact_panel(packet=encode_for_test('L|slot_cleared|1', 9), scale=1.17)
    reading = decode_bridge(image)

    class FakeSct:
        def grab(self, region):
            left, top = region['left'], region['top']
            width, height = region['width'], region['height']
            patch = image[top:top+height, left:left+width]
            assert patch.shape[:2] == (height, width)
            bgra = np.empty((height, width, 4), dtype=np.uint8)
            bgra[:, :, :3] = patch[:, :, ::-1]
            bgra[:, :, 3] = 255
            return bgra

    packet = monitor_semantics(FakeSct(), reading)
    assert packet is not None and packet.kind == 'L'
    assert packet.fields == ('slot_cleared', '1')


@pytest.mark.parametrize('scale', (1, 1.17, 1.5, 2))
def test_compact_bottom_right_optical_read_without_coordinate_calibration(scale):
    """Decoder must find the marker near the bottom-right on any UI scale."""
    packet_data = encode_for_test('T|hostile|alive', 13)
    image = compact_panel(packet=packet_data, scale=scale, bottom_right=True)
    reading = decode_bridge(image)
    assert reading.layout == 'compact'
    assert abs(reading.observation.hp - .76) < .02
    assert abs(reading.observation.mana - .48) < .02
    assert abs(reading.observation.target_hp - .34) < .02
    assert abs(reading.marker_x + round(350 * scale) - (image.shape[1] - 12)) < 3
    assert reading.marker_y > image.shape[0] // 2
    decoded = decode_pixels(image, reading.marker_x, reading.marker_y,
                            reading.scale, layout=reading.layout)
    assert decoded is not None and decoded.kind == 'T'
    assert decoded.sequence == 13


def _stamp_target_state(image, *, scale=1, exists=True, dead=False, marker=True,
                        panel_x=37, panel_y=23, row=37):
    """Synthetic PriestBridge v0.26 pixel flags on the validated panel."""
    def tile(x, rgb):
        left = panel_x + round(x * scale)
        top = panel_y + round(row * scale)
        width = max(1, round(8 * scale))
        image[top:top+width, left:left+width] = rgb
    if marker:
        tile(160, (0, 153, 255))
    def flag(value):
        return (0, 255, 0) if value is True else (
            (255, 0, 0) if value is False else (77, 77, 77))
    tile(168, flag(exists))
    tile(180, flag(dead))
    return image


@pytest.mark.parametrize('scale', (1, 1.17, 1.5, 2))
def test_v026_compact_target_state_roundtrip_at_zero_optical_hp(scale):
    image = compact_panel(target=0, scale=scale)
    _stamp_target_state(image, scale=scale, exists=True, dead=False)
    obs = decode_bridge(image).observation
    assert obs.target_hp == 0
    assert obs.target_exists is True
    assert obs.target_dead is False

    from priestbot.config import Config
    from priestbot.engine import PriestEngine
    engine = PriestEngine(Config(main_damage="wand", use_shield=False, use_pain=False))
    assert engine.update(obs, 0).action == "wand"
    assert engine.update(obs, 2).action is None

    _stamp_target_state(image, scale=scale, exists=True, dead=True)
    dead_obs = decode_bridge(image).observation
    assert dead_obs.target_dead is True
    assert engine.update(dead_obs, 4).action == "next_target"


def test_v026_legacy_and_secret_states_are_not_falsely_decoded():
    old = decode_bridge(compact_panel(target=0)).observation
    assert old.target_exists is None and old.target_dead is None
    image = compact_panel(target=0)
    _stamp_target_state(image, exists=True, dead=None)
    obs = decode_bridge(image).observation
    assert obs.target_exists is True and obs.target_dead is None
    _stamp_target_state(image, exists=None, dead=None)
    obs = decode_bridge(image).observation
    assert obs.target_exists is None and obs.target_dead is None
    _stamp_target_state(image, exists=False, dead=False)
    with pytest.raises(BridgeNotFound):
        decode_bridge(image)


def test_v026_normal_layout_target_state():
    panel = np.full((102, 270, 3), (27, 37, 48), dtype=np.uint8)
    def tile(x, y, w, h, rgb):
        panel[y:y+h, x:x+w] = rgb
    for x, color in ((0,(255,0,255)),(16,(0,255,255)),(32,(255,255,0))):
        tile(x,0,12,12,color)
    tile(48,0,8,8,(0,204,102))
    tile(60,0,10,10,(77,77,77))
    tile(76,0,10,10,(77,77,77))
    for x in (96,108,120,132):
        tile(x,0,8,8,(64,64,64))
    for y,value,color in ((20,.85,(0,255,0)),(40,.7,(0,97,255)),(60,0,(255,0,0))):
        tile(0,y,160,12,(25,25,25))
        tile(0,y,round(160*value),12,color)
    tile(0,84,8,8,(0,179,179))
    for x in (16,32,48):
        tile(x,84,10,10,(77,77,77))
    for x in (64,76,88,100,112,124,136,148):
        tile(x,84,8,8,(64,64,64))
    tile(160,84,8,8,(0,153,255))
    tile(168,84,8,8,(0,255,0))
    tile(180,84,8,8,(255,0,0))
    image = np.full((240, 420, 3), (20, 40, 60), dtype=np.uint8)
    image[24:126, 32:302] = panel
    result = decode_bridge(image)
    assert result.layout == 'normal'
    assert result.observation.target_hp == 0
    assert result.observation.target_exists is True
    assert result.observation.target_dead is False
