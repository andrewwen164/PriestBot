"""Conservative color/geometry-based bar suggestions for *review* in calibration UI.

Never auto-apply to live controls. It detects filled horizontal colored strips,
not the full empty bar track. Works best with 100% HP/mana/target HP and a
standard WoW layout; customized nameplates and UI skins need manual boxes.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class BarSuggestion:
    box: tuple[int, int, int, int]  # original screenshot coordinates, x1/y1/x2/y2
    confidence: float  # heuristic, NOT a calibrated probability
    explanation: str


@dataclass(frozen=True)
class _Candidate:
    kind: str
    box: tuple[int, int, int, int]
    area: int


def _candidates(image: Image.Image) -> list[_Candidate]:
    """Extract sufficiently long, thick horizontal single-color segments."""
    im = image.convert('RGB')
    # Bound processing on 4K/multi-monitor screenshots; preserve exact scaling.
    scale = min(1.0, 1800 / max(1, im.width))
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.BILINEAR)
    arr = np.asarray(im, dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    color_masks = {
        'green': (g > 78) & (g > r * 1.38) & (g > b * 1.23),
        'blue': (b > 85) & (b > r * 1.55) & (b > g * 1.17),
        'red': (r > 85) & (r > g * 1.4) & (r > b * 1.28),
        'yellow': (r > 105) & (g > 72) & (b < (r * .68)) & (r > (g * .83)),
    }
    h, w = arr.shape[:2]
    min_w = max(30, int(w * .027))
    # Samples grouped into vertical strips; semi-transparent text and image borders
    # can make suggestions imperfect; user must review and redraw if necessary.
    out = []
    for kind, mask in color_masks.items():
        active = []  # (x1, x2, first_y, last_y, count)
        finished = []
        for y in range(0, h, 2):
            row = mask[y]
            transitions = np.diff(np.r_[False, row, False].astype(np.int8))
            starts = np.flatnonzero(transitions == 1)
            ends = np.flatnonzero(transitions == -1)
            runs = [(int(a), int(z)) for a, z in zip(starts, ends)
                    if min_w <= z-a <= min(w * .50, 900)]
            touched = set()
            for a, z in runs:
                matched = -1
                best_dist = float('inf')
                for idx, (u, v, fy, ly, n) in enumerate(active):
                    if idx in touched or y - ly > 4:
                        continue
                    overlap = max(0, min(z, v) - max(a, u))
                    size_ratio = min(v-u, z-a) / max(v-u, z-a)
                    if overlap / max(1, min(v-u, z-a)) > .78 and size_ratio > .74:
                        dist = abs(a-u) + abs(z-v)
                        if dist < best_dist:
                            matched, best_dist = idx, dist
                if matched >= 0:
                    u, v, fy, ly, n = active[matched]
                    active[matched] = (min(a, u), max(z, v), fy, y, n+1)
                    touched.add(matched)
                else:
                    active.append((a,z,y,y,1))
                    touched.add(len(active)-1)
            current = []
            for idx, item in enumerate(active):
                if idx in touched or y-item[3] <= 4:
                    current.append(item)
                else:
                    finished.append(item)
            active = current
        finished += active
        for a,z,fy,ly,n in finished:
            # 2+ sampled rows = at least ~4px. Reject tiny UI accents and buttons.
            height = ly - fy + 2
            if n < 2 or height < 4 or z-a < min_w:
                continue
            if (z-a) / height < 4 or height > 45:
                continue
            if (z-a) > w*.50:
                continue
            # Crop inward one pixel if possible, avoiding bright borders.
            src = (max(0, round(a / scale)), max(0, round(fy / scale)),
                   min(image.width, round(z / scale)), min(image.height, round((ly+2) / scale)))
            out.append(_Candidate(kind, src, (z-a)*height))
    return out


def _center(c):
    x1,y1,x2,y2 = c.box
    return ((x1+x2)/2, (y1+y2)/2)


def suggest_bars(image: Image.Image) -> dict[str, BarSuggestion]:
    """Suggest up to three regions. No guess is returned if confidence is too low.

    This is not a UI framework detector. It only produces boxes on solid colored
    portions of bars; always verify the full track before saving.
    """
    w, h = image.size
    if w < 300 or h < 200:
        return {}
    cand = _candidates(image)
    upper = [c for c in cand if _center(c)[1] < h*.77]
    if not upper:
        return {}

    def plausible(c):
        x1, y1, x2, y2 = c.box
        return 55 <= x2-x1 <= min(720,w*.5) and 4 <= y2-y1 <= 65

    upper = [c for c in upper if plausible(c)]
    if not upper:
        return {}
    # Character frames are usually near upper left. Use a lenient prior so
    # users with customized frame positions can fall back to manual calibration.
    green = [c for c in upper if c.kind == 'green']
    blue = [c for c in upper if c.kind == 'blue']
    if not green or not blue:
        return {}

    pairs = []
    for hp in green:
        for mana in blue:
            hx, hy = _center(hp)
            mx, my = _center(mana)
            hw = hp.box[2]-hp.box[0]; mw = mana.box[2]-mana.box[0]
            # Same unit frame: horizontal alignment, near-equal widths,
            # mana generally just below player health bar.
            if 0 < my-hy < max(90, h*.09) and abs(hx-mx) < max(60, hw*.4):
                width = min(hw,mw) / max(hw,mw)
                if width < .62:
                    continue
                score = ((min(hw,300)/300)*1.2 + width
                         + (1 - abs(hx-mx)/max(65,hw*.5))
                         + (1 - min(1, (my-hy)/max(100,h*.11)))
                         + (1.1 if hx < w*.55 else 0)
                         + (0.3 if hy < h*.40 else 0))
                pairs.append((score, hp, mana))
    if not pairs:
        return {}
    _, hp, mana = max(pairs, key=lambda t:t[0])
    result = {
        'player_health': BarSuggestion(hp.box,.68,'Likely green player HP bar; verify entire bar track'),
        'player_mana': BarSuggestion(mana.box,.68,'Likely blue mana bar; verify entire bar track'),
    }
    hx, hy = _center(hp)
    targets = []
    for c in upper:
        if c in (hp, mana) or c.kind not in ('red','green','yellow'):
            continue
        cx,cy = _center(c)
        # Different position from player's own health bar; target might be
        # green or red depending on UI skin/classic client configuration.
        if abs(cx-hx) < max(95,w*.07) and abs(cy-hy) < 80:
            continue
        tw = c.box[2]-c.box[0]
        score = (min(tw,300)/300)*1.4 + (.7 if c.kind=='red' else .2)
        score += .7 if cx > hx + 80 else 0
        score += .3 if cy < h*.40 else 0
        score -= 1 if cx > w*.9 else 0
        targets.append((score,c))
    if targets:
        score, target = max(targets,key=lambda t:t[0])
        if score >= .7:
            result['target_health'] = BarSuggestion(target.box,.48,
                'Possible target HP bar; target must be alive and near 100% HP; check manually')
    return result
