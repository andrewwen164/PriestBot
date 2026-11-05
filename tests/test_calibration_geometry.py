from priestbot.calibration_geometry import ZoomView


def test_fit_entire_image_with_margin():
    view = ZoomView(3840, 2160)
    view.fit(1200, 750)
    assert view.zoom < 1
    assert view.offset_x >= 0
    assert view.offset_y >= 0
    assert view.offset_x + view.zoom * view.image_width <= 1200
    assert view.offset_y + view.zoom * view.image_height <= 750


def test_cursor_anchor_preserved_while_zooming():
    view = ZoomView(1920, 1080)
    view.fit(1000, 700)
    old = view.canvas_to_image(250, 340)
    view.zoom_at(view.zoom * 4, 250, 340, 1000, 700)
    new = view.canvas_to_image(250, 340)
    assert abs(old[0] - new[0]) < 1e-8
    assert abs(old[1] - new[1]) < 1e-8


def test_coordinate_roundtrip_even_after_pan_and_zoom():
    view = ZoomView(3840, 2160, zoom=3.0, offset_x=-500, offset_y=-700)
    view.pan(-17, 12, 1280, 720)
    cx, cy = view.image_to_canvas(211, 302)
    ix, iy = view.canvas_to_image(cx, cy)
    assert abs(ix - 211) < 1e-8
    assert abs(iy - 302) < 1e-8


def test_drag_uses_original_pixels_not_zoomed_canvas_pixels():
    view = ZoomView(1920, 1080, zoom=4.0, offset_x=-240, offset_y=-120)
    a = view.image_to_canvas(200, 100)
    b = view.image_to_canvas(300, 117)
    assert view.drag_rect(a, b) == (200, 100, 300, 117)
    assert view.drag_rect(b, a) == (200, 100, 300, 117)


def test_drag_clips_at_image_edge():
    view = ZoomView(200, 100, zoom=4.0, offset_x=0, offset_y=0)
    assert view.drag_rect((700, 200), (1000, 500)) == (175, 50, 200, 100)


def test_zoom_bounds_and_pan_clamping():
    view = ZoomView(500, 400)
    view.zoom_at(100, 100, 100, 700, 600)
    assert view.zoom == 16.0
    view.pan(1e6, 1e6, 700, 600)
    assert view.offset_x == 0
    assert view.offset_y == 0
    view.zoom_at(0.0001, 100, 100, 700, 600)
    assert view.zoom == 0.05
    assert view.offset_x > 0
    assert view.offset_y > 0
