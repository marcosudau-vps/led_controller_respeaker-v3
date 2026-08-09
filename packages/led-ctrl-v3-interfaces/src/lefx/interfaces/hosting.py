"""Running the service as a process: port selection and the instance file.

Separate from the service itself, which is perfectly usable embedded in another
application and should not know about ports or PID files.
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PORT = 8765
DEFAULT_POOL = tuple(range(8765, 8776))


@dataclass(slots=True, frozen=True)
class InstanceInfo:
    """What a running service publishes about itself."""

    pid: int
    host: str
    port: int
    requested_port: int
    started_at: float
    status: str = "starting"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def select_port(host: str, requested: int, pool: tuple[int, ...] = DEFAULT_POOL) -> int:
    """The requested port if it is free, otherwise the first free one from the pool."""
    if port_is_free(host, requested):
        return requested
    for candidate in pool:
        if candidate != requested and port_is_free(host, candidate):
            return candidate
    raise OSError(f"No free port for {host}; tried {requested} and {len(pool)} alternatives")


def parse_pool(text: str) -> tuple[int, ...]:
    """Accept ``8765,8770-8774`` and produce the ports it names."""
    ports: list[int] = []
    for chunk in str(text or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        if "-" in item:
            start, _, end = item.partition("-")
            ports.extend(range(int(start), int(end) + 1))
        else:
            ports.append(int(item))
    return tuple(dict.fromkeys(ports))


def write_instance(path: Path, info: InstanceInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def read_instance(path: Path) -> InstanceInfo | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return InstanceInfo(**payload)
    except TypeError:
        return None


def update_instance_status(path: Path, status: str) -> None:
    info = read_instance(path)
    if info is None:
        return
    write_instance(path, InstanceInfo(**{**info.to_dict(), "status": status}))


def clear_instance(path: Path, *, pid: int | None = None) -> None:
    """Remove the instance file, unless another process has claimed it."""
    info = read_instance(path)
    if info is not None and pid is not None and info.pid != pid:
        return
    path.unlink(missing_ok=True)


def create_instance(*, host: str, port: int, requested_port: int) -> InstanceInfo:
    return InstanceInfo(
        pid=os.getpid(),
        host=host,
        port=port,
        requested_port=requested_port,
        started_at=time.time(),
    )


__all__ = [
    "DEFAULT_POOL",
    "DEFAULT_PORT",
    "InstanceInfo",
    "clear_instance",
    "create_instance",
    "parse_pool",
    "port_is_free",
    "read_instance",
    "select_port",
    "update_instance_status",
    "write_instance",
]
