"""Fail-closed recovery for brief visual telemetry interruptions.

The engine and input controller MUST NOT be called on a missed frame or while
confirming recovery. Two clean frames permit resumption if the gap is short;
otherwise caller stops with an alarm. No stale measurements are reused.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    state: str  # good | pause | recovered | stop
    elapsed_s: float = 0.0
    detail: str = ""


class TelemetryGuard:
    def __init__(self, grace_s: float = 1.5, recovery_frames: int = 2):
        if grace_s <= 0 or recovery_frames < 1:
            raise ValueError("grace_s must be positive; recovery_frames at least 1")
        self.grace_s = grace_s
        self.recovery_frames = recovery_frames
        self.missing_since: float | None = None
        self.valid_streak = 0
        self.last_error = ""

    def failed(self, now: float, reason: str) -> Check:
        if self.missing_since is None:
            self.missing_since = now
        self.last_error = reason
        self.valid_streak = 0
        elapsed = max(0., now - self.missing_since)
        if elapsed >= self.grace_s:
            return Check('stop', elapsed, reason)
        return Check('pause', elapsed, reason)

    def succeeded(self, now: float) -> Check:
        if self.missing_since is None:
            return Check('good')
        elapsed = max(0., now - self.missing_since)
        if elapsed >= self.grace_s:
            return Check('stop', elapsed, self.last_error)
        self.valid_streak += 1
        if self.valid_streak < self.recovery_frames:
            return Check('pause', elapsed, self.last_error)
        self.missing_since = None
        self.valid_streak = 0
        self.last_error = ""
        return Check('recovered', elapsed)
