"""Conservative, game-window-only visual features for *offline* learning.

No screenshots of other windows, no memory access and no autonomous control.
Hostile-nameplate rectangles are CANDIDATES based on red bar geometry, not
verified NPCs. Never use these to issue game inputs without further validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class NameplateCandidate:
    x: float  # center normalized to [0,1]
    y: float
    width: float
    height: float
    confidence: float
    track_id: int = 0

    def as_dict(self):
        return {"x": round(self.x, 4), "y": round(self.y, 4),
                "width": round(self.width, 4), "height": round(self.height, 4),
                "confidence": round(self.confidence, 3), "track_id": self.track_id}


def detect_red_nameplates(image: Image.Image, *, max_results: int = 12) -> list[NameplateCandidate]:
    """Find long, thin saturated red bars. A visual hint, NOT an NPC identifier.

    Operates on a small resized copy; excludes most bottom action-bar UI and
    leftmost 15% where PriestBridge's optical panel usually sits.
    """
    src_w, src_h = image.size
    if src_w < 160 or src_h < 90:
        return []
    scale = min(1.0, 480 / src_w)
    w = max(120, round(src_w * scale))
    h = max(70, round(src_h * scale))
    rgb = np.asarray(image.convert("RGB").resize((w, h), Image.Resampling.BILINEAR), dtype=np.int16)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (red >= 105) & (red >= green * 1.60) & (red >= blue * 1.48) & (green < 135)
    mask[int(h * .76):] = False
    mask[:int(h * .12), :int(w * .15)] = False
    # Count runs on each row; merge nearby rows when their x positions overlap.
    runs = []
    minimum_width = max(11, int(w * .018))
    for yy in range(int(h * .06), int(h * .76)):
        row = mask[yy]
        edges = np.diff(np.r_[False, row, False].astype(np.int8))
        for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            width = int(end - start)
            if minimum_width <= width <= int(w * .32):
                runs.append((int(start), yy, int(end), yy + 1))
    # Coalesce consecutive red rows belonging to the same bar. Some textures
    # have one-pixel gaps, so allow 2 rows and 4 pixels horizontal discrepancy.
    components = []
    for x1, y1, x2, y2 in runs:
        found = None
        for comp in reversed(components[-100:]):
            if 0 <= y1 - comp[3] <= 2 and max(x1, comp[0]) < min(x2, comp[2]) - 3:
                found = comp
                break
        if found is None:
            components.append([x1, y1, x2, y2, 1])
        else:
            found[0] = min(found[0], x1)
            found[2] = max(found[2], x2)
            found[3] = y2
            found[4] += 1
    detections = []
    seen = []
    for x1, y1, x2, y2, n in components:
        ww, hh = x2 - x1, y2 - y1
        if ww < minimum_width or ww > w * .32 or hh > max(16, h * .045) or ww / max(1, hh) < 3.4:
            continue
        cx, cy = (x1 + x2) / (2*w), (y1 + y2) / (2*h)
        if any(abs(cx-x) < .02 and abs(cy-y) < .012 for x, y in seen):
            continue
        seen.append((cx, cy))
        # Score reflects visual bar shape only, not certainty that this is a mob.
        conf = min(.90, .30 + min(ww / max(w * .09, 1), 1) * .35 + (n > 1) * .15)
        detections.append(NameplateCandidate(cx, cy, ww / w, hh / h, float(conf)))
    return sorted(detections, key=lambda p: p.confidence, reverse=True)[:max_results]


class NameplateTracker:
    """Association of nearby 2D detections; resets when the game loses focus."""
    def __init__(self):
        self.previous: list[NameplateCandidate] = []
        self.next_id = 1

    def reset(self):
        self.previous = []

    def update(self, detections: list[NameplateCandidate]) -> list[NameplateCandidate]:
        used = set()
        result = []
        for candidate in detections:
            choices = sorted(((hypot(candidate.x - p.x, candidate.y - p.y), p)
                             for p in self.previous if p.track_id not in used),
                             key=lambda pair: pair[0])
            if choices and choices[0][0] < .085:
                track_id = choices[0][1].track_id
            else:
                track_id = self.next_id
                self.next_id += 1
            used.add(track_id)
            result.append(NameplateCandidate(candidate.x, candidate.y, candidate.width,
                                              candidate.height, candidate.confidence, track_id))
        self.previous = result
        return result


def estimate_scene_shift(previous: Image.Image, current: Image.Image, *, max_shift: int = 6) -> dict:
    """Approximate global scene translation between frames (screen pixels at 96x54).

    Can reveal whether the scene moved; cannot by itself distinguish camera
    turning from character strafing. Confidence remains low in blank scenes.
    """
    def prepare(im):
        small = np.asarray(im.convert('L').resize((96,54), Image.Resampling.BILINEAR), np.float32)
        return small[7:40, 12:84] / 255.0
    a, b = prepare(previous), prepare(current)
    if float(a.std()) < .018 or float(b.std()) < .018:
        return {'dx': 0, 'dy': 0, 'confidence': 0.0}
    best = (float('inf'), 0, 0)
    for dy in range(-max_shift, max_shift+1):
        for dx in range(-max_shift, max_shift+1):
            aa = a[max(0, -dy):a.shape[0]-max(0,dy), max(0, -dx):a.shape[1]-max(0,dx)]
            bb = b[max(0,dy):b.shape[0]-max(0,-dy), max(0,dx):b.shape[1]-max(0,-dx)]
            if aa.size == 0:
                continue
            delta = float(np.mean((aa-bb)**2))
            if delta < best[0]:
                best = (delta, dx, dy)
    # Need correlation gain compared with zero-shift to call this motion.
    zero = float(np.mean((a-b)**2))
    confidence = max(0.0, min(.95, (zero-best[0]) / max(zero, 1e-5)))
    return {'dx': int(best[1]), 'dy': int(best[2]), 'confidence': round(confidence,3)}
