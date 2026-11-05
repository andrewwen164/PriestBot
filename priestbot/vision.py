from __future__ import annotations
import numpy as np
from PIL import Image
from .config import Rect


def bar_fraction(rgb: np.ndarray) -> float | None:
    """Estimate filled percentage of a bright colored bar on dark background.

    Region MUST contain only bar interior, NOT its border/text/portrait.
    Returns None for an invalid/empty crop. Pure function, independently testable.
    This heuristic needs per-UI validation; it is not OCR or an addon API.
    """
    if rgb.ndim != 3 or rgb.shape[2] < 3 or rgb.shape[0] < 3 or rgb.shape[1] < 15:
        return None
    h, w = rgb.shape[:2]
    # Sample slightly above center to avoid centered unit frame text.
    rows = rgb[max(0, round(.18*h)):max(1, round(.38*h)), :, :3].astype(np.float32)
    if not len(rows):
        rows = rgb[:, :, :3].astype(np.float32)
    colors = np.median(rows, axis=0)
    maximum = colors.max(axis=1)
    minimum = colors.min(axis=1)
    saturation = np.divide(maximum-minimum, np.maximum(1., maximum))
    bright = maximum >= 52
    colored = saturation >= .28
    raw = bright & colored
    # Remove isolated frame details, preserving leading colored columns.
    if w >= 24:
        kernel = np.ones(5) / 5
        raw = np.convolve(raw.astype(float), kernel, mode="same") >= .6
    return max(0.0, min(1.0, float(np.count_nonzero(raw)) / w))


def rect_capture(sct, rect: Rect) -> np.ndarray:
    if rect.width < 15 or rect.height < 3:
        raise ValueError("Bar rectangles must be at least 15x3 pixels")
    shot = sct.grab({"left":rect.left,"top":rect.top,"width":rect.width,"height":rect.height})
    return np.asarray(shot)[:, :, [2, 1, 0]]  # BGRA -> RGB


def monitor_bars(sct, cfg):
    from .engine import Observation
    hp = bar_fraction(rect_capture(sct, cfg.player_health))
    mana = bar_fraction(rect_capture(sct, cfg.player_mana))
    target = bar_fraction(rect_capture(sct, cfg.target_health))
    if hp is None or mana is None or target is None:
        raise RuntimeError("Invalid bar calibration. Capture the bar interiors again.")
    return Observation(hp=hp, mana=mana, target_hp=target)


def full_screenshot(sct):
    desktop = sct.monitors[0]
    return Image.frombytes("RGB", (desktop["width"], desktop["height"]),
                           sct.grab(desktop).rgb), desktop["left"], desktop["top"]
