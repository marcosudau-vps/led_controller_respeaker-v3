"""reSpeaker XVF3800 hardware integration — USB transport, frame sink, DoA input.

Depends on ``lefx.sdk`` and nothing else from the system. The engine is never
imported here; it reaches this package through entry points, which is what makes
"not installed" and "not present" the same thing.
"""

from __future__ import annotations

from .contention import Holder, ReleaseReport, device_probe, find_holders, release_device
from .provider import ReSpeakerDoaProvider, decode_doa
from .registration import create_doa_provider, create_frame_sink, shared_transport
from .sink import ReSpeakerFrameSink
from .transport import ConnectionState, UsbTransport
from .xvf import RING_LED_COUNT

__version__ = "3.0.0"

__all__ = [
    "ConnectionState",
    "Holder",
    "RING_LED_COUNT",
    "ReleaseReport",
    "ReSpeakerDoaProvider",
    "ReSpeakerFrameSink",
    "UsbTransport",
    "__version__",
    "create_doa_provider",
    "create_frame_sink",
    "decode_doa",
    "device_probe",
    "find_holders",
    "release_device",
    "shared_transport",
]
