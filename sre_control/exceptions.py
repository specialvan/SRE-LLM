"""Control-domain exception taxonomy for SRE adapters."""

from __future__ import annotations


class ControlDomainError(Exception):
    """Base class for expected control-domain failures."""


class RecoverableControlError(ControlDomainError):
    """A failure where a validated fallback can safely complete the tick."""


class AdapterInputError(RecoverableControlError):
    """Invalid or missing adapter input with a known safe fallback."""
