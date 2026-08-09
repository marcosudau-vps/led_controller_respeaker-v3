"""What is loaded, and how a name turns into it.

Definition ids and preset ids share one public namespace, so a short name always
means one thing. Qualified forms exist for diagnostics and for choosing between
sources deliberately; they are exact aliases, never fuzzy matches.

Nothing is ever run on a guess. A miss suggests near matches, and an ambiguity
is refused outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from lefx.sdk import (
    BaseEffect,
    DefinitionBase,
    DefinitionType,
    ParameterValidationError,
    resolve_configuration,
)

from .errors import (
    AmbiguousTargetError,
    RegistrationError,
    TargetNotFoundError,
    WrongTargetTypeError,
)


@dataclass(slots=True, frozen=True)
class Preset:
    """A named starting point for one definition's configuration.

    A preset is a convenience, never a restriction: a caller may take it as is
    or override any value the schema allows. It cannot change type, placement or
    lifecycle, and it carries no runtime inputs.
    """

    preset_id: str
    source_id: str
    effect_id: str
    params: Mapping[str, Any] = field(default_factory=dict)
    title: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()

    @property
    def qualified_id(self) -> str:
        return f"{self.source_id}::{self.preset_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "qualified_id": self.qualified_id,
            "source_id": self.source_id,
            "effect_id": self.effect_id,
            "title": self.title or self.preset_id,
            "description": self.description,
            "tags": list(self.tags),
            "config": dict(self.params),
        }


@dataclass(slots=True, frozen=True)
class RegisteredEffect:
    """One definition as the registry knows it, together with its origin."""

    definition: DefinitionBase
    effect_class: type[BaseEffect]
    source_id: str
    package_id: str | None = None
    package_version: int | None = None

    @property
    def effect_id(self) -> str:
        return self.definition.id

    @property
    def qualified_id(self) -> str:
        return f"{self.source_id}::{self.definition.id}"


@dataclass(slots=True, frozen=True)
class ResolvedTarget:
    """What a caller-supplied name turned out to mean."""

    effect: RegisteredEffect
    preset: Preset | None = None

    @property
    def kind(self) -> str:
        return "preset" if self.preset is not None else "definition"

    @property
    def target_id(self) -> str:
        return self.preset.preset_id if self.preset is not None else self.effect.effect_id


class EffectRegistry:
    """Holds every loaded definition and preset and resolves names against them."""

    def __init__(self) -> None:
        self._effects: dict[str, RegisteredEffect] = {}
        self._presets: dict[str, Preset] = {}
        self._aliases: dict[str, str] = {}
        self._preset_aliases: dict[str, str] = {}

    # -- registration -------------------------------------------------------

    def register_effect(
        self,
        effect_class: type[BaseEffect],
        *,
        source_id: str,
        package_id: str | None = None,
        package_version: int | None = None,
    ) -> RegisteredEffect:
        definition = _definition_of(effect_class)
        if definition.id in self._effects:
            existing = self._effects[definition.id]
            raise RegistrationError(
                f"Definition id {definition.id!r} is already registered from source "
                f"{existing.source_id!r}; ids are globally unique"
            )
        if definition.id in self._presets:
            raise RegistrationError(
                f"Definition id {definition.id!r} collides with a preset of the same name"
            )

        registered = RegisteredEffect(
            definition=definition,
            effect_class=effect_class,
            source_id=source_id,
            package_id=package_id,
            package_version=package_version,
        )
        self._effects[definition.id] = registered
        self._aliases[registered.qualified_id] = definition.id
        self._aliases[f"{source_id}.{definition.id}"] = definition.id
        if package_id:
            self._aliases[package_id] = definition.id
        return registered

    def register_preset(self, preset: Preset) -> Preset:
        if preset.preset_id in self._presets:
            existing = self._presets[preset.preset_id]
            raise RegistrationError(
                f"Preset id {preset.preset_id!r} is already registered from source "
                f"{existing.source_id!r}; ids are globally unique"
            )
        if preset.preset_id in self._effects:
            raise RegistrationError(
                f"Preset id {preset.preset_id!r} collides with a definition of the same name"
            )
        effect = self._effects.get(preset.effect_id)
        if effect is None:
            raise RegistrationError(
                f"Preset {preset.preset_id!r} references unknown definition "
                f"{preset.effect_id!r}"
            )
        try:
            # Presets are configuration and nothing else. Validating on
            # registration means a broken one is found when it is loaded, not
            # when somebody happens to activate it.
            resolve_configuration(effect.definition, preset=preset.params)
        except ParameterValidationError as exc:
            raise RegistrationError(
                f"Preset {preset.preset_id!r} does not satisfy the schema of "
                f"{preset.effect_id!r}: {exc}"
            ) from exc

        self._presets[preset.preset_id] = preset
        self._preset_aliases[preset.qualified_id] = preset.preset_id
        self._preset_aliases[f"{preset.source_id}.{preset.preset_id}"] = preset.preset_id
        return preset

    def remove_source(self, source_id: str) -> None:
        """Drop everything a source contributed, in one step."""
        for effect_id in [
            key for key, value in self._effects.items() if value.source_id == source_id
        ]:
            del self._effects[effect_id]
        for preset_id in [
            key for key, value in self._presets.items() if value.source_id == source_id
        ]:
            del self._presets[preset_id]
        self._rebuild_aliases()

    def clear(self) -> None:
        self._effects.clear()
        self._presets.clear()
        self._aliases.clear()
        self._preset_aliases.clear()

    def _rebuild_aliases(self) -> None:
        self._aliases.clear()
        self._preset_aliases.clear()
        for effect in self._effects.values():
            self._aliases[effect.qualified_id] = effect.effect_id
            self._aliases[f"{effect.source_id}.{effect.effect_id}"] = effect.effect_id
            if effect.package_id:
                self._aliases[effect.package_id] = effect.effect_id
        for preset in self._presets.values():
            self._preset_aliases[preset.qualified_id] = preset.preset_id
            self._preset_aliases[f"{preset.source_id}.{preset.preset_id}"] = preset.preset_id

    # -- lookup -------------------------------------------------------------

    def get(self, effect_id: str) -> RegisteredEffect:
        effect = self._effects.get(effect_id)
        if effect is None:
            raise TargetNotFoundError(effect_id, suggestions=self._suggest(effect_id))
        return effect

    def get_preset(self, preset_id: str) -> Preset:
        preset = self._presets.get(preset_id)
        if preset is None:
            raise TargetNotFoundError(preset_id, suggestions=self._suggest(preset_id))
        return preset

    def resolve(
        self, target: str, *, expected_type: DefinitionType | None = None
    ) -> ResolvedTarget:
        """Turn a caller-supplied name into a definition and optional preset."""
        name = str(target or "").strip()
        if not name:
            raise TargetNotFoundError(target)

        matches: list[ResolvedTarget] = []
        registered = self._effects.get(name)
        if registered is None:
            aliased = self._aliases.get(name)
            registered = None if aliased is None else self._effects.get(aliased)
        if registered is not None:
            matches.append(ResolvedTarget(effect=registered))

        preset = self._presets.get(name)
        if preset is None:
            aliased = self._preset_aliases.get(name)
            preset = None if aliased is None else self._presets[aliased]
        if preset is not None:
            matches.append(
                ResolvedTarget(effect=self._effects[preset.effect_id], preset=preset)
            )

        if not matches:
            raise TargetNotFoundError(name, suggestions=self._suggest(name))
        if len(matches) > 1:
            raise AmbiguousTargetError(
                name, tuple(sorted(match.effect.qualified_id for match in matches))
            )

        resolved = matches[0]
        if expected_type is not None:
            actual = resolved.effect.definition.definition_type
            if actual is not expected_type:
                raise _wrong_type(name, actual, expected_type)
        return resolved

    def _suggest(self, name: str) -> tuple[str, ...]:
        candidates = sorted(set(self._effects) | set(self._presets))
        return tuple(get_close_matches(name, candidates, n=3, cutoff=0.55))

    # -- listings -----------------------------------------------------------

    def list_effects(
        self, *, definition_type: DefinitionType | None = None, source_id: str | None = None
    ) -> list[RegisteredEffect]:
        items = [
            effect
            for effect in self._effects.values()
            if (definition_type is None or effect.definition.definition_type is definition_type)
            and (source_id is None or effect.source_id == source_id)
        ]
        return sorted(items, key=lambda effect: effect.effect_id)

    def list_presets(
        self, *, definition_type: DefinitionType | None = None, effect_id: str | None = None
    ) -> list[Preset]:
        items = []
        for preset in self._presets.values():
            if effect_id is not None and preset.effect_id != effect_id:
                continue
            if definition_type is not None:
                effect = self._effects.get(preset.effect_id)
                if effect is None or effect.definition.definition_type is not definition_type:
                    continue
            items.append(preset)
        return sorted(items, key=lambda preset: preset.preset_id)

    def source_ids(self) -> list[str]:
        return sorted({effect.source_id for effect in self._effects.values()})

    @property
    def effects(self) -> Mapping[str, RegisteredEffect]:
        return MappingProxyType(self._effects)

    def __len__(self) -> int:
        return len(self._effects)


def _definition_of(effect_class: type[BaseEffect]) -> DefinitionBase:
    definition = getattr(effect_class, "definition", None)
    if not isinstance(definition, DefinitionBase):
        raise RegistrationError(
            f"{effect_class.__name__} does not declare a LEFX V3 definition"
        )
    if not callable(getattr(effect_class, "render", None)):
        raise RegistrationError(f"{effect_class.__name__} does not implement render()")
    return definition


def _wrong_type(
    name: str, actual: DefinitionType, expected: DefinitionType
) -> WrongTargetTypeError:
    verbs = {
        DefinitionType.STATE: "set state",
        DefinitionType.OVERLAY: "set overlay",
        DefinitionType.EVENT: "emit event",
    }
    return WrongTargetTypeError(
        f"{name!r} is a {actual.value}, not a {expected.value}. "
        f"Use '{verbs[actual]}' for it."
    )


def build_registry(
    effect_classes: Iterable[type[BaseEffect]] = (), *, source_id: str = "builtin"
) -> EffectRegistry:
    """Convenience for tests and embedders: a registry from plain classes."""
    registry = EffectRegistry()
    for effect_class in effect_classes:
        registry.register_effect(effect_class, source_id=source_id)
    return registry


__all__ = [
    "EffectRegistry",
    "Preset",
    "RegisteredEffect",
    "ResolvedTarget",
    "build_registry",
]
