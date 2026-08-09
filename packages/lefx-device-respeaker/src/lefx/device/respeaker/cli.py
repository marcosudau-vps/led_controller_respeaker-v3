"""``lefx-respeaker`` — look at the device before doing anything to it.

Force-claiming stops another program. That is not something to trigger blind
from a service flag with no way to see what it would hit first, so the same
machinery is available here as three commands that escalate in what they do:

    lefx-respeaker probe     is the device reachable, and if not, who else
                                   is holding a USB device
    lefx-respeaker claim -n  what a claim would stop, stopping nothing
    lefx-respeaker claim     stop it, then check the device answers

``claim`` only ever stops processes that identify themselves as reSpeaker
software. Peripheral software — mouse, keyboard, RGB — holds WinUSB handles
permanently and shows up in the same search; it is listed and left alone unless
``--include-unrelated`` says otherwise, and even then one at a time with a
re-check after each.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import contention


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lefx-respeaker",
        description="Inspect the reSpeaker and, if asked, take it from another process.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="Report whether the device can be talked to")
    probe.add_argument("--json", action="store_true")

    claim = sub.add_parser("claim", help="Stop what is holding the device, then re-check")
    claim.add_argument(
        "-n", "--dry-run", action="store_true", help="Report what would be stopped"
    )
    claim.add_argument(
        "--include-unrelated",
        action="store_true",
        help="Also consider USB software not identifiable as reSpeaker software",
    )
    claim.add_argument("--json", action="store_true")

    return parser


def run_probe(as_json: bool) -> int:
    reachable = contention.device_probe()()
    holders = [] if reachable else contention.find_holders()

    if as_json:
        print(
            json.dumps(
                {"reachable": reachable, "holders": contention.as_dicts(holders)},
                indent=2,
            )
        )
        return 0 if reachable else 1

    if reachable:
        print("The reSpeaker is reachable.")
        return 0

    print("The reSpeaker is NOT reachable.")
    if not holders:
        print(
            "\nNo process on this machine has a USB backend loaded, so this is not\n"
            "another program holding the device. Look at the driver binding, or at\n"
            "whether the device is plugged in at all."
        )
        return 1

    print("\nProcesses holding a USB device:")
    for holder in holders:
        print(f"  {holder.describe()}")
    print(
        "\nOnly the ones marked 'reSpeaker software' would be stopped by\n"
        "'lefx-respeaker claim'. Try it with -n first."
    )
    return 1


def run_claim(*, dry_run: bool, include_unrelated: bool, as_json: bool) -> int:
    report = contention.release_device(
        contention.device_probe(),
        dry_run=dry_run,
        only_related=not include_unrelated,
    )

    if as_json:
        print(
            json.dumps(
                {
                    "dry_run": report.dry_run,
                    "reachable_before": report.reachable_before,
                    "reachable_after": report.reachable_after,
                    "terminated": contention.as_dicts(report.terminated),
                    "candidates": contention.as_dicts(report.candidates),
                    "skipped": contention.as_dicts(report.skipped),
                    "failures": [
                        {"pid": holder.pid, "error": error}
                        for holder, error in report.failures
                    ],
                    "note": report.note,
                    "summary": report.summary(),
                },
                indent=2,
            )
        )
        return 0 if report.reachable_after or dry_run else 1

    print(report.summary())
    for holder in report.terminated:
        print(f"  stopped: {holder.describe()}")
    for holder in report.candidates:
        print(f"  would stop: {holder.describe()}")
    for holder in report.skipped:
        print(f"  left alone: {holder.describe()}")
    for holder, error in report.failures:
        print(f"  could not stop pid {holder.pid}: {error}")
    if report.note:
        print(f"\n{report.note}")
    return 0 if report.reachable_after or dry_run else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    if args.command == "probe":
        return run_probe(args.json)
    return run_claim(
        dry_run=args.dry_run,
        include_unrelated=args.include_unrelated,
        as_json=args.json,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
