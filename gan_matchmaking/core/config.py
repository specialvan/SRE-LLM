"""Typed, validated configuration for the whole package.

We deliberately do **not** depend on pydantic so the library stays
single-file-importable with just numpy/scipy. Validation is done in
``__post_init__`` with explicit :class:`ConfigError` raising.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping, Optional

from .errors import ConfigError


# ---------------------------------------------------------------------------
# Per-module configuration blocks
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TrueSkillConfig:
    mu0: float = 25.0
    sigma0: float = 25.0 / 3.0
    beta: Optional[float] = None          # default = sigma0 / 2
    tau: Optional[float] = None           # default = sigma0 / 100
    draw_probability: float = 0.10

    def __post_init__(self) -> None:
        if self.sigma0 <= 0:
            raise ConfigError("sigma0 must be > 0", details={"sigma0": self.sigma0})
        if not 0.0 <= self.draw_probability < 1.0:
            raise ConfigError("draw_probability must be in [0, 1)",
                              details={"draw_probability": self.draw_probability})


@dataclass(frozen=True)
class DynamicKConfig:
    k_max: float = 32.0
    k_min: float = 4.0
    lam: float = 0.7
    theta: float = 5.0
    penalize_wins: bool = True

    def __post_init__(self) -> None:
        if self.k_max <= self.k_min:
            raise ConfigError("k_max must be > k_min",
                              details={"k_max": self.k_max, "k_min": self.k_min})
        if self.lam <= 0:
            raise ConfigError("lam must be > 0", details={"lam": self.lam})


@dataclass(frozen=True)
class HandicapConfig:
    max_penalty: float = 200.0
    tau: float = 3.0

    def __post_init__(self) -> None:
        if self.max_penalty < 0:
            raise ConfigError("max_penalty must be >= 0",
                              details={"max_penalty": self.max_penalty})
        if self.tau <= 0:
            raise ConfigError("tau must be > 0", details={"tau": self.tau})


@dataclass(frozen=True)
class EntropyConfig:
    min_entropy: float = 0.9  # bits; 0..1 for binary outcomes

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_entropy <= 1.0:
            raise ConfigError("min_entropy must be in [0, 1]",
                              details={"min_entropy": self.min_entropy})


@dataclass(frozen=True)
class EOMMConfig:
    epsilon: float = 0.0
    lr: float = 0.1
    iters: int = 200
    l2: float = 1e-3

    def __post_init__(self) -> None:
        if not 0.0 <= self.epsilon <= 1.0:
            raise ConfigError("epsilon must be in [0, 1]",
                              details={"epsilon": self.epsilon})
        if self.iters <= 0:
            raise ConfigError("iters must be > 0", details={"iters": self.iters})


@dataclass(frozen=True)
class SurvivalConfig:
    horizon_hours: float = 24.0
    warn_threshold: float = 0.3
    alarm_threshold: float = 0.6

    def __post_init__(self) -> None:
        if self.horizon_hours <= 0:
            raise ConfigError("horizon_hours must be > 0",
                              details={"horizon_hours": self.horizon_hours})
        if not 0.0 <= self.warn_threshold <= self.alarm_threshold <= 1.0:
            raise ConfigError(
                "thresholds must satisfy 0 <= warn <= alarm <= 1",
                details={"warn": self.warn_threshold,
                         "alarm": self.alarm_threshold},
            )


@dataclass(frozen=True)
class GNNConfig:
    hidden_dim: int = 8
    layers: int = 2
    seed: int = 42

    def __post_init__(self) -> None:
        if self.hidden_dim <= 0 or self.layers <= 0:
            raise ConfigError("hidden_dim and layers must be > 0",
                              details={"hidden_dim": self.hidden_dim,
                                       "layers": self.layers})


@dataclass(frozen=True)
class ObservabilityConfig:
    log_level: str = "INFO"
    log_sink: str = "stderr"   # "stderr" | "stdout" | file path
    emit_metrics: bool = True
    service_name: str = "gan-matchmaking"

    def __post_init__(self) -> None:
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("invalid log_level", details={"log_level": self.log_level})


# ---------------------------------------------------------------------------
# Top-level application config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AppConfig:
    trueskill: TrueSkillConfig = field(default_factory=TrueSkillConfig)
    dynamic_k: DynamicKConfig = field(default_factory=DynamicKConfig)
    handicap: HandicapConfig = field(default_factory=HandicapConfig)
    entropy: EntropyConfig = field(default_factory=EntropyConfig)
    eomm: EOMMConfig = field(default_factory=EOMMConfig)
    survival: SurvivalConfig = field(default_factory=SurvivalConfig)
    gnn: GNNConfig = field(default_factory=GNNConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------
def _from_mapping(cls, data: Mapping[str, Any]):
    """Build dataclass ``cls`` from a mapping, raising ConfigError on stray keys."""
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    extra = set(data) - known
    if extra:
        raise ConfigError(
            f"unknown keys for {cls.__name__}: {sorted(extra)}",
            details={"extra_keys": sorted(extra)},
        )
    return cls(**{k: v for k, v in data.items() if k in known})


def load_config(path_or_mapping: Any | None = None) -> AppConfig:
    """Load an :class:`AppConfig` from a JSON file path, a dict, or defaults.

    Parameters
    ----------
    path_or_mapping :
        - ``None`` → defaults.
        - ``str`` / ``Path`` → JSON file path.
        - ``Mapping`` → parsed config in memory.
    """
    if path_or_mapping is None:
        return AppConfig()

    if isinstance(path_or_mapping, (str, os.PathLike)):
        path = Path(path_or_mapping)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"config file not found: {path}",
                              details={"path": str(path)}) from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"invalid JSON in {path}: {exc.msg}",
                              details={"path": str(path), "line": exc.lineno}) from exc
    elif isinstance(path_or_mapping, Mapping):
        raw = dict(path_or_mapping)
    else:
        raise ConfigError("load_config argument must be None, path, or mapping",
                          details={"type": type(path_or_mapping).__name__})

    subs = {}
    mapping = {
        "trueskill": TrueSkillConfig,
        "dynamic_k": DynamicKConfig,
        "handicap": HandicapConfig,
        "entropy": EntropyConfig,
        "eomm": EOMMConfig,
        "survival": SurvivalConfig,
        "gnn": GNNConfig,
        "observability": ObservabilityConfig,
    }
    for key, cls in mapping.items():
        if key in raw and raw[key] is not None:
            subs[key] = _from_mapping(cls, raw[key])
    seed = int(raw.get("seed", 0))
    return AppConfig(seed=seed, **subs)
