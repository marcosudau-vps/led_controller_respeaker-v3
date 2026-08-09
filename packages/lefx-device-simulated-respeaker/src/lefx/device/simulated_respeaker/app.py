"""The ``lefx-simulator`` console script.

Qt is imported here and only here, behind a check that turns a missing optional
dependency into a sentence instead of a traceback. That is what keeps the extra
honest: the service half of this package is installed without PySide6, and
nothing it imports leads to this module.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import protocol
from .link import default_port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lefx-simulator",
        description="Open the ring window and connect it to a running lefx service.",
    )
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Service simulator port (default: ${protocol.PORT_ENV_VAR} or {protocol.DEFAULT_PORT})",
    )
    parser.add_argument(
        "--led-count",
        type=int,
        default=12,
        help="Ring size to draw until the service announces its own",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "The ring window needs PySide6, which is an optional extra:\n"
            '    uv pip install "lefx-device-simulated-respeaker[gui]"\n'
            "The service half of the simulator works without it.",
            file=sys.stderr,
        )
        return 2

    from .window import SimulatorWindow

    port = default_port() if args.port is None else args.port
    application = QApplication(sys.argv[:1])
    window = SimulatorWindow(host=args.host, port=port, led_count=args.led_count)
    window.show()
    return int(application.exec())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
