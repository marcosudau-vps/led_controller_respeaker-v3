"""Pure render functions. The compiler embeds these exact functions in exports.

No authoring imports: this module is also the source library for standalone
packages. Keep function dependencies in COMMON_FUNCTIONS in compiler.py.
"""

import colorsys
import math

from lefx.sdk import parse_color


def point(p, count):
    yield int(p["position"] * count + 0.5) % count, parse_color(p["color"]), p["brightness"]


def segment(p, count):
    start = int(p["position"] * count + 0.5) % count
    length = min(count, max(0, int(p["length"] * count + 0.5)))
    for step in range(length):
        yield (start + step) % count, parse_color(p["color"]), p["brightness"]


def fill(p, count):
    for index in range(count):
        yield index, parse_color(p["color"]), p["brightness"]


def gradient(p, count):
    first, last = parse_color(p["color"]), parse_color(p["end_color"])
    for index in range(count):
        ratio = index / max(1, count - 1)
        channels = [((first >> shift) & 255) * (1 - ratio) +
                    ((last >> shift) & 255) * ratio for shift in (16, 8, 0)]
        yield index, (int(channels[0]) << 16) | (int(channels[1]) << 8) | int(channels[2]), p["brightness"]


def rotation(p, time, state, reverse):
    direction = -1 if bool(p["reverse"]) != bool(reverse) else 1
    state["turns"] = p["phase"] + direction * time * p["rate"]


def blink(p, time, state, reverse):
    phase = (time * p["frequency"] + p["phase"]) % 1.0
    state["gain"] = p["maximum"] if phase < p["duty"] else p["minimum"]


def pulse(p, time, state, reverse):
    wave = (1 - math.cos(math.tau * (time * p["frequency"] + p["phase"]))) / 2
    state["shift"] += p["minimum"] + (p["maximum"] - p["minimum"]) * wave


def color_cycle(p, time, state, reverse):
    state["hue"] = (time * p["rate"] + p["phase"]) % 1.0


def sparkle(p, time, state, reverse):
    state["sparkle"] = (int(math.floor(time * p["frequency"])), p["seed"], p["density"])


def values_for(item, overrides):
    return {name: overrides.get((item["id"], name), value)
            for name, value in item["properties"].items()}


def elements_in(children):
    for child in children:
        if child["type"] == "group":
            yield from elements_in(child["children"])
        else:
            yield child


def shift_limits(intensities):
    positive = [value for value in intensities if value > 0]
    return (-min(positive) * 100, (1 - max(positive)) * 100) if positive else (0.0, 0.0)


def compose_pixel(below, above, mode, opacity):
    if above is None:
        return below
    low = below if below is not None else (0.0, 0.0, 0.0)
    if mode == "over":
        return tuple(a * opacity + b * (1 - opacity) for a, b in zip(above, low))
    if mode == "add":
        return tuple(min(255.0, b + a * opacity) for a, b in zip(above, low))
    return tuple(max(b, a * opacity) for a, b in zip(above, low))


def render_scene(scene, ctx):
    count = ctx.led_count
    overrides = {(entry["target"], entry["property"]): ctx.params[entry["name"]]
                 for entry in scene["exposures"]}
    time = max(0.0, ctx.elapsed) * ctx.params.get("speed", 1.0)
    output = [None] * count
    for layer in scene["layers"]:
        if not layer["enabled"]:
            continue
        lp = values_for(layer, overrides)
        if lp["opacity"] == 0:
            continue
        state = {"turns": 0.0, "gain": 1.0, "shift": lp["brightness_shift"], "hue": 0.0}
        for animation in scene["animations"]:
            if animation["target"] == layer["id"]:
                ANIMATIONS[animation["type"]](values_for(animation, overrides), time, state,
                                              ctx.params.get("reverse", False))
        samples = [None] * count
        intensities = []
        for element in elements_in(layer["children"]):
            props = values_for(element, overrides)
            intensities.append(props["brightness"])
            for index, color, intensity in ELEMENTS[element["type"]](props, count):
                samples[index] = (color, intensity)
        lower, upper = shift_limits(intensities)
        shift = min(upper, max(lower, state["shift"])) / 100
        offset = int(math.floor((state["turns"] % 1.0) * count + 0.5)) % count
        mask_start = int(lp["mask_start"] * count + 0.5) % count
        mask_length = min(count, int(lp["mask_length"] * count + 0.5))
        for index, sample in enumerate(samples):
            inside = (index - mask_start) % count < mask_length
            if sample is None or inside == lp["mask_invert"]:
                continue
            color, intensity = sample
            intensity = (intensity + shift if intensity > 0 else 0) * state["gain"]
            if "sparkle" in state:
                tick, seed, density = state["sparkle"]
                # Integer hash, stable across processes, frame rates and Python seeds.
                hashed = ((index + 1) * 374761393 + tick * 668265263 + seed * 1442695041) & 0xFFFFFFFF
                hashed = ((hashed ^ (hashed >> 13)) * 1274126177) & 0xFFFFFFFF
                intensity *= (hashed ^ (hashed >> 16)) / 4294967296 < density
            channels = tuple((color >> bit) & 255 for bit in (16, 8, 0))
            if state["hue"]:
                hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in channels))
                channels = tuple(channel * 255 for channel in
                                 colorsys.hsv_to_rgb((hue + state["hue"]) % 1, saturation, value))
            above = tuple(channel * intensity for channel in channels)
            dest = (index + offset) % count
            output[dest] = compose_pixel(output[dest], above, layer["blend"], lp["opacity"])
    tint = parse_color(ctx.params.get("color", "#FFFFFF"))
    gain = ctx.params.get("brightness", 1.0)
    result = []
    for pixel in output:
        if pixel is None:
            result.append(0 if scene["effect"]["composition"] == "opaque" else None)
        else:
            channels = [max(0, min(255, int(channel * gain * ((tint >> bit) & 255) / 255 + 1e-9)))
                        for channel, bit in zip(pixel, (16, 8, 0))]
            result.append((channels[0] << 16) | (channels[1] << 8) | channels[2])
    return result
