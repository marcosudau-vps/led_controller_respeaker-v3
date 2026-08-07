"""Software device double — frame sink, simulated DoA input and ring window.

Depends on ``lefx.sdk`` and nothing else from the system, exactly as the hardware
package does. It is a device, not a preview: it fills the same ports, reports
direction in the same shape and range, and passes the same conformance suite.

Only the names exported here are service-side and free of Qt. The ring window
lives in :mod:`respeaker_led.simulator.window` and is reached through the
``respeaker-led-simulator`` console script.
"""

from __future__ import annotations

from .link import SimulatorLink, default_port
from .provider import DETECTION_STATES, SimulatorDoaProvider
from .registration import create_doa_provider, create_frame_sink, shared_link
from .sink import SimulatorFrameSink

__version__ = "3.0.0"

__all__ = [
    "DETECTION_STATES",
    "SimulatorDoaProvider",
    "SimulatorFrameSink",
    "SimulatorLink",
    "__version__",
    "create_doa_provider",
    "create_frame_sink",
    "default_port",
    "shared_link",
]
