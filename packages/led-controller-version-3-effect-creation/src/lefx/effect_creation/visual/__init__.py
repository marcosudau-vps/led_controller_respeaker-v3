"""Headless visual authoring. No GUI or Studio installation at effect runtime."""

from .blocks import BLOCKS, DesignError
from .editor import Editor
from .model import new_document, validate

__all__ = ["BLOCKS", "DesignError", "Editor", "new_document", "validate"]
