"""Decode PriestBridge addon-drawn native status bars from a screenshot.

This does NOT read WoW process memory or the game network. Forever secret values
may be displayed by the native StatusBar UI without being readable by Lua.
The pixel decoder uses the displayed bars and a three-block visual sentinel.

Fail closed if the sentinel is missing or obscured, or if a bar's content doesn't
match the expected color/track palette. The panel can be anywhere on screen.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .engine import Observation


class BridgeNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class BridgeReading:
    observation: Observation
    marker_x: int
    marker_y: int
    scale: float


def _marker_pixel(rgb, x, y, color):
    if x < 0 or y < 0 or y >= rgb.shape[0] or x >= rgb.shape[1]:
        return False
    r, g, b = [int(v) for v in rgb[y, x, :3]]
    if color == 'magenta':
        return r >= 225 and b >= 225 and g < 55
    if color == 'cyan':
        return g >= 225 and b >= 225 and r < 55
    if color == 'yellow':
        return r >= 225 and g >= 225 and b < 55
    return False


def _find_marker(rgb: np.ndarray):
    magenta = (rgb[:, :, 0] >= 225) & (rgb[:, :, 1] < 55) & (rgb[:, :, 2] >= 225)
    ys, xs = np.nonzero(magenta)
    if not len(xs):
        raise BridgeNotFound('PriestBridge marker not visible. Is /pb show enabled?')
    # v0.14: examine every horizontal magenta RUN, not a sparse sample of
    # magenta pixels. Effects or other UI elements can create tens of thousands
    # of magenta pixels; the previous len(xs)//500 stride could jump entirely
    # over the real 12x12 sentinel on an otherwise valid screenshot.
    starts = magenta.copy()
    starts[:, 1:] &= ~magenta[:, :-1]
    ys, xs = np.nonzero(starts)
    # Vectorized prefilter: the marker has at least seven magenta pixels in a
    # row, so discard isolated spell particles before entering Python loops.
    possible = (xs + 6) < magenta.shape[1]
    possible &= magenta[ys, np.minimum(xs + 6, magenta.shape[1] - 1)]
    attempted = set()
    for y, x in zip(ys[possible], xs[possible]):
        x, y = int(x), int(y)
        left = x
        while left > 0 and magenta[y, left - 1]:
            left -= 1
        right = x
        while right + 1 < magenta.shape[1] and magenta[y, right + 1]:
            right += 1
        width = right - left + 1
        if not 7 <= width <= 72:
            continue
        cx = left + width // 2
        top = y
        while top > 0 and magenta[top - 1, cx]:
            top -= 1
        bottom = y
        while bottom + 1 < magenta.shape[0] and magenta[bottom + 1, cx]:
            bottom += 1
        height = bottom - top + 1
        if not (7 <= height <= 72 and .78 <= height / width <= 1.28):
            continue
        if (left, top) in attempted:
            continue
        attempted.add((left, top))
        # Marker width alone is unreliable under fractional UI scaling: the
        # outer magenta pixel can be interpolated below the color threshold.
        # The separation between the *centers* of the magenta and yellow
        # sentinels is 32 UI units and is much more stable.
        coarse_scale = width / 12.0
        center_y = top + round(6 * coarse_scale)
        if not (_marker_pixel(rgb, left + round(22 * coarse_scale), center_y, 'cyan')
                and _marker_pixel(rgb, left + round(38 * coarse_scale), center_y, 'yellow')):
            continue
        scan_end = min(rgb.shape[1], left + round(48 * coarse_scale) + 12)
        row = rgb[center_y, left:scan_end, :3]
        if len(row) < 35:
            continue
        mr, mg, mb = row[:, 0], row[:, 1], row[:, 2]
        yellow = np.flatnonzero((mr >= 225) & (mg >= 225) & (mb < 55))
        if len(yellow) < 5:
            continue
        marker_mid = (width - 1) / 2
        yellow_mid = (float(yellow[0]) + float(yellow[-1])) / 2
        scale = (yellow_mid - marker_mid) / 32
        if not (.75 * coarse_scale <= scale <= 1.25 * coarse_scale):
            continue
        if (_marker_pixel(rgb, left + round(6 * scale), center_y, 'magenta')
                and _marker_pixel(rgb, left + round(22 * scale), center_y, 'cyan')
                and _marker_pixel(rgb, left + round(38 * scale), center_y, 'yellow')):
            return left, top, scale
    raise BridgeNotFound('Found colored pixels but no valid PriestBridge marker.')


def _fraction(rgb: np.ndarray, x: int, top: int, scale: float, bar_y: int, kind: str):
    width = round(160 * scale)
    y = top + round((bar_y + 4) * scale)
    # Check two internal rows. Using the fill interior avoids top/bottom anti-aliasing.
    samples = []
    for dy in (0, max(1, round(3 * scale))):
        yy = y + dy
        if x < 0 or yy < 0 or yy >= rgb.shape[0] or x + width > rgb.shape[1]:
            raise BridgeNotFound('PriestBridge panel is partly off-screen.')
        samples.append(rgb[yy, x:x+width, :3])
    colors = np.mean(np.stack(samples, axis=0).astype(np.float32), axis=0)
    r, g, b = colors[:, 0], colors[:, 1], colors[:, 2]
    if kind == 'health':
        filled = (g >= 160) & (r <= 80) & (b <= 80)
    elif kind == 'mana':
        filled = (b >= 165) & (r <= 80) & (g >= 55) & (g <= 170)
    else:
        filled = (r >= 160) & (g <= 80) & (b <= 80)
    dark = (r <= 70) & (g <= 70) & (b <= 70)
    classification = filled | dark
    if float(np.mean(classification)) < .90:
        raise BridgeNotFound(f'{kind} bar is covered, scaled incorrectly, or rendered differently.')
    # One contiguous fill, followed by dark track; do not mistake arbitrary UI content for a bar.
    frac = float(np.mean(filled))
    if not (0.0 <= frac <= 1.0):
        raise BridgeNotFound(f'{kind} bar returned invalid fill value.')
    return frac


def _status(rgb: np.ndarray, x: int, y: int, scale: float):
    """Decode optional v0.7 signal pixels. Return None values for v0.6 addons."""
    def sample(px, size):
        sx, sy = x + round((px + size / 2) * scale), y + round(4 * scale)
        if sy < 0 or sy >= rgb.shape[0] or sx < 0 or sx >= rgb.shape[1]:
            raise BridgeNotFound('PriestBridge status strip partially off-screen.')
        return tuple(int(v) for v in rgb[sy, sx, :3])
    # A unique teal version marker distinguishes new signal reporting from
    # harmless empty/black UI pixels in the original v0.6 addon.
    r,g,b=sample(48,8)
    if not (r < 70 and 145 <= g <= 255 and 40 <= b <= 160):
        return None, None, None
    r,g,b=sample(60,10)
    if g > 180 and r < 90 and b < 90:
        casting=True
    elif 50 <= r <= 120 and 50 <= g <= 120 and 50 <= b <= 120:
        casting=False
    else:
        raise BridgeNotFound('Unrecognized casting-status color in PriestBridge.')
    r,g,b=sample(76,10)
    if r > 175 and 65 <= g <= 190 and b < 70:
        err='range'
    elif r > 125 and b > 170 and g < 80:
        err='los'
    elif r < 70 and 145 <= g <= 225 and b > 235:
        err='facing'
    elif r > 175 and g < 70 and b < 70:
        err='failed'
    elif 50 <= r <= 120 and 50 <= g <= 120 and 50 <= b <= 120:
        err=None
    else:
        raise BridgeNotFound('Unrecognized spell-error color in PriestBridge.')
    seq=0
    for i, px in enumerate((96,108,120,132)):
        r,g,b=sample(px,8)
        if r >= 200 and g >= 200 and b >= 200:
            seq |= (1 << i)
        elif not (35 <= r <= 105 and 35 <= g <= 105 and 35 <= b <= 105):
            raise BridgeNotFound('Unrecognized event counter colors in PriestBridge.')
    return casting, err, seq




def _v08(rgb: np.ndarray, x: int, y: int, scale: float):
    """Read appended v0.8 aura/success strip. Old addons return None fields."""
    def sample(px, size=8):
        sx = x + round((px + size/2) * scale)
        sy = y + round((84 + 4) * scale)
        if sx < 0 or sy < 0 or sy >= rgb.shape[0] or sx >= rgb.shape[1]:
            raise BridgeNotFound('PriestBridge v0.8 row clipped by screen')
        return tuple(int(v) for v in rgb[sy, sx, :3])

    # A v0.6/v0.7 root frame ends above y84 and has no new protocol marker.
    # A random pixel outside their panel must not accidentally enable v0.8.
    r,g,b = sample(0,8)
    if not (r < 65 and 135 <= g <= 215 and 135 <= b <= 215):
        return None,None,None,None,None

    def aura(px):
        r,g,b = sample(px,10)
        if g >= 190 and r < 75 and b < 75:
            return 'present'
        if r > 195 and g < 70 and b < 70:
            return 'absent'
        if r > 190 and 120 <= g <= 220 and b < 70:
            return 'estimated'
        if 40 <= r <= 120 and 40 <= g <= 120 and 40 <= b <= 120:
            return 'unknown'
        raise BridgeNotFound('Unrecognized aura status in PriestBridge v0.8')

    shield = aura(16)
    pain = aura(32)
    r,g,b = sample(48,10)
    if g >= 190 and r < 75 and b < 75: last='shield'
    elif r >= 195 and b >= 195 and g < 75: last='pain'
    elif r >= 195 and b >= 195 and g >= 195: last='smite'
    elif r >= 195 and 90 <= g <= 165 and b < 75: last='mind_blast'
    elif g >= 195 and b >= 195 and r < 75: last='heal'
    elif 40 <= r <= 120 and 40 <= g <= 120 and 40 <= b <= 120: last=None
    else: raise BridgeNotFound('Unrecognized success spell indicator')

    def bits(xs, counter_name):
        """Read each bit from several central pixels, not one fragile pixel.

        WoW's UI scaling may interpolate a pixel near a texture boundary.  The
        patch is strictly inside the 8-unit tile; genuinely unexpected colors
        still invalidate telemetry instead of silently changing the sequence.
        """
        value = 0
        for i, px in enumerate(xs):
            sx = x + round((px + 4) * scale)
            sy = y + round(88 * scale)
            radius = max(1, min(3, round(1.5 * scale)))
            if (sx - radius < 0 or sy - radius < 0 or
                    sx + radius >= rgb.shape[1] or sy + radius >= rgb.shape[0]):
                raise BridgeNotFound(f'PriestBridge {counter_name} counter clipped by screen')
            patch = rgb[sy-radius:sy+radius+1, sx-radius:sx+radius+1, :3]
            r, g, b = (int(v) for v in np.median(patch.reshape(-1, 3), axis=0))
            # Both palette colors are neutral gray; reject unrelated UI colors.
            neutral = max(r, g, b) - min(r, g, b) <= 30
            if neutral and min(r, g, b) >= 185:
                value |= 1 << i
            elif not (neutral and 25 <= min(r, g, b) and max(r, g, b) <= 125):
                raise BridgeNotFound(
                    f'Unrecognized v0.8 {counter_name} counter bit {i+1} '
                    f'at ({sx}, {sy}): RGB=({r},{g},{b}), scale={scale:.3f}. '
                    'Check that the entire PriestBridge panel is unobstructed.'
                )
        return value
    return shield,pain,last,bits((64,76,88,100), 'success'),bits((112,124,136,148), 'target')

def decode_bridge(rgb: np.ndarray) -> BridgeReading:
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError('RGB image expected')
    x, y, scale = _find_marker(rgb)
    hp = _fraction(rgb, x, y, scale, 20, 'health')
    mana = _fraction(rgb, x, y, scale, 40, 'mana')
    target_hp = _fraction(rgb, x, y, scale, 60, 'target')
    casting, err, seq = _status(rgb, x, y, scale)
    shield,pain,success,success_seq,target_seq = _v08(rgb,x,y,scale)
    obs = Observation(hp, mana, target_hp, casting, err, seq,
                      shield, pain, success, success_seq, target_seq)
    return BridgeReading(obs, x, y, scale)


def monitor_bridge(sct) -> BridgeReading:
    desktop = sct.monitors[0]  # full virtual desktop; supports negative monitor coordinates
    shot = sct.grab(desktop)
    arr = np.asarray(shot)[:, :, [2, 1, 0]]
    reading = decode_bridge(arr)
    return BridgeReading(reading.observation,
                         reading.marker_x + desktop['left'],
                         reading.marker_y + desktop['top'], reading.scale)
