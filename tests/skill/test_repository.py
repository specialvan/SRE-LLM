"""Tests for :class:`SkillRepository` (PR-012).

Covers REQ-DAT-006, REQ-GOV-002..004, REQ-GOV-011.
"""

from __future__ import annotations

import threading

import pytest

from attention_residuals.skill.governance.repository import (
    ConservativeRejection,
    SkillListener,
    SkillRepository,
)
from attention_residuals.skill.governance.version_graph import (
    HeadName,
    SkillVersionGraph,
)
from attention_residuals.skill.types import (
    BlastRadius,
    ChangeKind,
    PatchField,
    PatchTarget,
    SkillRecord,
    SkillVersion,
    Stage,
    compute_version_id,
)

_BLAST = BlastRadius.compute((), (), 0.0)


def _make_record_and_version(
    skill_id: str = "s1",
    tenant: str = "default",
    stage: Stage = Stage.SANDBOX,
    delta: float = 0.1,
    author: str = "alice",
    parents: tuple[str, ...] = (),
) -> tuple[SkillRecord, SkillVersion]:
    targets = (PatchTarget("sig-a", PatchField.BIAS, delta),)
    version_id = compute_version_id(skill_id, targets, parents, author)
    version = SkillVersion(
        version_id=version_id,
        skill_id=skill_id,
        parents=parents,
        author=author,
        timestamp=0.0,
        summary="test",
        change_kind=ChangeKind.CREATE,
        blast_radius=_BLAST,
    )
    rec = SkillRecord(
        skill_id=skill_id,
        version=version_id,
        tenant=tenant,
        stage=stage,
        meta={"name": skill_id},
        targets=targets,
    )
    return rec, version


# -----------------------------------------------------------------------------
# Basic CRUD
# -----------------------------------------------------------------------------


def test_put_and_get_head() -> None:
    repo = SkillRepository()
    rec, ver = _make_record_and_version(stage=Stage.SANDBOX)
    repo.put(rec, version=ver)

    # SANDBOX head is set; ACTIVE head is not.
    heads = repo.graph.get_heads("s1")
    assert heads.sandbox_head == rec.version
    assert heads.active_head is None

    # get by explicit version works
    assert repo.get("s1", version=rec.version) == rec

    # "HEAD" (active) raises because no active_head yet
    with pytest.raises(KeyError):
        repo.get("s1")


def test_explicit_graph_is_used_not_replaced() -> None:
    """Regression guard: SkillVersionGraph has __len__ so ``g or default``
    silently drops explicit graphs. We must pass it through verbatim.
    """
    graph = SkillVersionGraph()
    repo = SkillRepository(graph=graph)
    assert repo.graph is graph
    rec, ver = _make_record_and_version()
    repo.put(rec, version=ver)
    # The put must have written to *this* graph, not a replacement.
    assert graph.get_heads("s1").sandbox_head == rec.version


def test_put_is_idempotent_on_same_record() -> None:
    repo = SkillRepository()
    rec, ver = _make_record_and_version()
    repo.put(rec, version=ver)
    repo.put(rec, version=ver)  # second call no-op
    assert len(repo.list()) == 1


def test_req_dat_006_unique_key() -> None:
    repo = SkillRepository()
    rec_a, ver_a = _make_record_and_version(tenant="east")
    rec_b, ver_b = _make_record_and_version(tenant="west")
    repo.put(rec_a, version=ver_a)
    repo.put(rec_b, version=ver_b)
    assert repo.get("s1", version=rec_a.version, tenant="east") == rec_a
    assert repo.get("s1", version=rec_b.version, tenant="west") == rec_b


def test_list_filters_by_tenant_stage_tag() -> None:
    repo = SkillRepository()
    rec1, ver1 = _make_record_and_version(skill_id="a", stage=Stage.SANDBOX)
    rec2, ver2 = _make_record_and_version(skill_id="b", stage=Stage.SANDBOX)
    repo.put(rec1, version=ver1)
    repo.put(rec2, version=ver2)
    assert {r.skill_id for r in repo.list(stage=Stage.SANDBOX)} == {"a", "b"}
    assert repo.list(stage=Stage.ACTIVE) == []


# -----------------------------------------------------------------------------
# Promote / retire
# -----------------------------------------------------------------------------


def test_promote_sandbox_to_quarantine_to_active() -> None:
    repo = SkillRepository()
    rec, ver = _make_record_and_version(stage=Stage.SANDBOX)
    repo.put(rec, version=ver)
    assert repo.graph.get_heads("s1").sandbox_head == rec.version

    q = repo.promote("s1", to_stage=Stage.QUARANTINE)
    assert q.stage is Stage.QUARANTINE
    assert repo.graph.get_heads("s1").quarantine_head == rec.version

    a = repo.promote("s1", to_stage=Stage.ACTIVE)
    assert a.stage is Stage.ACTIVE
    assert repo.graph.get_heads("s1").active_head == rec.version

    # get("HEAD") now works
    assert repo.get("s1").stage is Stage.ACTIVE


def test_retire_clears_active_head() -> None:
    repo = SkillRepository()
    rec, ver = _make_record_and_version(stage=Stage.ACTIVE)
    repo.put(rec, version=ver)
    assert repo.graph.get_heads("s1").active_head == rec.version

    repo.retire("s1")
    assert repo.graph.get_heads("s1").active_head is None


def test_promote_without_source_raises() -> None:
    repo = SkillRepository()
    with pytest.raises(KeyError):
        repo.promote("nope", to_stage=Stage.ACTIVE)


# -----------------------------------------------------------------------------
# Listener (REQ-GOV-003 broadcast)
# -----------------------------------------------------------------------------


class _RecordingListener:
    """Simple :class:`SkillListener` that records callbacks."""

    def __init__(self) -> None:
        self.put_calls: list[SkillRecord] = []
        self.promote_calls: list[SkillRecord] = []
        self.retire_calls: list[SkillRecord] = []

    def on_put(self, record: SkillRecord) -> None:
        self.put_calls.append(record)

    def on_promote(self, record: SkillRecord) -> None:
        self.promote_calls.append(record)

    def on_retire(self, record: SkillRecord) -> None:
        self.retire_calls.append(record)


def test_subscribe_fires_lifecycle_callbacks() -> None:
    repo = SkillRepository()
    listener = _RecordingListener()
    repo.subscribe(listener)

    rec, ver = _make_record_and_version(stage=Stage.SANDBOX)
    repo.put(rec, version=ver)
    repo.promote("s1", to_stage=Stage.QUARANTINE)
    repo.promote("s1", to_stage=Stage.ACTIVE)
    repo.retire("s1")

    assert len(listener.put_calls) == 1
    assert len(listener.promote_calls) == 2
    assert len(listener.retire_calls) == 1


def test_listener_exception_does_not_break_repo() -> None:
    """CON-010 related: listener failures are isolated."""

    class BadListener:
        def on_put(self, record: SkillRecord) -> None:
            raise RuntimeError("boom")

        def on_promote(self, record: SkillRecord) -> None: ...

        def on_retire(self, record: SkillRecord) -> None: ...

    repo = SkillRepository()
    repo.subscribe(BadListener())
    rec, ver = _make_record_and_version()
    repo.put(rec, version=ver)  # must not raise
    assert repo.get("s1", version=rec.version) == rec


# -----------------------------------------------------------------------------
# Conservative hook (PR-014 interop)
# -----------------------------------------------------------------------------


def test_conservative_hook_can_reject_put() -> None:
    def always_reject(prev, proposed):
        raise ConservativeRejection("nope")

    repo = SkillRepository(conservative_hook=always_reject)
    rec, ver = _make_record_and_version()
    with pytest.raises(ConservativeRejection):
        repo.put(rec, version=ver)
    # Index unchanged
    assert repo.list() == []


# -----------------------------------------------------------------------------
# Persistence (REQ-GOV-011)
# -----------------------------------------------------------------------------


def test_persistence_roundtrip(tmp_path) -> None:
    repo1 = SkillRepository(base_dir=tmp_path)
    rec, ver = _make_record_and_version(stage=Stage.SANDBOX)
    repo1.put(rec, version=ver)
    repo1.promote("s1", to_stage=Stage.QUARANTINE)
    repo1.promote("s1", to_stage=Stage.ACTIVE)
    repo1.flush()

    # Re-open fresh repository
    graph = SkillVersionGraph()
    # Re-commit the version into the fresh graph (SkillVersion is content
    # hashed so this is fine in production via a full replay of a sibling
    # graph log; for this test we hand-seed).
    graph.commit(ver)
    repo2 = SkillRepository(graph=graph, base_dir=tmp_path)
    recovered = repo2.get("s1")
    assert recovered.stage is Stage.ACTIVE
    assert recovered.version == rec.version


def test_pending_file_discarded_on_reload(tmp_path) -> None:
    repo = SkillRepository(base_dir=tmp_path)
    # Simulate a stale pending file
    (tmp_path / "records.jsonl.pending").write_text("garbage")
    repo.reload()
    assert not (tmp_path / "records.jsonl.pending").exists()


# -----------------------------------------------------------------------------
# Concurrency smoke test (REQ-GOV-009 simplified)
# -----------------------------------------------------------------------------


def test_single_writer_many_readers_smoke() -> None:
    repo = SkillRepository()
    rec, ver = _make_record_and_version()
    repo.put(rec, version=ver)

    errors: list[Exception] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                repo.list()
                repo.get("s1", version=rec.version)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)
                return

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(200):
        repo.list()
    stop.set()
    for t in threads:
        t.join(timeout=1.0)

    assert errors == []
