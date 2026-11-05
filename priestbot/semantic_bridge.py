"""Optional read-only PriestBridge v0.21 optical action-semantics packets.

No game-memory access. Unlike combat telemetry, invalid semantic packets are
ignored rather than being used to halt a healthy PriestBot combat session.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

MAGIC = 166
VERSION = 1
TILE_COUNT = 32
PACKET_SIZE = TILE_COUNT * 3
PAYLOAD_MAX = PACKET_SIZE - 7


@dataclass(frozen=True)
class SemanticPacket:
    sequence: int
    kind: str
    fields: tuple[str, ...]
    payload: str


def encode_for_test(payload: str, sequence: int) -> bytes:
    """Byte-for-byte equivalent of the Lua sidecar, for protocol tests."""
    data = payload.encode('utf-8')[:PAYLOAD_MAX]
    seq = sequence % 65536
    checksum = (sum(data) + seq + len(data)) % 65536
    raw = bytes([MAGIC, VERSION, seq % 256, seq // 256,
                 len(data), checksum % 256, checksum // 256]) + data
    return raw.ljust(PACKET_SIZE, b'\0')


def decode_bytes(raw: bytes) -> SemanticPacket | None:
    if len(raw) != PACKET_SIZE or raw[0] != MAGIC or raw[1] != VERSION:
        return None
    seq = raw[2] + 256 * raw[3]
    size = raw[4]
    if size > PAYLOAD_MAX:
        return None
    payload = raw[7:7 + size]
    checksum = raw[5] + 256 * raw[6]
    if checksum != (sum(payload) + seq + size) % 65536:
        return None
    try:
        text = payload.decode('utf-8')
    except UnicodeError:
        text = payload.decode('utf-8', errors='replace')
    tokens = text.split('|')
    if not tokens or tokens[0] not in ('B', 'R', 'P', 'S', 'T', 'H', 'F', 'A', 'C', 'I', 'G', 'L', 'D'):
        return None
    return SemanticPacket(seq, tokens[0], tuple(tokens[1:]), text)


def decode_pixels(rgb: np.ndarray, x: int, y: int, scale: float,
                  layout: str = 'normal') -> SemanticPacket | None:
    """Decode sidecar anchored to the *already verified* PriestBridge marker.

    x, y are image-local coordinates. The fixed 8x8 tile interiors are sampled
    away from edges to limit bilinear interpolation. Strict checksum rejects
    accidental UI overlays and old addons that have no sidecar.
    """
    columns = 16 if layout == 'compact' else 8
    start_y = 18 if layout == 'compact' else 24
    # The bridge sentinel can estimate fractional UI scale slightly high or
    # low. At the far end of the 16-column compact packet that error can move
    # samples into a tile edge. Try a tiny bounded scale correction; accept
    # only a packet with matching magic, version, and full checksum.
    for correction in (1, .995, .99, 1.005, 1.01, .985, 1.015, .98, 1.02):
        candidate_scale = scale * correction

        def pixel(px, py):
            sx = x + round(px * candidate_scale)
            sy = y + round(py * candidate_scale)
            if sx < 0 or sy < 0 or sx >= rgb.shape[1] or sy >= rgb.shape[0]:
                return None
            return np.asarray(rgb[sy, sx, :3], dtype=np.int16)

        a = pixel(184, 4)
        b = pixel(200, 4)
        if a is None or b is None:
            continue
        if not (a[0] < 45 and 145 < a[1] < 235 and 45 < a[2] < 145
                and 135 < b[0] < 235 and 65 < b[1] < 150 and b[2] < 45):
            continue
        raw = bytearray()
        for i in range(TILE_COUNT):
            col, row = i % columns, i // columns
            px, py = 184 + col * 10, start_y + row * 10
            # Median of inner pixels rejects edge antialiasing artifacts.
            samples = [pixel(px + dx, py + dy) for dx, dy in ((0, 0), (1, 0), (0, 1))]
            if any(s is None for s in samples):
                break
            color = np.median(np.asarray(samples), axis=0).astype(np.uint8)
            raw.extend(int(v) for v in color)
        if len(raw) != PACKET_SIZE:
            continue
        packet = decode_bytes(bytes(raw))
        if packet is not None:
            return packet
    return None


def monitor_semantics(sct, bridge_reading) -> SemanticPacket | None:
    """Grab a tiny window region. Failure never stops primary combat telemetry."""
    scale = bridge_reading.scale
    x, y = bridge_reading.marker_x, bridge_reading.marker_y
    layout = getattr(bridge_reading, 'layout', 'normal')
    try:
        region = {"left": x, "top": y,
                  "width": max(1, round((350 if layout == 'compact' else 265) * scale)),
                  "height": max(1, round((48 if layout == 'compact' else 70) * scale))}
        shot = sct.grab(region)
        rgb = np.asarray(shot)[:, :, [2, 1, 0]]
        return decode_pixels(rgb, 0, 0, scale, layout=layout)
    except (OSError, ValueError, IndexError, RuntimeError):
        return None
