"""Public widgets and adapters for lefx_configurator_widget."""

from .call_editor import LedCallEditor
from .catalogue import CatalogueEntry, CatalogueProvider, LefxCatalogueAdapter, MemoryCatalogue
from .catalogue_widget import EffectCatalogueWidget
from .configurator import LedFeedbackConfigurator, LedFeedbackDialog
from .mapping import Diagnostic, EventSpec, FeedbackDocument, HostCapabilities, LedVerb, validate_call
from .mapping_editor import FeedbackMappingEditor
from .parameters import EffectEditor, ParameterForm
from .preview import MemoryFrameSink, PreviewAdapter, PreviewPanel, PreviewRequest, PreviewSession
from .widgets import (
    AngleEditor, ColorListEditor, ColorRangeEditor, GradientEditor,
    LedRingPreview, RangeEditor, RepeatableContainer,
)

__all__ = [
    "AngleEditor", "CatalogueEntry", "CatalogueProvider", "ColorListEditor", "ColorRangeEditor",
    "Diagnostic", "EffectCatalogueWidget", "EffectEditor", "EventSpec", "FeedbackDocument",
    "FeedbackMappingEditor", "GradientEditor", "HostCapabilities", "LedCallEditor",
    "LedFeedbackConfigurator", "LedFeedbackDialog", "LedRingPreview", "LedVerb",
    "LefxCatalogueAdapter", "MemoryCatalogue", "MemoryFrameSink", "ParameterForm",
    "PreviewAdapter", "PreviewPanel", "PreviewRequest", "PreviewSession", "RangeEditor",
    "RepeatableContainer", "validate_call",
]
