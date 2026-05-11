"""Golden replay corpus for SRE decisions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from gan_matchmaking.core import MetricsRegistry, load_config
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.sre import ReleaseContext, SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    EOMM_FEATURE_NAMES,
    build_metadata,
    save_cox_artifact,
    save_retention_artifact,
)
from gan_matchmaking.sre.features import RISK_FEATURE_NAMES
from gan_matchmaking.survival import CoxModel


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "replay"


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.json"))


def _write_artifacts(spec: dict, directory: Path, fixture_name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if "retention" in spec:
        raw = spec["retention"]
        model = RetentionModel(
            weights=np.asarray(raw["weights"], dtype=float),
            bias=float(raw["bias"]),
        )
        metadata = build_metadata(
            "retention",
            source_window={"fixture": fixture_name},
            config={"fixture": fixture_name, "model": "retention"},
            extra={"feature_dim": len(EOMM_FEATURE_NAMES),
                   "feature_names": list(EOMM_FEATURE_NAMES)},
            trained_at=1.0,
            build_id="replay-fixture",
        )
        save_retention_artifact(directory, model, metadata)
    if "cox" in spec:
        raw = spec["cox"]
        model = CoxModel(
            beta=np.asarray(raw["beta"], dtype=float),
            _baseline_t=np.asarray(raw["baseline_t"], dtype=float),
            _baseline_H=np.asarray(raw["baseline_H"], dtype=float),
        )
        metadata = build_metadata(
            "cox",
            source_window={"fixture": fixture_name},
            config={"fixture": fixture_name, "model": "cox"},
            extra={"feature_dim": len(RISK_FEATURE_NAMES),
                   "feature_names": list(RISK_FEATURE_NAMES)},
            trained_at=1.0,
            build_id="replay-fixture",
        )
        save_cox_artifact(directory, model, metadata)


def _get_path(payload: dict, path: str):
    current = payload
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_golden_replay_corpus(fixture_path, tmp_path):
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    config_raw = dict(raw.get("config", {}))
    if raw.get("artifacts"):
        artifact_dir = tmp_path / raw["name"] / "artifacts"
        _write_artifacts(raw["artifacts"], artifact_dir, raw["name"])
        config_raw["artifacts"] = {"directory": str(artifact_dir)}
    elif raw.get("artifact_bundle"):
        artifact_bundle = raw["artifact_bundle"]
        artifact_path = Path(artifact_bundle["path"])
        if not artifact_path.is_absolute():
            artifact_path = fixture_path.parent / artifact_path
        assert artifact_path.exists()
        config_raw["artifacts"] = {
            **dict(config_raw.get("artifacts", {})),
            "directory": str(artifact_path),
        }

    cfg = load_config(config_raw)
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())
    decision = pipeline.decide(ReleaseContext.from_dict(raw["context"]))
    payload = decision.to_dict()
    expected = raw["expected"]

    assert payload["kind"] == expected["kind"]
    assert payload["chosen_id"] == expected["chosen_id"]
    assert payload["risk_level"] == expected["risk_level"]
    if expected["artifact_version"] == "bootstrap":
        assert payload["artifact_version"] == "bootstrap"
    else:
        assert payload["artifact_version"] != "bootstrap"
        assert payload["trace"]["artifacts"]["fitted"] is True
    if raw.get("requires_artifact_version"):
        assert payload["artifact_version"] == raw["requires_artifact_version"]

    if "eomm_source" in expected:
        assert payload["trace"]["stages"]["eomm"]["source"] == expected["eomm_source"]

    for needle in expected.get("rationale_contains", []):
        assert any(needle in item for item in payload["rationale"])

    for path, value in expected.get("trace_values", {}).items():
        assert _get_path(payload["trace"], path) == value
