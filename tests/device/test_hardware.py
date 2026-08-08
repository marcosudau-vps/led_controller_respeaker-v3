"""What only a reSpeaker can answer.

These do not run in CI and are not meant to. Everything here asks a question a
double would answer with whatever it was told to say: does the firmware accept
``LED_RING_COLOR``, does ``DOA_VALUE`` come back in the shape the decoder
expects, does a pulled cable really surface as ``available=False``. Checking any
of that against a fake would only confirm that our code reacts correctly to our
own invented replies.

Run them with a device attached::

    uv run pytest -m hardware

Two of them wait for a person to unplug and replug the cable. They are marked
``interactive`` on top of ``hardware`` and skip unless ``LEFX_INTERACTIVE=1``,
so an unattended run with a device connected does not hang waiting for hands.
"""

from __future__ import annotations

import os
import time

import pytest

from lefx.sdk import InputContext, OutputFrame
from respeaker_led.device import xvf
from respeaker_led.device.provider import ReSpeakerDoaProvider, decode_doa
from respeaker_led.device.sink import ReSpeakerFrameSink
from respeaker_led.device.transport import UsbTransport

from .conftest import hardware_reachable, until

pytestmark = pytest.mark.hardware

INTERACTIVE = os.environ.get("LEFX_INTERACTIVE") == "1"
needs_hands = pytest.mark.skipif(
    not INTERACTIVE, reason="needs someone at the cable; set LEFX_INTERACTIVE=1"
)

HANDS_TIMEOUT_S = 120.0
"""How long to wait for a person to reach the cable.

Generous on purpose. The thing being measured is how the transport reacts, and
that takes a second once the plug moves; everything before it is somebody
reading a prompt and standing up. A tight window here does not make the test
stricter, it makes it fail for a reason that has nothing to do with the device.
"""


@pytest.fixture
def transport():
    reachable, reason = hardware_reachable()
    if not reachable:
        pytest.skip(reason)
    link = UsbTransport(retry_interval_s=0.5, heartbeat_interval_s=1.0)
    link.start()
    until(lambda: link.is_connected, "the reSpeaker never connected")
    try:
        yield link
    finally:
        link.close()


def test_the_firmware_accepts_a_ring_of_colours(transport):
    """The claim the whole output path rests on, asked of the firmware itself."""
    sink = ReSpeakerFrameSink(transport)
    colors = tuple(
        (index * 0x00110F) & 0xFFFFFF for index in range(xvf.RING_LED_COUNT)
    )
    sink.apply_frame(OutputFrame(leds=colors, timestamp=time.time()))

    status = sink.status()
    assert status.available is True, status.detail


def test_the_ring_size_in_the_command_table_matches_the_device(transport):
    """If the firmware disagreed, it would reject the write rather than truncate."""
    sink = ReSpeakerFrameSink(transport)
    sink.apply_frame(OutputFrame(leds=(0x000000,) * xvf.RING_LED_COUNT, timestamp=0.0))
    assert sink.status().available is True


def test_doa_value_comes_back_in_the_shape_the_decoder_expects(transport):
    """The wire format, read from the device rather than assumed."""
    payload = transport.read("DOA_VALUE")
    assert isinstance(payload, tuple) and len(payload) == 2

    decoded = decode_doa(payload)
    assert 0.0 <= decoded["direction_deg"] < 360.0
    assert decoded["detection_state"] in ("none", "sound")


def test_the_provider_keeps_producing_readings_over_time(transport):
    """A real device, polled the way the service polls it."""
    provider = ReSpeakerDoaProvider(transport, max_hz=30.0)
    context = InputContext(
        now=time.monotonic(), led_count=xvf.RING_LED_COUNT, config={}, previous_inputs={}
    )

    started = time.monotonic()
    while time.monotonic() - started < 1.0:
        provider.refresh(time.monotonic())
        time.sleep(1.0 / 60.0)

    status = provider.status(time.monotonic())
    assert status["last_error"] is None, status["last_error"]
    assert provider.sample(context) is not None
    # Polled at 30 Hz for a second while rendering at 60: about thirty reads,
    # not sixty. The ceiling is the point of the split between refresh and sample.
    assert 20 <= status["poll_count"] <= 40


@needs_hands
def test_an_unplugged_cable_surfaces_as_unavailable(transport):
    sink = ReSpeakerFrameSink(transport)
    sink.apply_frame(OutputFrame(leds=(0,) * xvf.RING_LED_COUNT, timestamp=0.0))
    assert sink.status().available is True

    print("\n>>> Unplug the reSpeaker now.")
    until(lambda: not transport.is_connected, "the unplug went unnoticed", timeout=HANDS_TIMEOUT_S)

    for _ in range(5):
        # The rule the render loop depends on, checked against a real unplug.
        sink.apply_frame(OutputFrame(leds=(0xFF0000,) * xvf.RING_LED_COUNT, timestamp=0.0))
    status = sink.status()
    assert status.available is False
    assert status.detail


@needs_hands
def test_replugging_restores_output_without_a_restart(transport):
    """The same sink object has to keep working across a reconnection.

    A device that came back has forgotten the ring mode along with everything
    else written to the old handle, and the sink is the only thing that knows to
    say it again. Reusing the sink from before the unplug is what makes this a
    test of that, rather than of a freshly built one.
    """
    sink = ReSpeakerFrameSink(transport)
    sink.apply_frame(OutputFrame(leds=(0x0000FF,) * xvf.RING_LED_COUNT, timestamp=0.0))
    assert sink.status().available is True

    print("\n>>> Unplug the reSpeaker, then plug it back in.")
    until(lambda: not transport.is_connected, "the unplug went unnoticed", timeout=HANDS_TIMEOUT_S)
    until(lambda: transport.is_connected, "it never came back", timeout=HANDS_TIMEOUT_S)

    sink.apply_frame(OutputFrame(leds=(0x00FF00,) * xvf.RING_LED_COUNT, timestamp=0.0))
    assert sink.status().available is True
