"""v0.14 transient marker failure handling and complete search coverage."""
import numpy as np
import pytest
from priestbot.telemetry_guard import TelemetryGuard
from priestbot.bridge import decode_bridge, BridgeNotFound
from test_v08_aura_success import panel_v08


def test_guard_requires_two_good_frames_before_resuming():
    guard = TelemetryGuard(grace_s=1.5, recovery_frames=2)
    assert guard.succeeded(10).state == 'good'
    assert guard.failed(10.0, 'marker missing').state == 'pause'
    assert guard.succeeded(10.3).state == 'pause'
    assert guard.succeeded(10.6).state == 'recovered'
    assert guard.succeeded(10.9).state == 'good'


def test_guard_interleaved_failures_reset_recovery_streak():
    guard = TelemetryGuard(1.5, 2)
    assert guard.failed(10, 'marker absent').state == 'pause'
    assert guard.succeeded(10.3).state == 'pause'
    assert guard.failed(10.6, 'bad status color').state == 'pause'
    assert guard.succeeded(10.9).state == 'pause'
    assert guard.succeeded(11.2).state == 'recovered'


def test_guard_stops_on_sustained_failure_or_late_recovery():
    guard = TelemetryGuard(1.5, 2)
    guard.failed(1.0, 'bad marker')
    assert guard.failed(2.6, 'bad marker').state == 'stop'
    guard2 = TelemetryGuard(1.5, 2)
    guard2.failed(1.0, 'bad marker')
    assert guard2.succeeded(2.6).state == 'stop'
    assert guard2.last_error == 'bad marker'


def test_guard_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        TelemetryGuard(grace_s=0)
    with pytest.raises(ValueError):
        TelemetryGuard(recovery_frames=0)


def test_marker_found_with_many_magenta_pixels_elsewhere():
    image = panel_v08(seq=4, target_seq=5)
    # Add a bright magenta overlay in a different part of the screenshot.
    # It produces far more magenta candidate pixels than the small marker.
    image[200:350, 250:450] = (255, 0, 255)
    actual = decode_bridge(image)
    assert (actual.marker_x, actual.marker_y) == (70, 60)
    assert actual.observation.success_seq == 4
    assert actual.observation.target_seq == 5


def test_invalid_marker_is_still_rejected():
    image = panel_v08(seq=2)
    image[60:72, 70:82] = (0, 0, 0)
    with pytest.raises(BridgeNotFound):
        decode_bridge(image)
