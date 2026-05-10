"""Tests for :mod:`gan_matchmaking.core.config`."""
from __future__ import annotations

import json

import pytest

from gan_matchmaking.core import ConfigError, load_config
from gan_matchmaking.core.config import (
    AppConfig,
    DynamicKConfig,
    HandicapConfig,
    SurvivalConfig,
    TrueSkillConfig,
)


def test_defaults_are_valid():
    cfg = AppConfig()
    assert cfg.trueskill.sigma0 > 0
    assert cfg.survival.warn_threshold <= cfg.survival.alarm_threshold


def test_load_from_mapping():
    cfg = load_config({"dynamic_k": {"k_max": 40.0, "k_min": 2.0}, "seed": 7})
    assert cfg.dynamic_k.k_max == 40.0
    assert cfg.dynamic_k.k_min == 2.0
    assert cfg.seed == 7


def test_load_from_json_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"handicap": {"max_penalty": 100.0, "tau": 2.0}}))
    cfg = load_config(path)
    assert cfg.handicap.max_penalty == 100.0


def test_invalid_trueskill_raises():
    with pytest.raises(ConfigError):
        TrueSkillConfig(sigma0=-1.0)


def test_invalid_dynamic_k():
    with pytest.raises(ConfigError):
        DynamicKConfig(k_max=10, k_min=20)


def test_invalid_handicap():
    with pytest.raises(ConfigError):
        HandicapConfig(max_penalty=-5)


def test_invalid_survival_thresholds():
    with pytest.raises(ConfigError):
        SurvivalConfig(warn_threshold=0.9, alarm_threshold=0.2)


def test_unknown_key_rejected():
    with pytest.raises(ConfigError):
        load_config({"dynamic_k": {"bogus": 1}})


def test_config_is_frozen():
    cfg = AppConfig()
    with pytest.raises(Exception):
        cfg.trueskill.mu0 = 42  # type: ignore[misc]
