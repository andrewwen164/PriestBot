"""Screenshot-coordinate geometry independent of Tk and Windows.

Image coordinates are *unscaled original screenshot pixels*. Canvas coordinates
may be fractional after zooming; never persist canvas-space coordinates.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil, floor


@dataclass
class ZoomView:
    image_width: int
    image_height: int
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    min_zoom: float = 0.05
    max_zoom: float = 16.0

    def image_to_canvas(self, ix: float, iy: float) -> tuple[float, float]:
        return ix * self.zoom + self.offset_x, iy * self.zoom + self.offset_y

    def canvas_to_image(self, cx: float, cy: float) -> tuple[float, float]:
        return (cx - self.offset_x) / self.zoom, (cy - self.offset_y) / self.zoom

    def constrain(self, canvas_width: int, canvas_height: int) -> None:
        """Keep the screenshot visible; center when smaller than viewport."""
        displayed_w = self.image_width * self.zoom
        displayed_h = self.image_height * self.zoom
        if displayed_w <= canvas_width:
            self.offset_x = (canvas_width - displayed_w) / 2
        else:
            self.offset_x = min(0.0, max(canvas_width - displayed_w, self.offset_x))
        if displayed_h <= canvas_height:
            self.offset_y = (canvas_height - displayed_h) / 2
        else:
            self.offset_y = min(0.0, max(canvas_height - displayed_h, self.offset_y))

    def fit(self, canvas_width: int, canvas_height: int, padding: int = 12) -> None:
        self.zoom = min(
            self.max_zoom,
            max(self.min_zoom, min(
                max(1, canvas_width - 2 * padding) / self.image_width,
                max(1, canvas_height - 2 * padding) / self.image_height,
            )),
        )
        self.offset_x = (canvas_width - self.image_width * self.zoom) / 2
        self.offset_y = (canvas_height - self.image_height * self.zoom) / 2

    def zoom_at(self, new_zoom: float, cx: float, cy: float,
                canvas_width: int, canvas_height: int) -> None:
        """Keep the original screenshot point under the pointer fixed."""
        ix, iy = self.canvas_to_image(cx, cy)
        self.zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        self.offset_x = cx - ix * self.zoom
        self.offset_y = cy - iy * self.zoom
        self.constrain(canvas_width, canvas_height)

    def pan(self, dx: float, dy: float, canvas_width: int, canvas_height: int) -> None:
        self.offset_x += dx
        self.offset_y += dy
        self.constrain(canvas_width, canvas_height)

    def drag_rect(self, start: tuple[float, float], end: tuple[float, float]) -> tuple[int, int, int, int]:
        """Return image-pixel bounds (left, top, right, bottom), clamped to image."""
        a = self.canvas_to_image(*start)
        b = self.canvas_to_image(*end)
        x1 = max(0, min(self.image_width, floor(min(a[0], b[0]))))
        y1 = max(0, min(self.image_height, floor(min(a[1], b[1]))))
        x2 = max(0, min(self.image_width, ceil(max(a[0], b[0]))))
        y2 = max(0, min(self.image_height, ceil(max(a[1], b[1]))))
        return x1, y1, x2, y2
