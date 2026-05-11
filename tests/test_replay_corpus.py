"""Golden replay corpus for SRE decisions."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from gan_matchmaking.cli import _ctx_from_dict
from gan_matchmaking.core import MetricsRegistry, load_config
from gan_matchmaking.eomm import RetentionModel
from gan_matchmaking.sre import SelfIterationPipeline
from gan_matchmaking.sre.artifacts import (
    build_metadata,
    save_cox_artifact,
    save_retention_artifact,
)
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
            trained_at=1.0,
            build_id="replay-fixture",
        )
        save_cox_artifact(directory, model, metadata)


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_golden_replay_corpus(fixture_path, tmp_path):
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    config_raw = dict(raw.get("config", {}))
    if raw.get("artifacts"):
        artifact_dir = tmp_path / raw["name"] / "artifacts"
        _write_artifacts(raw["artifacts"], artifact_dir, raw["name"])
        config_raw["artifacts"] = {"directory": str(artifact_dir)}

    cfg = load_config(config_raw)
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())
    decision = pipeline.decide(_ctx_from_dict(raw["context"]))
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

    if "eomm_source" in expected:
        assert payload["trace"]["stages"]["eomm"]["source"] == expected["eomm_source"]
