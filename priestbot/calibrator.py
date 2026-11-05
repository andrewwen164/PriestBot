"""Zoomable screenshot calibration and optional automatic box suggestions.

Controls: left-drag draw, right-/middle-drag pan, wheel zoom at pointer,
Fit and 100% buttons, arrows nudge selected rectangle, Shift+arrows resize.
Only original screenshot pixel coordinates + virtual-desktop offsets are saved.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk

from .calibration_geometry import ZoomView
from .config import Rect


class BarCalibrator(tk.Toplevel):
    ITEMS = (
        ("player_health", "Your HEALTH bar", "#3efa70"),
        ("player_mana", "Your MANA bar", "#50c9ff"),
        ("target_health", "Enemy TARGET health bar", "#ffb546"),
    )
    MIN_WIDTH, MIN_HEIGHT = 15, 3  # pixels in the ORIGINAL screenshot

    def __init__(self, master, image: Image.Image, origin_x: int, origin_y: int,
                 complete, existing: dict[str, Rect | None] | None = None):
        super().__init__(master)
        self.title("Priest Farmer - Zoomable / assisted bar calibration")
        self.original = image.convert("RGB").copy()
        self.origin = (origin_x, origin_y)
        self.view = ZoomView(*self.original.size)
        self.complete = complete
        self.selections: dict[str, tuple[int, int, int, int]] = {}
        self.history: list[tuple[str, tuple[int, int, int, int] | None]] = []
        self.active_index = tk.IntVar(value=0)
        self.status = tk.StringVar()
        self.cursor_status = tk.StringVar(value="Move your pointer over the screenshot")
        self.zoom_label = tk.StringVar(value="Zoom: --")
        self.selection_status = tk.StringVar(value="")
        self.reading_status = tk.StringVar(value="Screenshot reading: select bars, then preview their estimated percentages.")
        self._fitted = False
        self._draw_start: tuple[float, float] | None = None
        self._draw_now: tuple[float, float] | None = None
        self._pan_start: tuple[int, int] | None = None
        self._image_handle: ImageTk.PhotoImage | None = None
        self._render_pending = False
        self._render_after_id = None

        if existing:
            for name, rect in existing.items():
                if rect is None or rect.width <= 0 or rect.height <= 0:
                    continue
                bounds = (rect.left - origin_x, rect.top - origin_y,
                          rect.left - origin_x + rect.width,
                          rect.top - origin_y + rect.height)
                if (0 <= bounds[0] < bounds[2] <= self.original.width
                        and 0 <= bounds[1] < bounds[3] <= self.original.height):
                    self.selections[name] = bounds

        self._build_ui()
        self._update_status()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(master)
        self.grab_set()
        self.focus_set()
        # Fit once the canvas has its final size.
        self.after(100, self._initial_fit)

    def _build_ui(self):
        desktop_w, desktop_h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{max(680, min(1390, desktop_w - 80))}x{max(550, min(880, desktop_h - 90))}")
        self.minsize(650, 475)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Draw the inside of each colored bar",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.status, wraplength=1250).pack(anchor="w", pady=(3, 6))

        bar = ttk.Frame(self, padding=(10, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text="Draw:").pack(side="left", padx=(0, 5))
        for index, (_, text, _) in enumerate(self.ITEMS):
            ttk.Radiobutton(bar, text=text, variable=self.active_index,
                            value=index, command=self._selected_changed).pack(side="left", padx=(0, 10))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=5)
        for title, command in (("−", lambda: self._zoom_button(1 / 1.5)),
                               ("+", lambda: self._zoom_button(1.5)),
                               ("Fit", self.fit),
                               ("100%", lambda: self._zoom_to(1.0)),
                               ("400%", lambda: self._zoom_to(4.0))):
            ttk.Button(bar, text=title, width=5, command=command).pack(side="left", padx=2)
        ttk.Label(bar, textvariable=self.zoom_label).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Auto suggest bars", command=self.auto_suggest).pack(side="right", padx=3)

        canvas_container = ttk.Frame(self, padding=(10, 8, 10, 0))
        canvas_container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_container, bg="#202329", cursor="crosshair",
                                highlightthickness=1, highlightbackground="#777777", takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._resized)
        self.canvas.bind("<ButtonPress-1>", self._draw_down)
        self.canvas.bind("<B1-Motion>", self._draw_motion)
        self.canvas.bind("<ButtonRelease-1>", self._draw_up)
        self.canvas.bind("<Motion>", self._pointer_motion)
        self.canvas.bind("<MouseWheel>", self._mouse_wheel)
        self.canvas.bind("<Button-4>", lambda ev: self._zoom_wheel_other(ev, 1))
        self.canvas.bind("<Button-5>", lambda ev: self._zoom_wheel_other(ev, -1))
        for button in (2, 3):
            self.canvas.bind(f"<ButtonPress-{button}>", self._pan_down)
            self.canvas.bind(f"<B{button}-Motion>", self._pan_move)
            self.canvas.bind(f"<ButtonRelease-{button}>", self._pan_up)
        # Keyboard shortcuts work as long as the calibrator has focus.
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0),
                            ("Up", 0, -1), ("Down", 0, 1)):
            self.bind(f"<{key}>", lambda ev, x=dx, y=dy: self._nudge(x, y))
            self.bind(f"<Shift-{key}>", lambda ev, x=dx, y=dy: self._nudge(x, y, resize=True))
        self.bind("<Escape>", lambda ev: self._cancel())
        self.bind("<Control-z>", lambda ev: self.undo())

        foot = ttk.Frame(self, padding=(10, 6, 10, 10))
        foot.pack(fill="x")
        ttk.Label(foot, text="Wheel: zoom at cursor  •  Right-drag: pan  •  Left-drag: draw  •  "
                              "Arrows: move 1px  •  Shift+arrows: resize 1px",
                  wraplength=1260).pack(anchor="w")
        ttk.Label(foot, textvariable=self.cursor_status, font=("Consolas", 9)).pack(anchor="w", pady=(3, 1))
        ttk.Label(foot, textvariable=self.selection_status, wraplength=1250).pack(anchor="w", pady=(0, 4))
        ttk.Label(foot, textvariable=self.reading_status, wraplength=1250).pack(anchor="w", pady=(0, 5))
        buttons = ttk.Frame(foot)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Preview screenshot readings", command=self.preview_readings).pack(side="left", padx=(0, 9))
        ttk.Button(buttons, text="Undo", command=self.undo).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Clear selected bar", command=self.clear_selected).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=(5, 0))
        self.save_button = ttk.Button(buttons, text="Save all 3 bars", command=self.save)
        self.save_button.pack(side="right")

    def _size(self) -> tuple[int, int]:
        return max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())

    def _initial_fit(self):
        if not self.winfo_exists():
            return
        if not self._fitted:
            self.fit()
            self._fitted = True

    def _resized(self, _ev=None):
        w, h = self._size()
        if not self._fitted:
            # Fit as soon as the real canvas geometry is known, so an early
            # user zoom cannot be overwritten by a late initial-fit timer.
            if w >= 200 and h >= 150:
                self.fit()
            return
        self.view.constrain(w, h)
        self._schedule_render()

    def fit(self):
        self.view.fit(*self._size())
        self._fitted = True
        self._schedule_render()

    def _zoom_button(self, factor: float):
        self._zoom_to(self.view.zoom * factor)

    def _zoom_to(self, level: float):
        w, h = self._size()
        self.view.zoom_at(level, w / 2, h / 2, w, h)
        self._schedule_render()

    def _mouse_wheel(self, ev):
        if ev.delta:
            self._zoom_at_pointer(ev.x, ev.y, 1.25 if ev.delta > 0 else 1 / 1.25)
        return "break"

    def _zoom_wheel_other(self, ev, direction):
        self._zoom_at_pointer(ev.x, ev.y, 1.25 if direction > 0 else 1 / 1.25)
        return "break"

    def _zoom_at_pointer(self, x: int, y: int, factor: float):
        w, h = self._size()
        self.view.zoom_at(self.view.zoom * factor, x, y, w, h)
        self._schedule_render()

    def _pan_down(self, ev):
        self.canvas.focus_set()
        self._pan_start = (ev.x, ev.y)
        self.canvas.configure(cursor="fleur")

    def _pan_move(self, ev):
        if self._pan_start is None:
            return
        previous_x, previous_y = self._pan_start
        self.view.pan(ev.x - previous_x, ev.y - previous_y, *self._size())
        self._pan_start = (ev.x, ev.y)
        self._schedule_render()

    def _pan_up(self, _ev):
        self._pan_start = None
        self.canvas.configure(cursor="crosshair")

    def _draw_down(self, ev):
        ix, iy = self.view.canvas_to_image(ev.x, ev.y)
        if not (0 <= ix < self.original.width and 0 <= iy < self.original.height):
            return
        self.canvas.focus_set()
        self._draw_start = (ev.x, ev.y)
        self._draw_now = self._draw_start
        self._schedule_render()

    def _draw_motion(self, ev):
        if self._draw_start is not None:
            self._draw_now = (ev.x, ev.y)
            self._schedule_render()
        self._pointer_motion(ev)

    def _draw_up(self, ev):
        if self._draw_start is None:
            return
        bounds = self.view.drag_rect(self._draw_start, (ev.x, ev.y))
        self._draw_start = None
        self._draw_now = None
        self._schedule_render()
        if not self._valid(bounds):
            messagebox.showwarning("Box too small",
                                   "Select at least 15 pixels wide and 3 pixels high "
                                   "in the original screenshot. Zoom further if necessary.",
                                   parent=self)
            return
        name = self.ITEMS[self.active_index.get()][0]
        self._set_selection(name, bounds)
        # Convenient next-step behavior, without saving until explicit confirmation.
        for idx in list(range(self.active_index.get() + 1, len(self.ITEMS))) + list(range(self.active_index.get())):
            if self.ITEMS[idx][0] not in self.selections:
                self.active_index.set(idx)
                break
        self._update_status()
        self._schedule_render()

    def _pointer_motion(self, ev):
        ix, iy = self.view.canvas_to_image(ev.x, ev.y)
        if 0 <= ix < self.original.width and 0 <= iy < self.original.height:
            self.cursor_status.set(f"Screenshot pixel: {math.floor(ix)}, {math.floor(iy)}    "
                                   f"Desktop pixel: {math.floor(ix) + self.origin[0]}, "
                                   f"{math.floor(iy) + self.origin[1]}")
        else:
            self.cursor_status.set("Pointer outside screenshot")

    @classmethod
    def _valid(cls, bounds):
        x1, y1, x2, y2 = bounds
        return (x2 - x1 >= cls.MIN_WIDTH and y2 - y1 >= cls.MIN_HEIGHT)

    def _set_selection(self, name, bounds):
        previous = self.selections.get(name)
        self.history.append((name, previous))
        if bounds is None:
            self.selections.pop(name, None)
        else:
            self.selections[name] = bounds
        self._update_status()

    def _selected_changed(self):
        self._update_status()
        self._schedule_render()
        self.canvas.focus_set()

    def undo(self):
        if not self.history:
            self.status.set("Nothing to undo yet.")
            return
        name, previous = self.history.pop()
        if previous is None:
            self.selections.pop(name, None)
        else:
            self.selections[name] = previous
        self.active_index.set(next(i for i, item in enumerate(self.ITEMS) if item[0] == name))
        self._update_status()
        self._schedule_render()

    def clear_selected(self):
        name = self.ITEMS[self.active_index.get()][0]
        if name in self.selections:
            self._set_selection(name, None)
            self._schedule_render()

    def _nudge(self, dx: int, dy: int, resize=False):
        name = self.ITEMS[self.active_index.get()][0]
        if name not in self.selections:
            return
        x1, y1, x2, y2 = self.selections[name]
        if resize:
            box = (x1, y1, x2 + dx, y2 + dy)
        else:
            box = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        if (0 <= box[0] < box[2] <= self.original.width
                and 0 <= box[1] < box[3] <= self.original.height and self._valid(box)):
            self._set_selection(name, box)
            self._schedule_render()
        return "break"

    def _update_status(self):
        current_name, current_title, _ = self.ITEMS[self.active_index.get()]
        ready = len(self.selections)
        self.status.set(f"{ready}/3 bars selected. Currently drawing: {current_title}. "
                        "You can redraw any bar by selecting its radio button.")
        self.save_button.configure(state="normal" if ready == len(self.ITEMS) else "disabled")
        summaries = []
        for name, title, _ in self.ITEMS:
            rect = self.selections.get(name)
            if rect:
                x1, y1, x2, y2 = rect
                summaries.append(f"{title}: {x2-x1}×{y2-y1}px")
            else:
                summaries.append(f"{title}: not selected")
        self.selection_status.set("  |  ".join(summaries))

    def _schedule_render(self):
        if self._render_pending:
            return
        self._render_pending = True
        self._render_after_id = self.after_idle(self._render)

    def _render(self):
        self._render_pending = False
        if not self.winfo_exists():
            return
        w, h = self._size()
        z = self.view.zoom
        ox, oy = self.view.offset_x, self.view.offset_y
        self.canvas.delete("all")
        # Only render the original-image region currently visible in the window.
        # This avoids constructing a huge 16x screenshot in RAM.
        left = max(0, math.floor(-ox / z) - 2)
        top = max(0, math.floor(-oy / z) - 2)
        right = min(self.original.width, math.ceil((w - ox) / z) + 2)
        bottom = min(self.original.height, math.ceil((h - oy) / z) + 2)
        if right > left and bottom > top:
            crop = self.original.crop((left, top, right, bottom))
            scaled_w = max(1, round((right - left) * z))
            scaled_h = max(1, round((bottom - top) * z))
            sample = Image.Resampling.NEAREST if z >= 1.0 else Image.Resampling.LANCZOS
            crop = crop.resize((scaled_w, scaled_h), sample)
            self._image_handle = ImageTk.PhotoImage(crop, master=self)
            x, y = self.view.image_to_canvas(left, top)
            self.canvas.create_image(round(x), round(y), anchor="nw", image=self._image_handle)
        self.zoom_label.set(f"Zoom: {z * 100:.0f}%")
        for idx, (name, title, color) in enumerate(self.ITEMS):
            if name not in self.selections:
                continue
            x1, y1, x2, y2 = self.selections[name]
            a, b = self.view.image_to_canvas(x1, y1)
            c, d = self.view.image_to_canvas(x2, y2)
            # Thicker border for the currently selected area.
            width = 3 if idx == self.active_index.get() else 2
            self.canvas.create_rectangle(a, b, c, d, outline=color, width=width)
            caption_y = b - 3 if b > 23 else d + 3
            self.canvas.create_text(a, caption_y, anchor="sw" if b > 23 else "nw",
                                    text=title, fill=color, font=("Segoe UI", 10, "bold"))
        if self._draw_start and self._draw_now:
            x1, y1 = self._draw_start
            x2, y2 = self._draw_now
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="white", width=2,
                                         dash=(5, 3))

    def preview_readings(self):
        """Preview readings on the *captured image*, before approving calibration."""
        import numpy as np
        from .vision import bar_fraction
        values = []
        for name, display, _ in self.ITEMS:
            if name not in self.selections:
                values.append(f"{display}: not selected")
                continue
            crop = self.original.crop(self.selections[name])
            fraction = bar_fraction(np.asarray(crop))
            values.append(f"{display}: {fraction:.0%}" if fraction is not None
                          else f"{display}: unreadable")
        self.reading_status.set("Captured screenshot only:  " + "  |  ".join(values))

    def auto_suggest(self):
        """Suggest only missing boxes; always require a visual review/save."""
        try:
            from .auto_bars import suggest_bars
            suggestions = suggest_bars(self.original)
        except Exception as exc:
            messagebox.showerror("Bar detection failed", str(exc), parent=self)
            return
        added = []
        for name, proposal in suggestions.items():
            if name not in self.selections and self._valid(proposal.box):
                self._set_selection(name, proposal.box)
                added.append(name)
        self._schedule_render()
        if added:
            self._update_status()
            self.status.set("SUGGESTED (not verified): " + ", ".join(added) +
                            ". Zoom in and fix the boxes so they include the full bar track, even any empty area. "
                            "Nothing has been saved yet.")
            self.active_index.set(next(i for i, (name, _, _) in enumerate(self.ITEMS)
                                       if name == added[0]))
        else:
            self.status.set("No new reliable bar suggestions. Keep your current selections or draw bars manually.")
        messagebox.showinfo("Review before saving",
            f"Suggested {len(added)} new box(es). Automatic detection only sees COLORED FILL, "
            "not the empty track. For best results, capture when player HP, mana and target HP "
            "are all full. Inspect at 400% and redraw any incomplete or wrong box. "
            "This button never saves or starts automation.", parent=self)

    def save(self):
        if len(self.selections) != len(self.ITEMS):
            messagebox.showwarning("Incomplete calibration", "Draw all three bars before saving.", parent=self)
            return
        result = {}
        for name, _, _ in self.ITEMS:
            x1, y1, x2, y2 = self.selections[name]
            if not self._valid((x1, y1, x2, y2)):
                messagebox.showerror("Invalid bar", f"The box for {name} is too small.", parent=self)
                return
            result[name] = Rect(self.origin[0] + x1, self.origin[1] + y1,
                                x2 - x1, y2 - y1)
        self.complete(result)
        self._finish()

    def _cancel(self):
        self._finish()

    def _finish(self):
        if self._render_after_id is not None:
            try:
                self.after_cancel(self._render_after_id)
            except (tk.TclError, ValueError):
                pass
        self.grab_release()
        self.destroy()
