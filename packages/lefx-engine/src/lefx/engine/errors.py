"""Engine-level failures, separate from schema and payload errors.

Payload problems raise ``lefx.sdk.ParameterValidationError`` and never reach
here. These are the failures that belong to running the system: an id that
resolves to nothing or to several things, a command that contradicts the form
it addresses, a package that does not load, a frame that breaks its contract.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for every engine failure."""


class TargetNotFoundError(EngineError, KeyError):
    """No definition or preset matches the requested identifier."""

    def __init__(self, target: str, *, suggestions: tuple[str, ...] = ()) -> None:
        self.target = target
        self.suggestions = suggestions
        message = f"No effect or preset named {target!r}"
        if suggestions:
            message = f"{message}. Did you mean: {', '.join(suggestions)}?"
        super().__init__(message)

    def __str__(self) -> str:  # KeyError would otherwise quote the message
        return self.args[0]


class AmbiguousTargetError(EngineError, ValueError):
    """Several definitions match; nothing is run on a guess."""

    def __init__(self, target: str, matches: tuple[str, ...]) -> None:
        self.target = target
        self.matches = matches
        super().__init__(
            f"{target!r} is ambiguous between: {', '.join(matches)}. "
            "Qualify it with its source, for example 'source::id'."
        )


class CommandError(EngineError, ValueError):
    """A command contradicts the form it addresses."""


class WrongTargetTypeError(CommandError):
    """The identifier resolves, but to a different form than the verb expects."""


class ChannelNotFoundError(EngineError, KeyError):
    """No controlled overlay is running on the requested channel."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"No controlled overlay on channel {channel!r}")

    def __str__(self) -> str:
        return self.args[0]


class RenderError(EngineError, ValueError):
    """A definition returned a frame that does not satisfy its own contract."""


class RegistrationError(EngineError, ValueError):
    """A definition or package cannot be registered."""


class PackageError(EngineError, ValueError):
    """A package is malformed, altered, or disagrees with the class it carries."""


__all__ = [
    "AmbiguousTargetError",
    "ChannelNotFoundError",
    "CommandError",
    "EngineError",
    "PackageError",
    "RegistrationError",
    "RenderError",
    "TargetNotFoundError",
    "WrongTargetTypeError",
]
