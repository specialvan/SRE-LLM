"""Artifact metadata, stable version hashing, and disk serialisation helpers.

These utilities are shared by every artifact kind. Keeping them in a
small module lets retention / cox / bundle modules import only what they
need without circular dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Sequence as _Seq
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, tuple)):
        return list(value)
    return value


def _stable_version(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=_json_safe).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_id() -> str:
    return (
        os.environ.get("GIT_SHA")
        or os.environ.get("BUILD_ID")
        or os.environ.get("CI_COMMIT_SHA")
        or "unknown"
    )


def _config_hash(config: Mapping[str, Any]) -> str:
    return _stable_version({"config": dict(config)})


@dataclass(frozen=True)
class ArtifactMetadata:
    name: str
    version: str
    trained_at: float
    source_window: Mapping[str, Any]
    config_hash: str
    build_id: str
    fitted: bool = True
    fallback: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "trained_at": self.trained_at,
            "source_window": dict(self.source_window),
            "config_hash": self.config_hash,
            "build_id": self.build_id,
            "fitted": self.fitted,
            "fallback": self.fallback,
            "extra": dict(self.extra),
        }


def build_metadata(
    name: str,
    *,
    source_window: Mapping[str, Any],
    config: Mapping[str, Any],
    extra: Optional[Mapping[str, Any]] = None,
    trained_at: Optional[float] = None,
    build_id: Optional[str] = None,
    fitted: bool = True,
    fallback: bool = False,
) -> ArtifactMetadata:
    payload = {
        "name": name,
        "trained_at": trained_at if trained_at is not None else time.time(),
        "source_window": dict(source_window),
        "config_hash": _config_hash(config),
        "build_id": build_id or _build_id(),
        "fitted": fitted,
        "fallback": fallback,
        "extra": dict(extra or {}),
    }
    version = _stable_version(payload)
    return ArtifactMetadata(
        name=name,
        version=version,
        trained_at=float(payload["trained_at"]),
        source_window=dict(source_window),
        config_hash=payload["config_hash"],
        build_id=payload["build_id"],
        fitted=fitted,
        fallback=fallback,
        extra=dict(extra or {}),
    )


def write_metadata(path: Path, metadata: ArtifactMetadata) -> None:
    path.write_text(
        json.dumps(metadata.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_metadata(path: Path, *, default_name: str) -> ArtifactMetadata:
    if not path.exists():
        return ArtifactMetadata(
            name=default_name,
            version="unversioned",
            trained_at=0.0,
            source_window={},
            config_hash="unknown",
            build_id="unknown",
            fitted=True,
            fallback=False,
            extra={},
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactMetadata(
        name=str(raw.get("name", default_name)),
        version=str(raw.get("version", "unknown")),
        trained_at=float(raw.get("trained_at", 0.0)),
        source_window=dict(raw.get("source_window", {})),
        config_hash=str(raw.get("config_hash", "unknown")),
        build_id=str(raw.get("build_id", "unknown")),
        fitted=bool(raw.get("fitted", True)),
        fallback=bool(raw.get("fallback", False)),
        extra=dict(raw.get("extra", {})),
    )


def declared_feature_names(metadata: ArtifactMetadata) -> Optional[list[str]]:
    names = metadata.extra.get("feature_names")
    if names is None:
        return None
    if not isinstance(names, _Seq) or isinstance(names, (str, bytes)):
        return []
    return [str(name) for name in names]


def declared_feature_dim(metadata: ArtifactMetadata) -> Optional[int]:
    dim = metadata.extra.get("feature_dim")
    if dim is None:
        return None
    try:
        return int(dim)
    except (TypeError, ValueError):
        return -1
