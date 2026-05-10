"""Core infrastructure shared by every gan-matchmaking module.

Modules:

- :mod:`config`    — typed, validated configuration objects
- :mod:`errors`    — typed exception hierarchy
- :mod:`logging`   — JSONL structured logger factory
- :mod:`metrics`   — Prometheus-style in-process metrics registry
- :mod:`tracing`   — correlation-id + span context manager
- :mod:`random`    — deterministic RNG / seed management
- :mod:`protocols` — Protocols/ABCs the domain layer speaks against
"""

from .config import AppConfig, load_config
from .errors import (
    GanError,
    ConfigError,
    DataError,
    NumericError,
    PolicyViolationError,
    UnsafeDecisionError,
)
from .logging import JsonLineLogger, get_logger
from .metrics import Counter, Gauge, Histogram, MetricsRegistry, default_registry
from .tracing import Span, current_correlation_id, span, with_correlation_id
from .random import SeedManager
from .protocols import (
    Matcher,
    Rater,
    RiskMonitor,
    SignalExtractor,
)

__all__ = [
    # config
    "AppConfig", "load_config",
    # errors
    "GanError", "ConfigError", "DataError", "NumericError",
    "PolicyViolationError", "UnsafeDecisionError",
    # logging
    "JsonLineLogger", "get_logger",
    # metrics
    "Counter", "Gauge", "Histogram", "MetricsRegistry", "default_registry",
    # tracing
    "Span", "current_correlation_id", "span", "with_correlation_id",
    # random
    "SeedManager",
    # protocols
    "Matcher", "Rater", "RiskMonitor", "SignalExtractor",
]
