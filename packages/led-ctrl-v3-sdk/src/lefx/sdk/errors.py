"""Error types shared by value normalization, schema construction and validation.

Three kinds of failure are distinguished on purpose:

``SchemaError``
    The definition itself is wrong. Raised while a definition is being
    constructed, so a broken contract can never reach the registry.

``ValueNormalizationError``
    A single value could not be brought into canonical form. Carries a code and
    optional suggestions but no field path — the caller knows the field.

``ParameterValidationError``
    One or more fields of a command payload were rejected. Aggregates issues so
    a caller learns about every problem at once rather than one per round trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SchemaError(ValueError):
    """A definition or parameter declaration violates the LEFX V3 contract."""


class ValueNormalizationError(ValueError):
    """A single value could not be normalized into its canonical form."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        value: Any,
        suggestions: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.value = value
        self.suggestions = suggestions

    def to_dict(self, *, field: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "value": self.value,
            "message": str(self),
        }
        if field is not None:
            payload["field"] = field
        if self.suggestions:
            payload["suggestions"] = list(self.suggestions)
        return payload


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    """One rejected field, with everything a caller needs to correct it."""

    code: str
    field: str
    message: str
    value: Any = None
    suggestions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "value": self.value,
        }
        if self.suggestions:
            payload["suggestions"] = list(self.suggestions)
        return payload


class ParameterValidationError(ValueError):
    """A command payload was rejected. Reports every issue, not just the first."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in issues))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": "validation_failed",
            "issues": [issue.to_dict() for issue in self.issues],
        }
