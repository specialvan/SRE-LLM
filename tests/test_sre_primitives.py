"""Tests for the reusable SRE primitive catalog."""
from __future__ import annotations

import pytest

from gan_matchmaking.sre.primitives import (
    CONTROL_PRIMITIVES,
    list_control_primitives,
    primitive_by_mechanism,
)


EXPECTED_MECHANISMS = {
    "TrueSkill",
    "EOMM",
    "Dynamic K",
    "PCA",
    "GNN",
    "Handicap",
    "Entropy",
    "Cox Survival",
    "Minimax BP",
}


def test_control_primitive_catalog_covers_the_nine_mechanisms():
    mechanisms = {primitive.mechanism for primitive in CONTROL_PRIMITIVES}

    assert len(CONTROL_PRIMITIVES) == 9
    assert mechanisms == EXPECTED_MECHANISMS
    assert list_control_primitives() == CONTROL_PRIMITIVES


def test_control_primitives_have_engineering_contracts():
    valid_statuses = {"production", "mixed", "research"}
    capabilities = set()

    for primitive in CONTROL_PRIMITIVES:
        assert primitive.capability
        assert primitive.pattern
        assert primitive.runtime_stage
        assert primitive.code_refs
        assert primitive.inputs
        assert primitive.outputs
        assert primitive.production_status in valid_statuses
        assert primitive.compounding_use
        capabilities.add(primitive.capability)

    assert len(capabilities) == len(CONTROL_PRIMITIVES)


def test_lookup_primitive_by_mechanism():
    primitive = primitive_by_mechanism("cox survival")

    assert primitive.capability == "time_to_incident_forecaster"
    assert primitive.runtime_stage == "stage.risk"

    with pytest.raises(KeyError):
        primitive_by_mechanism("not-a-mechanism")
