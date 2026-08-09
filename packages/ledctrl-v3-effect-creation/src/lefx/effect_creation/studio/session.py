"""The controller the studio drives, and the output it is pointed at.

No Qt in here, on purpose. Everything the studio *does* — pick a device, load a
catalogue, run an effect, watch the frames come out — is separable from the
window that shows it, and keeping it separable is what makes it testable without
a display.

The studio embeds a real :class:`ControllerService` rather than talking to a
running one over HTTP. That is a deliberate choice with one consequence worth
knowing: it means the studio can render a definition that has not been packaged
yet, which is the only way to edit one and watch it at the same time. The price
is that the studio and a running service both want the same USB device, and only
one of them can have it — hence :func:`device_in_use`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from lefx.interfaces import ControllerService, describe, discovery, hosting, paths
from lefx.sdk import FrameSink, OutputFrame, SinkStatus

from .project import Project

logger = logging.getLogger("lefx.effect_creation.studio.session")

FrameListener = Callable[[tuple[int, ...]], None]

NULL_OUTPUT = "null"
STUDIO_CHANNEL = "studio"
"""The overlay channel the studio keeps its work on, so it can clear its own
without touching a channel something else is using."""


class TappedSink:
    """Sends every frame to the chosen device and to whoever is watching.

    The studio shows a ring of its own next to the controls, and that ring has
    to be the frames the device is being sent — not a second rendering of the
    same effect, which could agree with the first right up until the moment it
    mattered. So the frames are taken from the one path that leads to the
    device, on the way past.

    Watching must not be able to break sending. A listener that raises is
    reported and dropped from that frame; the device still gets it.
    """

    def __init__(self, inner: FrameSink, listener: FrameListener | None = None) -> None:
        self.inner = inner
        self.listener = listener
        self.name = getattr(inner, "name", type(inner).__name__)
        self.frame_count = 0

    def apply_frame(self, frame: OutputFrame) -> None:
        self.inner.apply_frame(frame)
        self.frame_count += 1
        listener = self.listener
        if listener is None:
            return
        try:
            listener(tuple(frame.leds))
        except Exception:
            logger.exception("frame listener failed")

    def status(self) -> SinkStatus:
        return self.inner.status()

    def close(self) -> None:
        self.inner.close()


def available_outputs() -> list[str]:
    """Every output that could be chosen, the null one first.

    Read from the installed entry points, exactly as the service reads them, so
    the list is what is actually installed rather than what this file knows
    about. A machine without the hardware package does not offer the hardware.
    """
    installed = [item["name"] for item in describe()["sinks"] if item["name"] != NULL_OUTPUT]
    return [NULL_OUTPUT, *sorted(installed)]


def device_in_use() -> str | None:
    """Whether a service is already running, and where, or ``None``.

    Two processes cannot hold one reSpeaker. Discovering that by watching writes
    fail is a poor way to find out, so the studio asks first and says what it
    found — the instance file is exactly the running service's own claim.
    """
    info = hosting.read_instance(paths.instance_file())
    if info is None or info.status == "stopping":
        return None
    if info.pid == os.getpid():
        return None
    if not _process_alive(info.pid):
        return None
    return f"a lefx service is running on {info.host}:{info.port} (pid {info.pid})"


WINDOWS_INVALID_PARAMETER = 87
"""What Windows answers when asked about a pid that does not exist."""


def _process_alive(pid: int) -> bool:
    """Whether the instance file describes something still running.

    A service killed rather than stopped leaves its file behind, and refusing to
    start because of a note from a process that no longer exists would be a
    worse failure than the one being prevented.

    The three outcomes are the same everywhere but spelled differently. POSIX
    raises :class:`ProcessLookupError` for a pid that is gone; Windows raises a
    plain :class:`OSError` carrying ``winerror`` 87, which is not distinguishable
    from a real failure by type alone. Anything else that goes wrong is treated
    as "alive", because refusing to open a device is the recoverable mistake and
    taking one out from under a running service is not.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Someone else's process, but a process.
        return True
    except OSError as exc:
        return getattr(exc, "winerror", None) != WINDOWS_INVALID_PARAMETER
    return True


class StudioSession:
    """One embedded controller, pointed at one output at a time."""

    def __init__(
        self,
        *,
        led_count: int = 12,
        fps: float = 30.0,
        search_paths: Sequence[str | Path] | None = None,
        state_file: str | Path | None = None,
        project: Project | None = None,
    ) -> None:
        self.led_count = int(led_count)
        self.fps = float(fps)
        # A project answers all of these at once. Explicit paths still win, so
        # a test can hand over an empty search path without inventing a tree.
        self.project = project
        if project is not None:
            search_paths = project.package_search_paths if search_paths is None else search_paths
            state_file = project.state_file if state_file is None else state_file
        self.search_paths = None if search_paths is None else list(search_paths)
        # The studio is a workbench, not the installation. Leaving a background
        # state behind from an evening of trying things out would surprise
        # whoever started the real service next.
        self.state_file = state_file
        self.service: ControllerService | None = None
        self.output_name = NULL_OUTPUT
        self.device_options: dict[str, Any] = {}
        self._listener: FrameListener | None = None

    # -- the output ---------------------------------------------------------

    def set_frame_listener(self, listener: FrameListener | None) -> None:
        self._listener = listener
        sink = None if self.service is None else self.service.sink
        if isinstance(sink, TappedSink):
            sink.listener = listener

    def use(self, project: Project) -> None:
        """Point the studio at a different checkout, reopening the output on it."""
        self.project = project
        self.search_paths = project.package_search_paths
        self.state_file = project.state_file
        if self.service is not None:
            self.open(self.output_name, **self.device_options)

    def open(self, output: str, **device_options: Any) -> ControllerService:
        """Point the studio at an output, replacing whatever it had.

        Closing first is not tidiness: the previous device is still holding a
        USB endpoint or a listening socket, and building the next one before
        letting go would have them contend for it.
        """
        self.close()

        sink: FrameSink
        if output == NULL_OUTPUT:
            sink = discovery.NullSink()
        else:
            options = {"led_count": self.led_count, **device_options}
            sink = discovery.create_sink(output, **options)

        if self.project is not None:
            # Providers read their calibration from a file; which file is a
            # property of the project, not of the working directory.
            device_options.setdefault("calibration_file", str(self.project.calibration_file))

        service = ControllerService(
            sink=TappedSink(sink, self._listener),
            led_count=self.led_count,
            fps=self.fps,
            search_paths=self.search_paths,
            state_file=self.state_file,
            sink_options=device_options,
            # The sink is handed over as an object, so the service cannot infer
            # which device it is; name it, or the input providers of the chosen
            # device would not be the ones started.
            input_device=output,
        )
        service.start()

        self.service = service
        self.output_name = output
        self.device_options = dict(device_options)
        logger.info("studio output is now %s", output)
        return service

    def close(self) -> None:
        if self.service is None:
            return
        try:
            self.service.stop()
        except Exception:
            logger.exception("stopping the studio service failed")
        self.service = None

    def __enter__(self) -> "StudioSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- what is loaded -----------------------------------------------------

    @property
    def registry(self):
        if self.service is None:
            raise RuntimeError("no output is open")
        return self.service.library.registry

    def reload_sources(self) -> dict[str, Any]:
        if self.service is None:
            raise RuntimeError("no output is open")
        return self.service.reload_sources()

    def status(self) -> dict[str, Any]:
        return {} if self.service is None else self.service.status()

    def sink_status(self) -> SinkStatus:
        if self.service is None:
            return SinkStatus(available=False, detail="no output is open")
        return self.service.sink.status()

    # -- driving ------------------------------------------------------------

    def play_state(self, effect_id: str, config: Mapping[str, Any]) -> dict[str, Any]:
        return self._require().set_state(effect_id, dict(config))

    def play_overlay(
        self,
        effect_id: str,
        config: Mapping[str, Any],
        inputs: Mapping[str, Any] | None = None,
        *,
        channel: str | None = STUDIO_CHANNEL,
    ) -> dict[str, Any]:
        return self._require().set_overlay(
            effect_id, channel=channel, config=dict(config), inputs=dict(inputs or {})
        )

    def update_inputs(
        self, inputs: Mapping[str, Any], *, channel: str = STUDIO_CHANNEL
    ) -> dict[str, Any]:
        return self._require().update_overlay(channel, dict(inputs))

    def emit(self, effect_id: str, config: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
        return self._require().emit_event(effect_id, dict(config), **extra)

    def clear_overlay(self, *, channel: str = STUDIO_CHANNEL) -> dict[str, Any]:
        return self._require().clear_overlay(channel)

    def clear_everything(self) -> dict[str, Any]:
        return self._require().clear_all()

    def set_output(self, **settings: Any) -> dict[str, Any]:
        return self._require().set_output(**settings)

    def _require(self) -> ControllerService:
        if self.service is None:
            raise RuntimeError("no output is open")
        return self.service


__all__ = [
    "NULL_OUTPUT",
    "STUDIO_CHANNEL",
    "FrameListener",
    "Project",
    "StudioSession",
    "TappedSink",
    "available_outputs",
    "device_in_use",
]
