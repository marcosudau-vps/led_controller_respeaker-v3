"""An effect being designed, before it is a file.

The whole idea here is one move: **build the real definition first, emit the
source afterwards**. A blueprint is turned into an actual ``StateDefinition`` or
``EventDefinition`` — which validates itself in ``__post_init__`` — and only a
definition that survived that is ever written to disk. So the editor cannot
produce an ``effect.py`` the schema rejects, not because it checks carefully but
because the thing it prints was already constructed.

That inverts the usual arrangement, where a generator writes text and a
validator complains about it later, in another process, after a build.

What is *not* generated is the body of ``render``. That is the part with the
idea in it, and it is typed by a person; the editor imports the module to run
it, which is also how it finds out whether it works.

No Qt: this decides what a source says, and the page collects it.
"""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from lefx.authoring import SourceError, pack_effect, smoke_render, validate_effect_source
from lefx.sdk import (
    MISSING,
    RESERVED_PARAMETERS,
    ColorModel,
    CompositionMode,
    ControlledOverlayDefinition,
    DefinitionBase,
    DefinitionKind,
    DurationField,
    EventDefinition,
    InputMode,
    InputSamplingPolicy,
    ParamDefinition,
    ParamType,
    SchemaError,
    StateDefinition,
    StateSlot,
    TimedOverlayDefinition,
)

DEFINITION_CLASSES: Mapping[DefinitionKind, type[DefinitionBase]] = {
    DefinitionKind.STATE: StateDefinition,
    DefinitionKind.CONTROLLED_OVERLAY: ControlledOverlayDefinition,
    DefinitionKind.TIMED_OVERLAY: TimedOverlayDefinition,
    DefinitionKind.EVENT: EventDefinition,
}
"""One class per lifecycle form. A test asserts this covers every kind, so a
form added to the SDK cannot quietly become one the editor cannot produce."""

MANIFEST_NAME = "effect.yaml"
SOURCE_NAME = "effect.py"


# -- what each parameter type accepts ---------------------------------------


@dataclass(slots=True, frozen=True)
class TypeSupport:
    """Which companion fields a type accepts, so the form can grey out the rest.

    A restatement of the SDK's own matrix, kept here because a form has to know
    it *before* a value is entered rather than after it is rejected.
    ``tests/studio/test_blueprint.py`` probes the SDK for every row, so the two
    cannot drift apart without a failure.
    """

    bounds: bool = False
    integral_bounds: bool = False
    enum_values: bool = False
    units: tuple[str, ...] = ()

    @property
    def unit_allowed(self) -> bool:
        return bool(self.units)


TYPE_SUPPORT: Mapping[ParamType, TypeSupport] = {
    ParamType.BOOL: TypeSupport(),
    ParamType.INT: TypeSupport(
        bounds=True, integral_bounds=True,
        units=("ms", "deg", "px", "count", "index", "ratio", "multiplier", "percent"),
    ),
    ParamType.FLOAT: TypeSupport(
        bounds=True,
        units=("ms", "deg", "px", "count", "ratio", "multiplier", "percent", "hz"),
    ),
    ParamType.DURATION_MS: TypeSupport(bounds=True, integral_bounds=True, units=("ms",)),
    ParamType.ANGLE_DEG: TypeSupport(units=("deg",)),
    ParamType.ENUM: TypeSupport(enum_values=True),
    ParamType.COLOR: TypeSupport(),
    ParamType.COLOR_LIST: TypeSupport(bounds=True, integral_bounds=True, units=("count",)),
    ParamType.GRADIENT: TypeSupport(),
    ParamType.COLOR_RANGE: TypeSupport(),
}

# Ranges the *editor's* own number boxes offer. Wide enough that nothing
# reasonable is out of reach, narrow enough that a slip of the finger does not
# produce a duration of four hours. These bound the form, never the schema.
BOUND_LIMIT = 1_000_000.0
DURATION_LIMIT_MS = 600_000
"""Ten minutes. Longer than any effect in the catalogue by two orders of
magnitude, and short enough that a stray digit is visible as one."""

COLOR_LIST_LIMIT = 64
PRIORITY_LIMIT = 1_000
VERSION_LIMIT = 999

DEFAULT_COLOR = "#3399FF"


def default_for(kind: ParamType) -> Any:
    """A value of the right shape to start an editor from."""
    return {
        ParamType.BOOL: False,
        ParamType.INT: 0,
        ParamType.FLOAT: 0.0,
        ParamType.DURATION_MS: 1000,
        ParamType.ANGLE_DEG: 0.0,
        ParamType.ENUM: "first",
        ParamType.COLOR: DEFAULT_COLOR,
        ParamType.COLOR_LIST: [DEFAULT_COLOR, "#FF9F1A"],
        ParamType.GRADIENT: [{"at": 0.0, "color": "#000000"}, {"at": 1.0, "color": DEFAULT_COLOR}],
        ParamType.COLOR_RANGE: {
            "hue": [0.0, 360.0], "saturation": [0.4, 1.0], "brightness": [0.4, 1.0],
        },
    }[kind]


# -- a single parameter -----------------------------------------------------


@dataclass(slots=True)
class ParameterBlueprint:
    """One field of a configuration or runtime input schema, as being edited."""

    name: str = ""
    type: ParamType = ParamType.FLOAT
    default: Any = None
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    enum_values: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    nullable: bool = False
    required: bool = False

    @property
    def support(self) -> TypeSupport:
        return TYPE_SUPPORT[self.type]

    @property
    def reserved(self) -> bool:
        return self.name in RESERVED_PARAMETERS

    def build(self) -> ParamDefinition:
        """The real thing, which refuses to exist if it is wrong."""
        support = self.support
        return ParamDefinition(
            name=self.name,
            type=self.type,
            default=MISSING if self.required else self.default,
            required=self.required,
            description=self.description,
            minimum=self.minimum if support.bounds else None,
            maximum=self.maximum if support.bounds else None,
            unit=self.unit if support.unit_allowed else None,
            enum_values=self.enum_values if support.enum_values else (),
            aliases=self.aliases,
            nullable=self.nullable,
        )

    def problem(self) -> str | None:
        """Why this parameter cannot be built, in one sentence, or ``None``."""
        if not self.name:
            return "Ein Parameter braucht einen Namen."
        if not _is_identifier(self.name):
            return f"{self.name!r}: nur Kleinbuchstaben, Ziffern und Unterstriche, kein führender."
        try:
            self.build()
        except (SchemaError, ValueError, TypeError) as exc:
            return f"{self.name}: {exc}"
        return None

    def code(self) -> str:
        """The parameter as it appears in the generated source."""
        parts = [f'name="{self.name}"', f"type=ParamType.{self.type.name}"]
        if self.required:
            parts.append("required=True")
        else:
            parts.append(f"default={_literal(self.default)}")
        support = self.support
        if support.bounds and self.minimum is not None:
            parts.append(f"minimum={_number(self.minimum, support.integral_bounds)}")
        if support.bounds and self.maximum is not None:
            parts.append(f"maximum={_number(self.maximum, support.integral_bounds)}")
        if support.enum_values and self.enum_values:
            parts.append(f"enum_values={_literal(tuple(self.enum_values))}")
        if support.unit_allowed and self.unit:
            parts.append(f'unit="{self.unit}"')
        if self.nullable:
            parts.append("nullable=True")
        if self.aliases:
            parts.append(f"aliases={_literal(tuple(self.aliases))}")
        if self.description:
            parts.append(f"description={_literal(self.description)}")
        body = ",\n                ".join(parts)
        return f'"{self.name}": ParamDefinition(\n                {body},\n            )'


def reserved_blueprint(name: str) -> ParameterBlueprint:
    """A reserved parameter, pre-filled the only way it is allowed to look.

    ``brightness`` is a float from zero to one everywhere in the system; there
    is nothing to decide about it, so the editor does not ask.
    """
    rule = RESERVED_PARAMETERS[name]
    blueprint = ParameterBlueprint(name=name, type=rule.type, default=default_for(rule.type))
    if rule.exact_minimum is not None:
        blueprint.minimum = rule.exact_minimum
    if rule.exact_maximum is not None:
        blueprint.maximum = rule.exact_maximum
    if rule.minimum_at_least is not None:
        blueprint.minimum = float(rule.minimum_at_least)
    if rule.minimum_above_zero:
        blueprint.minimum = 0.1
        blueprint.maximum = 8.0
    if name == "secondary_color":
        # A contrasting default, so a two-colour definition looks like one the
        # first time it renders rather than like a single-colour one.
        blueprint.default = "#FF9F1A"
        blueprint.description = "Zweite Farbe."
    elif name == "background_color":
        blueprint.default = "#000000"
        blueprint.description = "Hintergrundfarbe."
    elif name == "brightness":
        blueprint.default = 1.0
        blueprint.description = "Helligkeitsfaktor."
    elif name == "speed":
        blueprint.default = 1.0
        blueprint.description = "Geschwindigkeit."
    elif name == "reverse":
        blueprint.default = False
        blueprint.description = "Richtung umkehren."
    elif name in ("duration_ms", "total_ms"):
        blueprint.default = 1000
        blueprint.maximum = float(DURATION_LIMIT_MS)
        blueprint.description = "Laufzeit."
    elif name == "progress":
        blueprint.default = 0.0
        blueprint.description = "Fortschritt in Prozent."
    return blueprint


# -- the effect -------------------------------------------------------------


@dataclass(slots=True)
class EffectBlueprint:
    """Everything a source directory needs, before it is one."""

    kind: DefinitionKind = DefinitionKind.STATE
    effect_id: str = ""
    title: str = ""
    description: str = ""
    source_id: str = "my-set"
    color_model: ColorModel = ColorModel.MONO
    composition: CompositionMode = CompositionMode.OPAQUE
    animated: bool = False
    directional: bool = False
    tags: tuple[str, ...] = ()
    version: int = 1

    parameters: list[ParameterBlueprint] = field(default_factory=list)
    runtime_inputs: list[ParameterBlueprint] = field(default_factory=list)

    slots: tuple[StateSlot, ...] = (StateSlot.PRIMARY,)
    restorable: bool = False

    duration_field: DurationField = DurationField.DURATION_MS
    supports_duration_override: bool = False
    default_priority: int | None = None

    sampling_mode: InputMode = InputMode.PUSH
    provider_id: str | None = None
    interval_ms: int = 0

    render_body: str = ""

    # -- identity -----------------------------------------------------------

    @property
    def class_name(self) -> str:
        return "".join(part.capitalize() for part in self.effect_id.split("_")) or "Effect"

    @property
    def folder(self) -> str:
        """States, overlays and events live in their own folders in a set."""
        return {
            DefinitionKind.STATE: "states",
            DefinitionKind.CONTROLLED_OVERLAY: "overlays",
            DefinitionKind.TIMED_OVERLAY: "overlays",
            DefinitionKind.EVENT: "events",
        }[self.kind]

    @property
    def finite(self) -> bool:
        return self.kind in (DefinitionKind.TIMED_OVERLAY, DefinitionKind.EVENT)

    # -- what the schema demands -------------------------------------------

    def required_parameters(self) -> list[str]:
        """Config fields this combination of choices makes mandatory.

        Derived from the same rules the definition enforces, so the editor can
        offer to add them instead of waiting for the constructor to complain.
        """
        needed: list[str] = []
        model_fields = {
            ColorModel.NONE: [],
            ColorModel.MONO: ["color"],
            ColorModel.DUAL: ["color", "secondary_color"],
            ColorModel.PALETTE: ["colors"],
            ColorModel.GRADIENT: ["gradient"],
            ColorModel.RANDOM_RANGE: ["color_range", "random_seed"],
        }[self.color_model]
        needed.extend(model_fields)
        if self.color_model is not ColorModel.NONE:
            needed.append("brightness")
        if self.animated:
            needed.append("speed")
        if self.directional:
            needed.append("reverse")
        if self.finite:
            needed.append(self.duration_field.value)
        return [name for name in needed if name not in {p.name for p in self.parameters}]

    def forbidden_parameters(self) -> list[str]:
        """Fields present that this combination of choices does not allow."""
        names = {p.name for p in self.parameters}
        wrong: list[str] = []
        if self.color_model is ColorModel.NONE:
            wrong.extend(sorted(names & {"color", "secondary_color", "colors", "gradient",
                                         "color_range", "random_seed", "brightness"}))
        if not self.animated and "speed" in names:
            wrong.append("speed")
        if not self.directional and "reverse" in names:
            wrong.append("reverse")
        if self.kind is DefinitionKind.STATE:
            wrong.extend(sorted(names & {"duration_ms", "total_ms"}))
        if self.finite:
            other = "total_ms" if self.duration_field is DurationField.DURATION_MS else "duration_ms"
            if other in names:
                wrong.append(other)
        return wrong

    def add_missing_parameters(self) -> list[str]:
        """Fill in what the schema demands, correctly typed. Returns what it added."""
        added = self.required_parameters()
        for name in added:
            self.parameters.append(reserved_blueprint(name))
        return added

    # -- becoming real ------------------------------------------------------

    def definition(self) -> DefinitionBase:
        """Construct the actual definition. Raises if anything is wrong."""
        common: dict[str, Any] = {
            "id": self.effect_id,
            "title": self.title,
            "description": self.description,
            "parameter_schema": {p.name: p.build() for p in self.parameters},
            "color_model": self.color_model,
            "composition": self.composition,
            "animated": self.animated,
            "directional": self.directional,
            "tags": tuple(self.tags),
            "version": self.version,
        }
        if self.kind is DefinitionKind.STATE:
            common.update(slots=tuple(self.slots), restorable=self.restorable)
        elif self.kind is DefinitionKind.CONTROLLED_OVERLAY:
            common.update(
                runtime_inputs={p.name: p.build() for p in self.runtime_inputs},
                sampling=InputSamplingPolicy(
                    mode=self.sampling_mode,
                    provider_id=self.provider_id if self.sampling_mode is InputMode.PULL else None,
                    interval_ms=self.interval_ms,
                ),
            )
        else:
            common.update(
                duration_field=self.duration_field,
                supports_duration_override=self.supports_duration_override,
            )
            if self.kind is DefinitionKind.EVENT:
                common.update(default_priority=self.default_priority)
        return DEFINITION_CLASSES[self.kind](**common)

    def problems(self) -> list[str]:
        """Everything standing between this blueprint and a valid source."""
        found: list[str] = []
        if not self.effect_id:
            found.append("Die Definition braucht eine Id.")
        elif not _is_identifier(self.effect_id):
            found.append(
                f"Id {self.effect_id!r}: nur Kleinbuchstaben, Ziffern und Unterstriche."
            )
        if not self.title.strip():
            found.append("Die Definition braucht einen Titel.")
        if not self.description.strip():
            found.append("Die Definition braucht eine Beschreibung.")
        if not _is_source_id(self.source_id):
            found.append("Die Set-Kennung darf nur Buchstaben, Ziffern und Bindestriche enthalten.")

        seen: set[str] = set()
        for parameter in [*self.parameters, *self.runtime_inputs]:
            problem = parameter.problem()
            if problem:
                found.append(problem)
            if parameter.name in seen:
                found.append(f"{parameter.name!r} ist doppelt deklariert.")
            seen.add(parameter.name)

        if not self.render_body.strip():
            found.append("render() hat noch keinen Rumpf.")

        if not found:
            # Only now: the constructor sees combinations no single field can.
            try:
                self.definition()
            except (SchemaError, ValueError, TypeError) as exc:
                found.append(str(exc))

        if not found:
            problem = self.render_problem()
            if problem is not None:
                found.append(problem)
        return found

    def render_problem(self) -> str | None:
        """Whether the body actually runs, asked the way the validator asks it.

        Without this, a definition whose ``render`` throws would be perfectly
        "valid" right up to the moment it is written — and then be refused by
        the source validator, after the dialog had closed over it. The same
        smoke render happens here instead, while the body is still on screen.

        It renders at three ring sizes because that is what the validator does,
        and a body that only works at twelve is a bug worth finding now.
        """
        try:
            effect_class = compile_blueprint(self)
        except SyntaxError as exc:
            return f"render() ist kein gültiges Python: Zeile {exc.lineno}: {exc.msg}"
        except Exception as exc:
            return f"Die Definition lässt sich nicht laden: {exc}"

        try:
            smoke_render(effect_class)
        except Exception as exc:
            return str(exc)
        return None

    @property
    def valid(self) -> bool:
        return not self.problems()

    # -- becoming a file ----------------------------------------------------

    def source_code(self) -> str:
        """The ``effect.py`` text. Only reachable once the definition is real."""
        definition = self.definition()  # never emit what would not construct
        del definition

        imports = self._imports()
        lines = [
            "from lefx.sdk import (",
            *(f"    {name}," for name in imports),
            ")",
            "",
            "",
            f"class {self.class_name}(BaseEffect):",
            f'    """{self.title}',
            "",
            *(f"    {line}" for line in _wrap(self.description)),
            '    """',
            "",
            f"    definition = {type(self.definition()).__name__}(",
            f'        id="{self.effect_id}",',
            f"        title={_literal(self.title)},",
            f"        description={_literal(self.description)},",
        ]
        if self.parameters:
            lines.append("        parameter_schema={")
            for parameter in self.parameters:
                lines.append(f"            {parameter.code()},")
            lines.append("        },")
        if self.kind is DefinitionKind.CONTROLLED_OVERLAY and self.runtime_inputs:
            lines.append("        runtime_inputs={")
            for parameter in self.runtime_inputs:
                lines.append(f"            {parameter.code()},")
            lines.append("        },")

        lines.append(f"        color_model=ColorModel.{self.color_model.name},")
        lines.append(f"        composition=CompositionMode.{self.composition.name},")
        if self.animated:
            lines.append("        animated=True,")
        if self.directional:
            lines.append("        directional=True,")
        if self.kind is DefinitionKind.STATE:
            slots = ", ".join(f"StateSlot.{slot.name}" for slot in self.slots)
            lines.append(f"        slots=({slots},)," if len(self.slots) == 1
                         else f"        slots=({slots}),")
            if self.restorable:
                lines.append("        restorable=True,")
        if self.kind is DefinitionKind.CONTROLLED_OVERLAY:
            policy = [f"mode=InputMode.{self.sampling_mode.name}"]
            if self.sampling_mode is InputMode.PULL and self.provider_id:
                policy.append(f'provider_id="{self.provider_id}"')
            policy.append(f"interval_ms={self.interval_ms}")
            lines.append(f"        sampling=InputSamplingPolicy({', '.join(policy)}),")
        if self.finite:
            lines.append(f"        duration_field=DurationField.{self.duration_field.name},")
            if self.supports_duration_override:
                lines.append("        supports_duration_override=True,")
            if self.kind is DefinitionKind.EVENT and self.default_priority is not None:
                lines.append(f"        default_priority={self.default_priority},")
        if self.tags:
            lines.append(f"        tags={_literal(tuple(self.tags))},")
        if self.version != 1:
            lines.append(f"        version={self.version},")
        lines.append("    )")
        lines.append("")
        lines.append("    def render(self, ctx: RenderContext) -> list[int | None]:")
        for line in self.render_body.rstrip().splitlines() or ["        return ctx.transparent_frame()"]:
            lines.append(line.rstrip())
        lines.append("")
        return "\n".join(lines)

    def _imports(self) -> list[str]:
        """Only what the generated source actually mentions.

        An unused import would be noise in a file meant to be read as an
        example, and the studio writes these to be read.
        """
        names = {"BaseEffect", "ColorModel", "CompositionMode", "RenderContext"}
        names.add(type(self.definition()).__name__)
        if self.parameters or self.runtime_inputs:
            names |= {"ParamDefinition", "ParamType"}
        if self.kind is DefinitionKind.STATE:
            names.add("StateSlot")
        if self.kind is DefinitionKind.CONTROLLED_OVERLAY:
            names |= {"InputMode", "InputSamplingPolicy"}
        if self.finite:
            names.add("DurationField")
        body = self.render_body
        for helper in ("parse_color", "scale_color", "blend", "position_for_angle",
                       "positions_for_angle", "sector_for_angle", "evenly_spaced_positions",
                       "segment_lengths", "rgb"):
            if re.search(rf"\b{helper}\b", body):
                names.add(helper)
        return sorted(names)

    def manifest_text(self) -> str:
        return (
            "# The class in effect.py is the source of truth for the contract. This\n"
            "# manifest only says where the definition belongs and where to find it.\n"
            f"source_id: {self.source_id}\n"
            "entry_file: effect.py\n"
            f"entry_class: {self.class_name}\n"
        )

    def write(self, parent: str | Path, *, force: bool = False) -> Path:
        """Write the source directory. Refuses to overwrite unless told to."""
        problems = self.problems()
        if problems:
            raise SourceError("; ".join(problems))

        root = Path(parent).expanduser().resolve() / self.effect_id
        source = root / SOURCE_NAME
        if source.exists() and not force:
            raise SourceError(f"{source} existiert bereits.")

        root.mkdir(parents=True, exist_ok=True)
        source.write_text(self.source_code(), encoding="utf-8")
        (root / MANIFEST_NAME).write_text(self.manifest_text(), encoding="utf-8")

        report = validate_effect_source(root)
        if not report.ok:
            # Written and then judged by the tool that will judge it later. The
            # files stay so the errors can be read against them, but the caller
            # is told rather than left to find out at build time.
            raise SourceError(
                f"{self.effect_id} wurde geschrieben, validiert aber nicht: "
                + "; ".join(report.errors)
            )
        return root


def compile_blueprint(blueprint: "EffectBlueprint"):
    """Turn a blueprint's generated source into a class, without touching disk.

    The same import the loader performs, minus the packaging — so a body that
    would not load fails here, while it is still being typed. The module is
    anonymous and thrown away; nothing is registered by looking.
    """
    import types

    module = types.ModuleType(f"_lefx_studio_{blueprint.effect_id or 'draft'}")
    code = compile(blueprint.source_code(), f"<{blueprint.effect_id or 'draft'}>", "exec")
    exec(code, module.__dict__)  # noqa: S102 — running what the author just wrote is the point
    return getattr(module, blueprint.class_name)


def build_package(source_dir: str | Path, output: str | Path) -> dict[str, Any]:
    """Pack one validated source into a single ``.lefx``."""
    root = Path(source_dir).expanduser().resolve()
    report = validate_effect_source(root)
    if not report.ok:
        raise SourceError("; ".join(report.errors))
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return pack_effect(root, target)


# -- starting points --------------------------------------------------------

_BODIES: Mapping[DefinitionKind, str] = {
    DefinitionKind.STATE: (
        '        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])\n'
        "        return [color] * ctx.led_count"
    ),
    DefinitionKind.CONTROLLED_OVERLAY: (
        "        frame = ctx.transparent_frame()\n"
        '        color = scale_color(parse_color(ctx.params["color"]), ctx.params["brightness"])\n'
        "        frame[0] = color\n"
        "        return frame"
    ),
    # The finite forms know how long they have: their declared duration and
    # ctx.elapsed. Fading over that is the smallest body that shows the shape.
    DefinitionKind.TIMED_OVERLAY: (
        '        total = ctx.params["duration_ms"] / 1000.0\n'
        "        fade = max(0.0, 1.0 - (ctx.elapsed / total if total > 0 else 1.0))\n"
        '        color = scale_color(parse_color(ctx.params["color"]),\n'
        '                            ctx.params["brightness"] * fade)\n'
        "        return [color] * ctx.led_count"
    ),
    DefinitionKind.EVENT: (
        '        total = ctx.params["duration_ms"] / 1000.0\n'
        "        fade = max(0.0, 1.0 - (ctx.elapsed / total if total > 0 else 1.0))\n"
        '        color = scale_color(parse_color(ctx.params["color"]),\n'
        '                            ctx.params["brightness"] * fade)\n'
        "        return [color] * ctx.led_count"
    ),
}


def starting_blueprint(kind: DefinitionKind, *, effect_id: str = "", source_id: str = "my-set"):
    """A blueprint that is already valid, so the editor opens on something that runs."""
    blueprint = EffectBlueprint(
        kind=kind,
        effect_id=effect_id,
        title=effect_id.replace("_", " ").title() if effect_id else "",
        description="",
        source_id=source_id,
        composition=(
            CompositionMode.OPAQUE
            if kind is DefinitionKind.STATE
            else CompositionMode.TRANSPARENT
        ),
        render_body=_BODIES[kind],
    )
    blueprint.add_missing_parameters()
    if kind is DefinitionKind.CONTROLLED_OVERLAY:
        blueprint.runtime_inputs.append(
            replace(
                reserved_blueprint("progress"),
                required=False,
                default=0.0,
                description="Wert, der zur Laufzeit geliefert wird.",
            )
        )
    return blueprint


# -- helpers ----------------------------------------------------------------


def _is_identifier(value: str) -> bool:
    return (
        bool(value)
        and value.isidentifier()
        and not value.startswith("_")
        and value == value.lower()
        and not keyword.iskeyword(value)
    )


def _is_source_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value or ""))


def _number(value: float, integral: bool) -> str:
    return str(int(value)) if integral else repr(float(value))


def _literal(value: Any) -> str:
    """A Python literal for a value that came out of a form.

    Double quotes where they are available, because that is how the rest of the
    catalogue is written and these files are meant to be read next to it.
    """
    if isinstance(value, str) and '"' not in value and "\\" not in value:
        return f'"{value}"'
    if isinstance(value, tuple):
        inner = ", ".join(_literal(item) for item in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, list):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{_literal(k)}: {_literal(v)}" for k, v in value.items())
        return "{" + inner + "}"
    return repr(value)


def _wrap(text: str, width: int = 72) -> list[str]:
    import textwrap

    return textwrap.wrap(text.strip(), width=width) or [""]


__all__ = [
    "BOUND_LIMIT",
    "COLOR_LIST_LIMIT",
    "DEFAULT_COLOR",
    "DURATION_LIMIT_MS",
    "MANIFEST_NAME",
    "PRIORITY_LIMIT",
    "SOURCE_NAME",
    "TYPE_SUPPORT",
    "VERSION_LIMIT",
    "EffectBlueprint",
    "ParameterBlueprint",
    "TypeSupport",
    "build_package",
    "compile_blueprint",
    "default_for",
    "reserved_blueprint",
    "starting_blueprint",
]
