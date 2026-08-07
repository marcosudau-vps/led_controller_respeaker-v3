"""Taking the device back from another process.

This is the one piece of the system that stops somebody's program, so what is
pinned down here is mostly what it must *not* do: never touch software that only
happens to hold some other USB device, never keep going once the device answers,
never act at all on a dry run.

The orchestration is tested against a fake probe and a fake terminator. Nothing
in this file ends a real process — a test suite that did would be a worse
neighbour than the problem it is testing.
"""

from __future__ import annotations

import os

import pytest

from respeaker_led.device import contention
from respeaker_led.device.contention import Holder, ReleaseReport


def holder(pid: int, *, command: str = "python.exe app.py", strong: bool = True) -> Holder:
    return Holder(
        pid=pid,
        executable="python.exe",
        command_line=command,
        evidence=("winusb.dll",) if strong else ("libusb-1.0.dll",),
        confidence="strong" if strong else "likely",
    )


RESPEAKER = holder(100, command="python.exe main.py serve --respeaker")
LEFX = holder(101, command="python.exe -m lefx.interfaces.cli serve")
MOUSE = holder(200, command="logioptionsplus_agent.exe")
RGB = holder(201, command="iCUE.exe --autorun")


# -- identification ---------------------------------------------------------


def test_only_this_devices_software_counts_as_related():
    """The distinction everything destructive here hangs on.

    Peripheral software holds an open WinUSB handle permanently, for devices
    that are not a reSpeaker. Without this line the USB evidence alone would
    nominate a mouse driver.
    """
    assert RESPEAKER.related is True
    assert LEFX.related is True
    assert MOUSE.related is False
    assert RGB.related is False


def test_related_software_is_ranked_ahead_of_unrelated():
    """Candidates are stopped in order until the device answers.

    So ordering decides what actually gets stopped, not merely how a list reads.
    """
    ordered = sorted([RGB, MOUSE, LEFX, RESPEAKER], key=lambda item: item.rank)
    assert [item.pid for item in ordered] == [100, 101, 200, 201]


def test_a_weaker_signal_ranks_behind_an_open_handle():
    loaded_backend = holder(102, command="python.exe tool.py respeaker", strong=False)
    open_handle = holder(103, command="python.exe tool.py respeaker", strong=True)
    assert open_handle.rank < loaded_backend.rank


def test_searching_never_nominates_the_process_doing_the_searching():
    """Whatever else it finds, it must not propose stopping us."""
    assert all(found.pid != os.getpid() for found in contention.find_holders())


def test_searching_can_be_told_to_ignore_processes():
    everything = contention.find_holders()
    if not everything:
        pytest.skip("nothing on this machine holds a USB device")
    first = everything[0].pid
    assert all(found.pid != first for found in contention.find_holders(exclude={first}))


# -- what the report says ---------------------------------------------------


def test_a_dry_run_report_does_not_claim_anything_was_stopped():
    report = ReleaseReport(
        reachable_before=False, reachable_after=False, dry_run=True, candidates=[RESPEAKER]
    )
    assert "nothing was stopped" in report.summary()
    assert report.changed_anything is False


def test_the_report_names_what_it_stopped():
    report = ReleaseReport(
        reachable_before=False, reachable_after=True, terminated=[RESPEAKER]
    )
    assert "pid 100" in report.summary()


def test_a_holder_describes_itself_well_enough_to_recognise():
    """Every candidate is python.exe; the command line is the only way to tell."""
    text = RESPEAKER.describe()
    assert "100" in text and "main.py" in text and "reSpeaker software" in text


# -- taking the device ------------------------------------------------------


@pytest.fixture
def fake(monkeypatch):
    """A machine whose holders and terminations we decide."""

    class Machine:
        def __init__(self) -> None:
            self.holders: list[Holder] = []
            self.freed_by: int | None = None
            self.stopped: list[int] = []
            self.refuse: dict[int, str] = {}

        def probe(self) -> bool:
            return self.freed_by is not None and self.freed_by in self.stopped

        def terminate(self, pid: int, timeout_s: float) -> str | None:
            del timeout_s
            if pid in self.refuse:
                return self.refuse[pid]
            self.stopped.append(pid)
            return None

    machine = Machine()
    monkeypatch.setattr(contention, "find_holders", lambda **_: list(machine.holders))
    monkeypatch.setattr(contention, "_terminate", machine.terminate)
    return machine


def test_a_reachable_device_is_left_entirely_alone(fake):
    fake.holders = [RESPEAKER, MOUSE]
    fake.freed_by = None
    report = contention.release_device(lambda: True)

    assert report.reachable_before is True
    assert fake.stopped == []


def test_stopping_ends_the_moment_the_device_answers(fake):
    """The property that keeps collateral damage to the process in the way.

    Two plausible candidates, but the first frees the device — so the second is
    never touched, however suspicious it looked.
    """
    fake.holders = [RESPEAKER, LEFX]
    fake.freed_by = RESPEAKER.pid

    report = contention.release_device(fake.probe, settle_s=0.05)

    assert fake.stopped == [RESPEAKER.pid]
    assert report.reachable_after is True
    assert [item.pid for item in report.terminated] == [RESPEAKER.pid]


def test_unrelated_usb_software_is_never_stopped_by_default(fake):
    """A mouse driver must survive a claim, even when nothing else is found."""
    fake.holders = [MOUSE, RGB]
    fake.freed_by = MOUSE.pid

    report = contention.release_device(fake.probe, settle_s=0.05)

    assert fake.stopped == []
    assert report.reachable_after is False
    assert {item.pid for item in report.skipped} == {MOUSE.pid, RGB.pid}
    assert "not reSpeaker software" in (report.note or "")


def test_unrelated_software_can_be_allowed_deliberately(fake):
    """An unknown holder is a decision for a person, not a default."""
    fake.holders = [MOUSE]
    fake.freed_by = MOUSE.pid

    report = contention.release_device(fake.probe, settle_s=0.05, only_related=False)

    assert fake.stopped == [MOUSE.pid]
    assert report.reachable_after is True


def test_a_dry_run_stops_nothing_but_says_what_it_would_stop(fake):
    fake.holders = [RESPEAKER, MOUSE]
    fake.freed_by = RESPEAKER.pid

    report = contention.release_device(fake.probe, dry_run=True)

    assert fake.stopped == []
    assert [item.pid for item in report.candidates] == [RESPEAKER.pid]
    assert [item.pid for item in report.skipped] == [MOUSE.pid]


def test_a_process_that_cannot_be_stopped_is_reported_not_retried(fake):
    fake.holders = [RESPEAKER, LEFX]
    fake.freed_by = LEFX.pid
    fake.refuse = {RESPEAKER.pid: "access denied"}

    report = contention.release_device(fake.probe, settle_s=0.05)

    assert fake.stopped == [LEFX.pid]
    assert [(item.pid, why) for item, why in report.failures] == [
        (RESPEAKER.pid, "access denied")
    ]
    assert report.reachable_after is True


def test_stopping_gives_up_rather_than_working_through_the_machine(fake):
    """Reaching the limit means the guess was wrong, not that we should continue."""
    fake.holders = [holder(300 + index, command=f"python.exe respeaker{index}.py")
                    for index in range(8)]
    fake.freed_by = None

    report = contention.release_device(fake.probe, settle_s=0.01, limit=3)

    assert len(fake.stopped) == 3
    assert report.reachable_after is False
    assert "limit" in (report.note or "")


def test_nothing_holding_usb_points_away_from_contention(fake):
    """An unreachable device with no USB software anywhere is a different problem."""
    fake.holders = []
    fake.freed_by = None

    report = contention.release_device(fake.probe)

    assert fake.stopped == []
    assert "driver binding" in (report.note or "")
