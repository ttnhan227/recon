from __future__ import annotations


class ReconError(Exception):
    """Base exception for Recon."""


class TargetUnreachableError(ReconError):
    """Raised when the target URL or OpenAPI spec cannot be reached."""


class SSRFSecurityError(ReconError):
    """Raised when a requested URL targets a blocked or restricted host/IP."""


class ConfigurationError(ReconError):
    """Raised when configuration or CLI parameters are invalid."""


class DiscoveryError(ReconError):
    """Raised when discovery of application assets or OpenAPI specs fails."""


class TestExecutionError(ReconError):
    """Raised when an unrecoverable error happens during test execution."""


class LLMProviderError(ReconError):
    """Raised when an LLM provider encounters an error or is unconfigured."""
