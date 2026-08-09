"""The wire format between the service and the ring window.

Length-prefixed JSON over a loopback TCP connection: a four-byte big-endian
length followed by that many bytes of UTF-8 JSON. Framing is explicit because
TCP is a byte stream — without a length, two frames sent quickly enough arrive
as one read, and a large one arrives in pieces.

Small and readable on purpose. This carries a colour ring and two slider values
between two processes on the same machine; anything cleverer would be harder to
debug than the thing it transports.

Free of Qt and of everything else optional: both halves of the simulator import
this, and only one of them has a GUI.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Mapping

PROTOCOL_VERSION = 3

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
"""Loopback only. The simulator is a local stand-in for a cable, not a network
service, and binding it to anything reachable would make it one.

Deliberately clear of 8765 and its neighbours: the HTTP interface uses 8765 and
falls back through the ports just above it, and earlier generations of this
controller took 8766. A default that collides with software the same person is
likely to be running is a bad default, however free the port is in the abstract.
"""

PORT_ENV_VAR = "LEFX_SIMULATOR_PORT"
"""Lets both halves agree on a port without either being told on the command
line — useful when several checkouts run side by side."""

MAX_MESSAGE_BYTES = 1 << 20
"""A ring of colours is a few hundred bytes. Anything of this size is a bug or
a stray client, and reading it would be the mistake."""

_HEADER = struct.Struct(">I")
HEADER_SIZE = _HEADER.size

# Message kinds
HELLO = "hello"
FRAME = "frame"
INPUT = "input"


class ProtocolError(Exception):
    """The peer sent something that is not a message of this protocol."""


def encode(message: Mapping[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"message of {len(body)} bytes exceeds the limit")
    return _HEADER.pack(len(body)) + body


def decode(body: bytes) -> dict[str, Any]:
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"not valid JSON: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("a message must be a JSON object")
    return message


def payload_length(header: bytes) -> int:
    if len(header) != HEADER_SIZE:
        raise ProtocolError(f"a header is {HEADER_SIZE} bytes, got {len(header)}")
    (length,) = _HEADER.unpack(header)
    if length > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"announced {length} bytes, over the limit")
    return length


def hello(*, led_count: int) -> dict[str, Any]:
    """Sent to a window the moment it connects, so it can size the ring."""
    return {"type": HELLO, "protocol": PROTOCOL_VERSION, "led_count": int(led_count)}


def frame(leds: tuple[int, ...] | list[int], timestamp: float) -> dict[str, Any]:
    return {"type": FRAME, "leds": [int(value) for value in leds], "timestamp": float(timestamp)}


def inputs(*, direction_deg: float | None, detection_state: str) -> dict[str, Any]:
    """What the window reports back — the same shape the hardware produces.

    Deliberately identical to the reSpeaker's decoded ``DOA_VALUE``: the point
    of the simulator is that nothing above the port can tell the two apart.
    """
    return {
        "type": INPUT,
        "direction_deg": None if direction_deg is None else float(direction_deg),
        "detection_state": str(detection_state),
    }


def read_message(sock: Any) -> dict[str, Any] | None:
    """Read exactly one message, or ``None`` when the peer closed cleanly.

    Both halves need this, and both would otherwise get the short-read handling
    subtly different — ``recv`` returning fewer bytes than asked for is normal,
    not an error.
    """
    header = _read_exactly(sock, HEADER_SIZE)
    if header is None:
        return None
    body = _read_exactly(sock, payload_length(header))
    if body is None:
        raise ProtocolError("connection ended between header and body")
    return decode(body)


def _read_exactly(sock: Any, count: int) -> bytes | None:
    """``None`` for a clean close on a message boundary; a partial one raises.

    A read timeout is only benign at a boundary — there, it means the peer had
    nothing to say. Half way through a message it means the rest is lost and the
    stream is out of step, so it becomes a protocol error rather than something
    a caller might reasonably retry into a garbled read.
    """
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except TimeoutError:
            if chunks:
                raise ProtocolError("timed out mid-message") from None
            raise
        if not chunk:
            if chunks:
                raise ProtocolError("connection ended mid-message")
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "FRAME",
    "HEADER_SIZE",
    "HELLO",
    "INPUT",
    "MAX_MESSAGE_BYTES",
    "PORT_ENV_VAR",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode",
    "encode",
    "frame",
    "hello",
    "inputs",
    "payload_length",
    "read_message",
]
