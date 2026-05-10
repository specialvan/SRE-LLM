"""Protocols that the SRE / domain layer speaks against.

Using :class:`typing.Protocol` means the domain layer can swap in alternative
implementations (mock / production / A-B) without forcing every class into
inheritance. Each protocol is narrow on purpose.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Rater(Protocol):
    """Anything that can update and return a scalar skill / reliability score."""

    def rate(self, subject_id: str) -> float: ...
    def observe(self, winner_id: str, loser_id: str, score_winner: float = 1.0) -> None: ...


@runtime_checkable
class Matcher(Protocol):
    """Pick a single candidate from a list given a context vector."""

    def best(self, context: Sequence[float], candidates: Iterable[Any]) -> Any: ...


@runtime_checkable
class RiskMonitor(Protocol):
    """Return a risk probability in [0, 1] and a coarse level string."""

    def predict(self, features: Sequence[float]) -> float: ...

    def level(self, p: float) -> str: ...


@runtime_checkable
class SignalExtractor(Protocol):
    """Turn a raw observation vector into a compressed latent vector."""

    def fit(self, X) -> "SignalExtractor": ...
    def transform(self, X): ...
