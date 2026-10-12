class AnalyzerError(Exception):
    """Base class for expected CLI-facing errors."""


class ValidationError(AnalyzerError):
    """Raised when a review JSON cannot be safely normalized."""


class ConflictError(AnalyzerError):
    """Raised when an external game identifier conflicts with known data."""
