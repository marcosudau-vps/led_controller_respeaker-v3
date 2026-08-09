# lefx-studio

A window for the things that are awkward from a command line: watching an
effect run, moving its parameters while it does, pointing it at real hardware or
at the simulator without restarting anything, measuring how the microphone array
sits relative to the ring, and writing a new effect source from what you ended
up with.

```bash
uv run lefx-studio
```

## As a standalone tool

```bash
uv run --group build python scripts/build_studio.py --onedir
```

```bash
lefx-studio.exe --project C:\path	oepo
```

The executable is a real tool, not a demo: it reads the catalogue out of a
checkout, writes sources into it, and builds them. Which checkout is a runtime
question — `--project`, or the last one used, or the working directory, and
`Projekt / Projekt öffnen` switches at any time.

Two things a bundle silently loses, both handled in `scripts/build_studio.py`
and both asserted by `tests/studio/test_project.py`: the `.dist-info` metadata
the device entry points are read from, and the standard library modules an
effect package is allowed to import. Without the first the executable offers no
device; without the second a catalogue that loads in the checkout fails one
effect at a time.

```bash
lefx-studio.exe --self-check --project C:\path	oepo
```

asks both questions by doing them — discovers the outputs, loads the catalogue,
renders every definition — and is the way to find out whether a build is
complete.

The studio runs its own engine in-process. It is not a client of `lefx serve` —
that is what lets it render a source that has not been built yet, which is the
whole point of editing one here.

Only one process can hold the reSpeaker at a time. If a service is already
running, the studio says so instead of fighting it for the device; choose
`simulator` or `null` as the output, or stop the service first.

## What is where

| Module | Qt | Purpose |
|---|---|---|
| `session` | no | The embedded controller: engine, chosen output, frame tap |
| `catalogue` | no | Browsing and filtering the loaded definitions |
| `calibrate` | no | Circular statistics and the fit behind the calibration page |
| `authoring` | no | Finding a source directory again, and writing a preset into it |
| `blueprint` | no | A definition being designed; builds it, then prints it |
| `parameters` | yes | Editors built from a definition's parameter schema |
| `ring` | yes | The live monitor, mirroring what the device is being sent |
| `calibration_page` | yes | Walking the ring in half-LED steps |
| `source_editor` | yes | Designing a new definition and packing it |
| `preset_dialog` | yes | Naming the values on screen and keeping them |
| `window` | yes | The three pages, and the output they share |
| `app` | yes | The console script |

The Qt-free modules are that way so they can be tested without a display — and
they hold every decision the studio makes.

## The three pages

**Player.** Search the catalogue, pick an output, and tune. The controls are
generated from each definition's parameter schema, so an effect written
tomorrow gets a full set without this package changing. Live by default, except
for events, which are never repeated by a moving slider.

**Kalibrierung.** Light a known bearing, speak from it, and let it work out how
the microphone array is rotated against the ring. Runs against whichever device
is attached; the answer is written per device into `doa_calibration.json`.

**Neuer Effekt.** Design a definition, watch it render on the real device, then
write `effect.py` + `effect.yaml` and pack a single `.lefx`. Nothing invalid can
be entered: the fields a parameter type does not have are switched off, reserved
names arrive with their fixed type and range, and the real definition is
constructed on every edit — Save is simply unavailable while that fails.
