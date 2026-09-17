class MlsMaquetadorError(Exception):
    """Base exception for expected application errors."""


class DocumentNotFoundError(MlsMaquetadorError):
    """Raised when a required document cannot be found in a workspace."""


class ZipValidationError(MlsMaquetadorError):
    """Raised when an uploaded ZIP is unsafe or unsupported."""


class MetadataExtractionError(MlsMaquetadorError):
    """Raised when required article metadata cannot be extracted."""


class AmbiguousMetadataError(MetadataExtractionError):
    """Raised when metadata is present but cannot be trusted automatically."""


class AutomationError(MlsMaquetadorError):
    """Raised when the MLS external maquetador cannot be automated."""


class HtmlValidationError(MlsMaquetadorError):
    """Raised when generated HTML violates delivery invariants."""


class EpubValidationError(MlsMaquetadorError):
    """Raised when generated EPUB violates delivery invariants."""
