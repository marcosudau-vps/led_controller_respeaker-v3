"""The ``lefx`` command line.

Verb first, subject second: ``lefx set state ready_state``. The same wording as
the HTTP API, because both carry the same commands and neither holds logic of
its own.

Plain ``set`` always means on. An implicit toggle would make a repeated command
or a retry do the opposite of what it did the first time, so switching something
off is spelled out.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import ControllerClient, Result

LIST_KINDS = {
    "state": "states",
    "states": "states",
    "overlay": "overlays",
    "overlays": "overlays",
    "event": "events",
    "events": "events",
    "preset": "presets",
    "presets": "presets",
}


def parse_json_object(value: str | None, *, label: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{label} must be a JSON object")
    return parsed


def parse_bool(value: str) -> bool:
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on", "ja", "an"}:
        return True
    if text in {"0", "false", "no", "off", "nein", "aus"}:
        return False
    raise argparse.ArgumentTypeError(f"Not a boolean: {value!r}")


def add_connection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=5.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lefx", description="Control the LEFX V3 effect engine."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the controller service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--port-pool", default="", help="Fallback ports, e.g. 8765,8770-8774")
    serve.add_argument("--sink", default="null", help="Frame sink to use, or 'null'")
    serve.add_argument("--led-count", type=int, default=12)
    serve.add_argument("--fps", type=float, default=30.0)

    sinks = sub.add_parser("sinks", help="List installed frame sinks and input providers")

    status = sub.add_parser("status", help="Show the service status")
    add_connection(status)
    status.add_argument("--json", action="store_true")

    listing = sub.add_parser("list", help="List states, overlays, events or presets")
    add_connection(listing)
    listing.add_argument("kind", choices=sorted(LIST_KINDS))
    listing.add_argument("--details", action="store_true")
    listing.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show one definition or preset")
    add_connection(show)
    show.add_argument("target")

    setter = sub.add_parser("set", help="Set a state or an overlay")
    add_connection(setter)
    setter.add_argument("subject", choices=("state", "overlay"))
    setter.add_argument("target")
    setter.add_argument("--slot", choices=("primary", "background"), default="primary")
    setter.add_argument("--channel")
    setter.add_argument("--config", default="")
    setter.add_argument("--inputs", default="")
    mode = setter.add_mutually_exclusive_group()
    mode.add_argument("--on", dest="action", action="store_const", const="on")
    mode.add_argument("--off", dest="action", action="store_const", const="off")
    mode.add_argument("--toggle", dest="action", action="store_const", const="toggle")
    setter.set_defaults(action="on")

    clear = sub.add_parser("clear", help="Clear a state slot, an overlay channel or everything")
    add_connection(clear)
    clear.add_argument("subject", choices=("state", "overlay", "all"))
    clear.add_argument("channel", nargs="?")
    clear.add_argument("--slot", choices=("primary", "background"), default="primary")

    update = sub.add_parser("update", help="Update a controlled overlay")
    add_connection(update)
    update.add_argument("subject", choices=("overlay",))
    update.add_argument("channel")
    update.add_argument("--inputs", default="")

    emit = sub.add_parser("emit", help="Emit an event")
    add_connection(emit)
    emit.add_argument("subject", choices=("event",))
    emit.add_argument("target")
    emit.add_argument("--config", default="")
    emit.add_argument("--priority", type=int)
    emit.add_argument("--duration-ms", type=int)

    output = sub.add_parser("output", help="Adjust global brightness or switch output off")
    add_connection(output)
    output.add_argument("--brightness", type=float)
    output.add_argument("--enabled", type=parse_bool)

    sources = sub.add_parser("sources", help="Manage effect package sources")
    add_connection(sources)
    sources.add_argument(
        "action", choices=("list", "register", "reload", "remove"), nargs="?", default="list"
    )
    sources.add_argument("value", nargs="?", help="Path to register, or source id to remove")

    shutdown = sub.add_parser("shutdown", help="Ask the service to stop")
    add_connection(shutdown)

    return parser


def emit_result(result: Result, *, plain: list[str] | None = None) -> int:
    if result.ok and plain is not None:
        for line in plain:
            print(line)
        return 0
    payload = result.to_dict()
    stream = sys.stdout if result.ok else sys.stderr
    print(json.dumps(payload["data"] if result.ok else payload, indent=2, sort_keys=True), file=stream)
    return 0 if result.ok else 1


def run_serve(args: argparse.Namespace) -> int:
    from uvicorn.config import Config
    from uvicorn.server import Server

    from . import hosting, paths
    from .api import create_app
    from .service import ControllerService

    pool = hosting.parse_pool(args.port_pool) or hosting.DEFAULT_POOL
    port = hosting.select_port(args.host, args.port, pool)
    instance = hosting.create_instance(host=args.host, port=port, requested_port=args.port)
    instance_path = paths.instance_file()
    hosting.write_instance(instance_path, instance)

    service = ControllerService(sink=args.sink, led_count=args.led_count, fps=args.fps)
    app = create_app(
        service,
        lifecycle_callback=lambda phase: hosting.update_instance_status(
            instance_path, "ready" if phase == "started" else "stopping"
        ),
    )

    print(
        json.dumps(
            {
                "event": "service_listening",
                "host": args.host,
                "port": port,
                "sink": service.sink_name,
                "effects": len(service.library.registry),
            }
        ),
        flush=True,
    )
    server = Server(Config(app, host=args.host, port=port, log_level="info", lifespan="on"))
    app.state.shutdown_server = lambda: setattr(server, "should_exit", True)
    try:
        server.run()
        return 0
    finally:
        hosting.clear_instance(instance_path, pid=instance.pid)


def run_sinks() -> int:
    from . import discovery

    print(json.dumps(discovery.describe(), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(parser, args)
    except argparse.ArgumentTypeError as exc:
        # Malformed --config or --inputs. Report it the way argparse reports any
        # other bad argument rather than letting a traceback out.
        parser.error(str(exc))
        return 2


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:

    if args.command == "serve":
        return run_serve(args)
    if args.command == "sinks":
        return run_sinks()

    client = ControllerClient(host=args.host, port=args.port, timeout=args.timeout)

    if args.command == "status":
        return emit_result(client.status())

    if args.command == "list":
        result = client.list(LIST_KINDS[args.kind], details=args.details)
        plain = None
        if result.ok and not args.details and not args.json and isinstance(result.data, list):
            plain = [str(item) for item in result.data]
        return emit_result(result, plain=plain)

    if args.command == "show":
        return emit_result(client.show(args.target))

    if args.command == "set":
        config = parse_json_object(args.config, label="--config")
        if args.subject == "state":
            return emit_result(
                client.set_state(args.target, config, slot=args.slot, action=args.action)
            )
        return emit_result(
            client.set_overlay(
                args.target,
                channel=args.channel,
                config=config,
                inputs=parse_json_object(args.inputs, label="--inputs"),
                action=args.action,
            )
        )

    if args.command == "clear":
        if args.subject == "state":
            return emit_result(client.clear_state(slot=args.slot))
        if args.subject == "all":
            return emit_result(client.clear_all())
        if not args.channel:
            parser.error("clear overlay needs a channel")
        return emit_result(client.clear_overlay(args.channel))

    if args.command == "update":
        return emit_result(
            client.update_overlay(args.channel, parse_json_object(args.inputs, label="--inputs"))
        )

    if args.command == "emit":
        return emit_result(
            client.emit_event(
                args.target,
                parse_json_object(args.config, label="--config"),
                priority=args.priority,
                duration_ms=args.duration_ms,
            )
        )

    if args.command == "output":
        if args.brightness is None and args.enabled is None:
            parser.error("output needs --brightness or --enabled")
        return emit_result(client.set_output(brightness=args.brightness, enabled=args.enabled))

    if args.command == "sources":
        if args.action == "list":
            return emit_result(client.list_sources())
        if args.action == "reload":
            return emit_result(client.reload_sources())
        if not args.value:
            parser.error(f"sources {args.action} needs a value")
        if args.action == "register":
            return emit_result(client.register_source(args.value))
        return emit_result(client.remove_source(args.value))

    if args.command == "shutdown":
        return emit_result(client.shutdown())

    parser.error(f"Unsupported command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
