"""Step points for looking at an animation one state at a time. Experimental.

A step plan only answers *when* to look; what is seen still comes from the
compiled design rendered at that moment. It deliberately is not a block
property: no animation is required to declare a number of positions, and the
plans below are read off the current kernel formulas for the Lab only.

Four quantities stay apart here, because conflating them is the mistake this
view exists to make visible:

* the physical LED count — how many positions the ring has;
* a step plan's points per cycle — when the animation's own state changes
  (a rotation on twelve LEDs has twelve offsets, a blink has two phases);
* the number of *different frames* in one cycle — an A/B pattern rotating over
  twelve LEDs passes twelve offsets but shows only two different pictures;
* elapsed time and frame counters — neither is a step.

Where an animation changes continuously (pulse, colour cycle) there is no
natural state to step to, and the plan says so: its points are labelled
"Abtastpunkte", evenly spaced samples, not states.
"""

from dataclasses import dataclass, replace
import math

from .blocks import BLOCKS

EPSILON = 1e-9


@dataclass(frozen=True)
class StepPlan:
    title: str
    natural: bool
    """True when the points are states of the animation, False for samples."""
    origin: float
    period: float
    offsets: tuple
    labels: tuple
    cyclic: bool = True
    """Cyclic plans repeat their labels; the others count onwards (ticks)."""

    @property
    def per_cycle(self):
        return len(self.offsets)

    def time(self, index):
        cycle, point = divmod(index, len(self.offsets))
        return self.origin + cycle * self.period + self.offsets[point]

    def label(self, index):
        cycle, point = divmod(index, len(self.offsets))
        return self.labels[point] if self.cyclic else f"{self.labels[point]} {index}"

    def _around(self, elapsed):
        base = math.floor((elapsed - self.origin) / self.period) * len(self.offsets)
        return range(base - len(self.offsets), base + 2 * len(self.offsets) + 1)

    def nearest(self, elapsed):
        return min(self._around(elapsed), key=lambda index: abs(self.time(index) - elapsed))

    def after(self, elapsed):
        return min(index for index in self._around(elapsed) if self.time(index) > elapsed + EPSILON)

    def before(self, elapsed):
        return max(index for index in self._around(elapsed) if self.time(index) < elapsed - EPSILON)


def samples(title, origin, period, count):
    count = max(1, int(count))
    return StepPlan(title, False, origin, period, tuple(period * i / count for i in range(count)),
                    tuple(f"Abtastpunkt {i + 1} von {count}" for i in range(count)))


def uniform(interval):
    interval = max(0.001, float(interval))
    return StepPlan(f"Abtastpunkte alle {interval:g} s", False, 0.0, interval, (0.0,),
                    ("Abtastpunkt",), cyclic=False)


def plan_for(animation, led_count, sample_count=8):
    """The plan one animation suggests, or ``None`` if it never changes."""
    p = animation["properties"]
    kind = animation["type"]
    label = BLOCKS[kind].label
    if kind == "rotation":
        direction = -1 if p["reverse"] else 1
        velocity = direction * p["rate"]
        if velocity == 0:
            return None
        # The kernel shows offset k while turns * count rounds to k, so the
        # centre of state k is where turns * count == k exactly.
        spacing = 1 / (abs(velocity) * led_count)
        sign = 1 if velocity > 0 else -1
        return StepPlan(f"{label}: LED-Versätze ({led_count} je Umdrehung)", True,
                        -p["phase"] / velocity, spacing * led_count,
                        tuple(spacing * m for m in range(led_count)),
                        tuple(f"Versatz {(sign * m) % led_count} von {led_count} LEDs" for m in range(led_count)))
    if kind == "blink":
        if p["frequency"] <= 0:
            return None
        period = 1 / p["frequency"]
        origin = -p["phase"] * period
        duty = p["duty"]
        if duty <= 0 or duty >= 1 or p["minimum"] == p["maximum"]:
            return StepPlan(f"{label}: konstant", True, origin, period, (period / 2,), ("Konstant",))
        return StepPlan(f"{label}: Phasen an/aus", True, origin, period,
                        (duty / 2 * period, (1 + duty) / 2 * period), ("Phase an (1 von 2)", "Phase aus (2 von 2)"))
    if kind == "sparkle":
        if p["frequency"] <= 0:
            return None
        period = 1 / p["frequency"]
        return StepPlan(f"{label}: Funkeltakte", True, 0.0, period, (period / 2,), ("Takt",),
                        cyclic=False)
    if kind == "pulse":
        if p["frequency"] <= 0:
            return None
        period = 1 / p["frequency"]
        return samples(f"{label}: Abtastpunkte ({sample_count} je Periode)",
                       -p["phase"] * period, period, sample_count)
    if kind == "color_cycle":
        if p["rate"] <= 0:
            return None
        period = 1 / p["rate"]
        return samples(f"{label}: Abtastpunkte ({sample_count} je Farbzyklus)",
                       -p["phase"] * period, period, sample_count)
    return None


def plans(document, led_count, sample_count=8):
    """Every animation's plan, keyed by animation id, titled with its layer."""
    names = {layer["id"]: layer["name"] for layer in document["layers"]}
    result = {}
    for animation in document["animations"]:
        plan = plan_for(animation, led_count, sample_count)
        if plan is not None:
            result[animation["id"]] = replace(plan, title=f"{names[animation['target']]} · {plan.title}")
    return result


def distinct_frames(render, plan, first_index=0):
    """How many different pictures one cycle of ``plan`` shows.

    Counted on whole rendered frames, so everything else that moves in the
    preview counts too; that is what was seen, which is the point.
    """
    return len({tuple(render(max(0.0, plan.time(first_index + i)))) for i in range(plan.per_cycle)})


__all__ = ["StepPlan", "distinct_frames", "plan_for", "plans", "samples", "uniform"]
