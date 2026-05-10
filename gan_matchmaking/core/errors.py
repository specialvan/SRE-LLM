"""Typed exception hierarchy.

Design principles
-----------------

1. Every failure path raises a subclass of :class:`GanError`. Callers can
   ``except GanError`` at the process boundary without swallowing unrelated
   exceptions.
2. Errors carry a machine-readable ``code`` plus an optional ``details`` dict.
   The structured logger re-emits these on ``log.exception``.
3. No exception message contains PII or secrets by construction; call-sites
   put such data into ``details`` only when the configured log sink redacts it.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


class GanError(Exception):
    """Root exception for everything raised by this package."""

    code: str = "gan.error"

    def __init__(self, message: str = "", *, details: Optional[Mapping[str, Any]] = None):
        super().__init__(message or self.__class__.__name__)
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class ConfigError(GanError):
    """Raised when configuration is invalid or internally inconsistent."""

    code = "gan.config.invalid"


class DataError(GanError):
    """Raised when inputs violate the module's data contract.

    Examples: empty team, NaN in feature vector, mismatched matrix shapes.
    """

    code = "gan.data.invalid"


class NumericError(GanError):
    """Raised when an underlying numerical routine fails or is unstable.

    Examples: LP infeasibility, singular covariance, Newton divergence.
    """

    code = "gan.numeric.failure"


class PolicyViolationError(GanError):
    """Raised by the SRE layer when a decision would violate a hard SRE policy.

    This is a *recoverable* error: the caller is expected to fall back to a
    safer policy (HOLD, ROLLBACK). Never swallow silently.
    """

    code = "gan.policy.violation"


class UnsafeDecisionError(GanError):
    """Raised by the pipeline when no safe decision exists.

    Distinct from ``PolicyViolationError`` in that this is terminal — the
    caller must escalate (paging, manual intervention). This is the SRE
    equivalent of the auto-decide project's "dead zone".
    """

    code = "gan.decision.unsafe"
