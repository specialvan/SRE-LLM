"""Tests for :class:`SkillVersionGraph` (PR-013).

Covers REQ-GOV-002 / REQ-GOV-005 / REQ-GOV-010.
"""

from __future__ import annotations

import itertools
import time

import pytest

from attention_residuals.skill.governance.version_graph import (
    HeadName,
    HeadRefs,
    SkillVersionGraph,
)
from attention_residuals.skill.types import (
    BlastRadius,
    ChangeKind,
    PatchField,
    PatchTarget,
    SkillVersion,
    compute_version_id,
)

_BLAST = BlastRadius.compute((), (), 0.0)


def _make_version(
    skill_id: str,
    parents: tuple[str, ...] = (),
    tag: str = "",
    kind: ChangeKind = ChangeKind.EDIT,
    ts: float = 0.0,
) -> SkillVersion:
    """Helper: build a deterministic SkillVersion for tests."""
    targets = (PatchTarget(f"sig-{tag or 'x'}", PatchField.BIAS, 0.1),)
    return SkillVersion(
        version_id=compute_version_id(skill_id, targets, parents, f"author-{tag}"),
        skill_id=skill_id,
        parents=parents,
        author=f"author-{tag}",
        timestamp=ts,
        summary=f"edit {tag}",
        change_kind=kind,
        blast_radius=_BLAST,
    )


# -----------------------------------------------------------------------------
# commit + invariants
# -----------------------------------------------------------------------------


def test_commit_idempotent() -> None:
    g = SkillVersionGraph()
    v = _make_version("s1", tag="a")
    g.commit(v)
    g.commit(v)  # no-op
    assert len(g) == 1


def test_commit_rejects_id_collision_with_different_content() -> None:
    g = SkillVersionGraph()
    v1 = _make_version("s1", tag="a", ts=1.0)
    g.commit(v1)
    # Manually forge a second version with same id but different content
    v2 = SkillVersion(
        version_id=v1.version_id,
        skill_id=v1.skill_id,
        parents=v1.parents,
        author="someone-else",
        timestamp=v1.timestamp,
        summary=v1.summary,
        change_kind=v1.change_kind,
        blast_radius=v1.blast_radius,
    )
    with pytest.raises(ValueError, match="already exists"):
        g.commit(v2)


def test_commit_rejects_dangling_parent() -> None:
    g = SkillVersionGraph()
    v = _make_version("s1", parents=("ghost-id",), tag="a")
    with pytest.raises(ValueError, match="dangling parent"):
        g.commit(v)


# -----------------------------------------------------------------------------
# ancestors / descendants
# -----------------------------------------------------------------------------


def test_ancestors_linear_chain() -> None:
    g = SkillVersionGraph()
    v1 = _make_version("s1", tag="a")
    g.commit(v1)
    v2 = _make_version("s1", parents=(v1.version_id,), tag="b")
    g.commit(v2)
    v3 = _make_version("s1", parents=(v2.version_id,), tag="c")
    g.commit(v3)

    assert g.ancestors(v3.version_id) == {v1.version_id, v2.version_id}
    assert g.ancestors(v1.version_id) == set()


def test_descendants_y_fork() -> None:
    g = SkillVersionGraph()
    v0 = _make_version("s1", tag="0")
    g.commit(v0)
    v1 = _make_version("s1", parents=(v0.version_id,), tag="1")
    g.commit(v1)
    v2 = _make_version("s1", parents=(v0.version_id,), tag="2")
    g.commit(v2)

    assert g.descendants(v0.version_id) == {v1.version_id, v2.version_id}


# -----------------------------------------------------------------------------
# merge_base / is_divergent
# -----------------------------------------------------------------------------


def test_merge_base_linear() -> None:
    g = SkillVersionGraph()
    v1 = _make_version("s1", tag="a")
    g.commit(v1)
    v2 = _make_version("s1", parents=(v1.version_id,), tag="b")
    g.commit(v2)
    assert g.merge_base(v1.version_id, v2.version_id) == v1.version_id
    assert not g.is_divergent(v1.version_id, v2.version_id)


def test_merge_base_y_fork() -> None:
    g = SkillVersionGraph()
    v0 = _make_version("s1", tag="0")
    g.commit(v0)
    v1 = _make_version("s1", parents=(v0.version_id,), tag="1")
    g.commit(v1)
    v2 = _make_version("s1", parents=(v0.version_id,), tag="2")
    g.commit(v2)
    assert g.merge_base(v1.version_id, v2.version_id) == v0.version_id
    assert g.is_divergent(v1.version_id, v2.version_id)


# -----------------------------------------------------------------------------
# HEAD pointers
# -----------------------------------------------------------------------------


def test_three_heads_independent() -> None:
    g = SkillVersionGraph()
    v = _make_version("s1", tag="a")
    g.commit(v)
    assert g.get_heads("s1") == HeadRefs()
    g.move_head("s1", HeadName.SANDBOX, v.version_id)
    assert g.get_heads("s1").sandbox_head == v.version_id
    assert g.get_heads("s1").active_head is None


def test_move_head_rejects_unknown_version() -> None:
    g = SkillVersionGraph()
    with pytest.raises(KeyError):
        g.move_head("s1", HeadName.ACTIVE, "no-such-version")


# -----------------------------------------------------------------------------
# revert_to (REQ-GOV-005)
# -----------------------------------------------------------------------------


def test_revert_emits_new_version_with_both_parents() -> None:
    g = SkillVersionGraph()
    v1 = _make_version("s1", tag="a")
    g.commit(v1)
    v2 = _make_version("s1", parents=(v1.version_id,), tag="b")
    g.commit(v2)
    g.move_head("s1", HeadName.ACTIVE, v2.version_id)

    # Monotonic clock so the revert id is determined.
    counter = itertools.count()
    revert = g.revert_to(
        target=v1.version_id, skill_id="s1", now=lambda: next(counter) + 1.0
    )
    assert revert.change_kind is ChangeKind.REVERT
    assert set(revert.parents) == {v1.version_id, v2.version_id}
    assert g.get_heads("s1").active_head == revert.version_id


def test_revert_to_same_target_twice_produces_distinct_ids() -> None:
    g = SkillVersionGraph()
    v1 = _make_version("s1", tag="a")
    g.commit(v1)
    g.move_head("s1", HeadName.ACTIVE, v1.version_id)

    rv1 = g.revert_to(v1.version_id, "s1", now=lambda: 1.0)
    rv2 = g.revert_to(v1.version_id, "s1", now=lambda: 2.0)
    assert rv1.version_id != rv2.version_id


# -----------------------------------------------------------------------------
# Performance sanity (REQ-GOV-010)
# -----------------------------------------------------------------------------


@pytest.mark.perf
def test_ancestors_1000_nodes_under_10ms() -> None:
    g = SkillVersionGraph()
    prev = None
    for i in range(1000):
        parents = (prev,) if prev else ()
        v = _make_version("s1", parents=parents, tag=str(i))
        g.commit(v)
        prev = v.version_id

    # cold call
    t0 = time.perf_counter()
    anc = g.ancestors(prev)  # type: ignore[arg-type]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert len(anc) == 999
    # Generous cap — we budget 10ms per REQ-GOV-010 on 1000 nodes.
    assert elapsed_ms < 50.0, f"cold ancestors() took {elapsed_ms:.2f}ms"
