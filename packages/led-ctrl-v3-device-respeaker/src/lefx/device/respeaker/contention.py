"""Finding out who else is holding the reSpeaker, and — on request — taking it.

A WinUSB device handle is exclusive. A second process that opens the reSpeaker
does not queue behind the first; it gets ``Errno 13``, which reads like a
permission or driver problem and sends you looking in the wrong place. The usual
cause is far more ordinary: another controller is already running.

Windows offers no supported way to ask "which process holds this device". What
it does offer is what each process has *loaded*, and that turns out to be a
sharp signal. ``WinUSB.dll`` is mapped when a WinUSB handle is actually opened,
not merely when a program is capable of USB — so a process carrying it is
holding *a* WinUSB device, and one also carrying a libusb backend is holding it
the same way we would.

That is evidence, not proof: it identifies a process talking to some WinUSB
device, not necessarily to this one. Which is why nothing here kills a set of
processes. :func:`release_device` stops one candidate, asks the device whether
it is free, and stops only if it is not — so the process actually in the way is
the one that goes, and a bystander with an unrelated USB device survives.

Nothing in this module runs unless it is asked for. Terminating another person's
program is not something a render loop should ever decide on its own.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Collection, Iterable

logger = logging.getLogger("lefx.device.respeaker.contention")

WINDOWS = sys.platform.startswith("win")

STRONG_MODULES = ("winusb.dll",)
"""Mapped when a WinUSB handle is open — the process is holding a device now."""

BACKEND_MODULES = ("libusb-1.0.dll", "libusb0.dll", "libusbk.dll", "usbdk_helper.dll")
"""A USB backend. Says the process speaks USB, not that it is speaking it."""

INTERESTING_TERMS = ("respeaker", "xvf", "lefx", "led_controller")
"""What marks a process as *this* device's software rather than some other's.

Not proof — a name is not a handle — but it is the difference that matters when
deciding what may be stopped. On an ordinary desktop the USB evidence alone
matches mouse and keyboard software: Logitech Options+ and Corsair iCUE both
carry an open WinUSB handle at all times, for devices that are emphatically not
a reSpeaker. Stopping either to free a microphone array would be absurd, so by
default nothing without one of these terms is ever terminated.
"""


@dataclass(frozen=True)
class Holder:
    """A process that looks like it is holding a USB device."""

    pid: int
    executable: str | None
    command_line: str | None
    evidence: tuple[str, ...]
    confidence: str
    """``"strong"`` for an open WinUSB handle, ``"likely"`` for a loaded backend."""

    @property
    def related(self) -> bool:
        """Whether this looks like reSpeaker software rather than some other USB app."""
        haystack = f"{self.command_line or ''} {self.executable or ''}".casefold()
        return any(term in haystack for term in INTERESTING_TERMS)

    @property
    def rank(self) -> tuple[int, int, int]:
        """Sort key: most-certainly-in-the-way first.

        Ordering matters more than usual here, because candidates are stopped
        one at a time until the device answers — so the first one is usually the
        only one.
        """
        return (0 if self.related else 1, 0 if self.confidence == "strong" else 1, self.pid)

    def describe(self) -> str:
        what = self.command_line or self.executable or "unknown"
        kind = "reSpeaker software" if self.related else "unrelated USB software"
        return f"pid {self.pid} [{self.confidence}, {kind}] {what} ({', '.join(self.evidence)})"


@dataclass
class ReleaseReport:
    """What was attempted and what came of it."""

    reachable_before: bool
    reachable_after: bool
    terminated: list[Holder] = field(default_factory=list)
    candidates: list[Holder] = field(default_factory=list)
    """On a dry run: what would be stopped, in the order it would be tried."""

    skipped: list[Holder] = field(default_factory=list)
    """Holders deliberately left alone."""

    failures: list[tuple[Holder, str]] = field(default_factory=list)
    note: str | None = None
    dry_run: bool = False

    @property
    def changed_anything(self) -> bool:
        return bool(self.terminated)

    def summary(self) -> str:
        if self.reachable_before:
            return "the reSpeaker was already reachable; nothing was stopped"
        if self.dry_run:
            if not self.candidates:
                return "dry run: nothing would be stopped"
            first = self.candidates[0]
            return (
                f"dry run: nothing was stopped; would try pid {first.pid} first, "
                f"then re-check the device"
            )
        if self.reachable_after:
            names = ", ".join(str(holder.pid) for holder in self.terminated)
            return f"the reSpeaker is reachable after stopping pid {names}"
        if not self.terminated:
            return "the reSpeaker is unreachable and nothing eligible was found to stop"
        return "the reSpeaker is still unreachable after stopping what looked responsible"


# -- Windows plumbing -------------------------------------------------------

if WINDOWS:  # pragma: no branch
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

    TH32CS_SNAPPROCESS = 0x00000002
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010
    PROCESS_TERMINATE = 0x0001
    SYNCHRONIZE = 0x00100000

    _INVALID_HANDLE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    class MODULEENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", ctypes.c_char * 256),
            ("szExePath", ctypes.c_char * 260),
        ]

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [
            ("Length", ctypes.c_ushort),
            ("MaximumLength", ctypes.c_ushort),
            ("Buffer", ctypes.c_void_p),
        ]

    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Reserved1", ctypes.c_void_p),
            ("PebBaseAddress", ctypes.c_void_p),
            ("Reserved2", ctypes.c_void_p * 2),
            ("UniqueProcessId", ctypes.c_void_p),
            ("Reserved3", ctypes.c_void_p),
        ]

    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    _k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    _k32.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    _k32.Module32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]

    # x64 layout, stable from Windows 7 through 11. Read defensively anyway:
    # a wrong offset must degrade to "no command line", never to a crash.
    _PEB_PROCESS_PARAMETERS = 0x20
    _PARAMS_COMMAND_LINE = 0x70


def _snapshot_processes() -> list[tuple[int, str]]:
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE:
        return []
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        found: list[tuple[int, str]] = []
        if not _k32.Process32First(snap, ctypes.byref(entry)):
            return found
        while True:
            found.append((entry.th32ProcessID, entry.szExeFile.decode("mbcs", "replace")))
            if not _k32.Process32Next(snap, ctypes.byref(entry)):
                return found
    finally:
        _k32.CloseHandle(snap)


def _snapshot_modules(pid: int) -> tuple[list[str], str | None]:
    """Loaded module names and the main image path, or empty when unreadable.

    A snapshot fails for protected processes and across a bitness boundary.
    That is not an error worth reporting: it means this process cannot be
    judged, and one that cannot be judged is never a candidate.
    """
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if not snap or snap == _INVALID_HANDLE:
        return [], None
    try:
        entry = MODULEENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        if not _k32.Module32First(snap, ctypes.byref(entry)):
            return [], None
        image = entry.szExePath.decode("mbcs", "replace") or None
        names: list[str] = []
        while True:
            names.append(entry.szModule.decode("mbcs", "replace").casefold())
            if not _k32.Module32Next(snap, ctypes.byref(entry)):
                return names, image
    finally:
        _k32.CloseHandle(snap)


def _command_line(pid: int) -> str | None:
    """Read a process's command line out of its PEB.

    Worth the trouble because every candidate here is likely to be
    ``python.exe``: without the arguments, a report would name four identical
    processes and leave the choice of which to stop to a coin toss.
    """
    handle = _k32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None
    try:
        info = PROCESS_BASIC_INFORMATION()
        if _ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            return None
        if not info.PebBaseAddress:
            return None

        params = ctypes.c_void_p()
        if not _read(handle, info.PebBaseAddress + _PEB_PROCESS_PARAMETERS, params):
            return None
        if not params.value:
            return None

        command = UNICODE_STRING()
        if not _read(handle, params.value + _PARAMS_COMMAND_LINE, command):
            return None
        if not command.Buffer or not command.Length:
            return None

        buffer = ctypes.create_string_buffer(command.Length)
        if not _read_into(handle, command.Buffer, buffer, command.Length):
            return None
        return buffer.raw.decode("utf-16-le", "replace").strip()
    except Exception:  # pragma: no cover — defensive; layout is version-dependent
        return None
    finally:
        _k32.CloseHandle(handle)


def _read(handle, address: int, target) -> bool:
    return _read_into(handle, address, ctypes.byref(target), ctypes.sizeof(target))


def _read_into(handle, address: int, target, size: int) -> bool:
    read = ctypes.c_size_t(0)
    ok = _k32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), target, size, ctypes.byref(read)
    )
    return bool(ok) and read.value == size


# -- identification ---------------------------------------------------------


def find_holders(*, exclude: Collection[int] = ()) -> list[Holder]:
    """Processes that look like they are holding a USB device, best guess first.

    Never includes this process. Returns an empty list on anything but Windows,
    where the exclusivity this exists to work around does not arise.
    """
    if not WINDOWS:
        return []

    skip = {0, 4, os.getpid(), *exclude}
    holders: list[Holder] = []

    for pid, name in _snapshot_processes():
        if pid in skip:
            continue
        modules, image = _snapshot_modules(pid)
        if not modules:
            continue

        evidence = [module for module in modules if module in STRONG_MODULES]
        confidence = "strong" if evidence else ""
        backends = [module for module in modules if module in BACKEND_MODULES]
        if backends:
            evidence.extend(backends)
            confidence = confidence or "likely"
        if not confidence:
            continue

        holders.append(
            Holder(
                pid=pid,
                executable=image or name,
                command_line=_command_line(pid),
                evidence=tuple(sorted(evidence)),
                confidence=confidence,
            )
        )

    holders.sort(key=lambda holder: holder.rank)
    return holders


# -- taking the device ------------------------------------------------------


def release_device(
    probe: Callable[[], bool],
    *,
    dry_run: bool = False,
    only_related: bool = True,
    limit: int = 4,
    settle_s: float = 1.5,
    exclude: Collection[int] = (),
) -> ReleaseReport:
    """Stop whatever is holding the device, one process at a time.

    ``probe`` answers "can the reSpeaker be talked to now". It is asked before
    anything is stopped, and again after each one — so the process actually in
    the way is the last one stopped, and a bystander holding some other USB
    device is never reached.

    ``only_related`` is the default because the USB evidence alone is not
    selective enough to kill on: peripheral software holds WinUSB handles
    permanently, and it is never holding this device. Processes it excludes are
    still reported, so a genuinely unknown holder can be seen and acted on
    deliberately rather than being terminated by a guess.

    ``limit`` caps how many processes may be stopped in one attempt. Reaching it
    means the guess was wrong, and going further would be flailing at a machine
    rather than solving anything.
    """
    if probe():
        return ReleaseReport(reachable_before=True, reachable_after=True)

    found = find_holders(exclude=exclude)
    report = ReleaseReport(reachable_before=False, reachable_after=False, dry_run=dry_run)
    if not found:
        report.note = (
            "no process on this machine has a USB backend loaded, so something "
            "other than contention is in the way — a driver binding, or a "
            "permission this account does not have"
        )
        logger.warning("%s", report.note)
        return report

    holders = [holder for holder in found if holder.related] if only_related else found
    report.skipped = [holder for holder in found if holder not in holders]
    if not holders:
        report.note = (
            "the processes holding USB devices are not reSpeaker software, so "
            "none was stopped; look at them and, if one really is in the way, "
            "allow it explicitly"
        )
        logger.warning("%s", report.note)
        return report

    if dry_run:
        report.candidates = holders
        return report

    for index, holder in enumerate(holders):
        if len(report.terminated) >= limit:
            report.skipped.extend(holders[index:])
            report.note = f"stopped at the limit of {limit} processes"
            break

        logger.warning("stopping %s to take the reSpeaker", holder.describe())
        error = _terminate(holder.pid, settle_s)
        if error is not None:
            report.failures.append((holder, error))
            logger.warning("could not stop pid %s: %s", holder.pid, error)
            continue
        report.terminated.append(holder)

        # Give the driver a moment to tear the old handle down: the process is
        # gone before its device handle is, and probing into that window would
        # blame the wrong process for still holding it.
        deadline = time.monotonic() + settle_s
        while time.monotonic() < deadline:
            if probe():
                report.reachable_after = True
                logger.info("the reSpeaker is reachable again")
                return report
            time.sleep(0.1)

    report.reachable_after = probe()
    return report


def _terminate(pid: int, timeout_s: float) -> str | None:
    """Stop one process. Returns why not, or ``None`` when it is gone."""
    handle = _k32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False, pid)
    if not handle:
        code = ctypes.get_last_error()
        if code == 5:
            return "access denied — it runs as another user or elevated"
        return f"cannot open the process (error {code})"
    try:
        if not _k32.TerminateProcess(handle, 1):
            return f"terminate failed (error {ctypes.get_last_error()})"
        # 0x102 is WAIT_TIMEOUT: asked to stop, still there.
        if _k32.WaitForSingleObject(handle, int(timeout_s * 1000)) == 0x102:
            return "it did not exit in time"
        return None
    finally:
        _k32.CloseHandle(handle)


def device_probe(vid: int | None = None, pid: int | None = None) -> Callable[[], bool]:
    """A probe that answers whether this reSpeaker can actually be talked to.

    Enumeration is not the question — a held device still enumerates. The probe
    performs a real read, which is the thing that returns ``Errno 13`` while
    somebody else has the handle.
    """
    from . import xvf

    def probe() -> bool:
        try:
            device = xvf.find(
                vid if vid is not None else xvf.VENDOR_ID,
                pid if pid is not None else xvf.PRODUCT_ID,
            )
        except Exception:
            return False
        if device is None:
            return False
        try:
            device.read("VERSION")
            return True
        except Exception:
            return False
        finally:
            try:
                device.close()
            except Exception:
                pass

    return probe


def as_dicts(holders: Iterable[Holder]) -> list[dict]:
    """Holders in a shape the CLI can print as JSON."""
    return [
        {
            "pid": holder.pid,
            "confidence": holder.confidence,
            "related": holder.related,
            "executable": holder.executable,
            "command_line": holder.command_line,
            "evidence": list(holder.evidence),
        }
        for holder in holders
    ]


__all__ = [
    "BACKEND_MODULES",
    "Holder",
    "ReleaseReport",
    "STRONG_MODULES",
    "as_dicts",
    "device_probe",
    "find_holders",
    "release_device",
]
