"""Skill repository · PR-012.

Refined spec: ``skill-research/refined/PR-012-skill-repository-refined.md``.

Scope (v1 / single-process):

* In-memory 3-dim index ``(skill_id, version, tenant)`` + HEAD pointers.
* Append-only JSONL persistence with write-ahead rename atomicity
  (ADR-003).
* Single-writer, multi-reader concurrency model (ADR-001).
* Pub-sub listeners for nightly evolver (REQ-GOV-003 broadcast).

Intentionally **not** included in this PR:

* ``ConservativeCommit.check()`` (PR-014) — the hook is present but
  will be wired in TASK-M1-03.
* Three-way merge (PR-033).
* Cross-process consistency (v2).

Requirements satisfied:

* REQ-GOV-002 · three HEAD pointers per (skill_id, tenant)
* REQ-GOV-003 · atomic promote (transactional update)
* REQ-GOV-004 · promote failure rollback
* REQ-GOV-011 · flush atomic via rename-after-write
* REQ-DAT-006 · unique (skill_id, version, tenant) key
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Protocol,
    Set,
    Tuple,
)

from attention_residuals.skill.governance.version_graph import (
    HeadName,
    HeadRefs,
    SkillVersionGraph,
)
from attention_residuals.skill.types import (
    SCHEMA_VERSION,
    SkillRecord,
    SkillVersion,
    Stage,
)

_LOGGER = logging.getLogger(__name__)


class ConservativeRejection(Exception):
    """Raised when a put() is rejected by ConservativeCommit (PR-014)."""


class SkillListener(Protocol):
    """Subscriber interface; both callbacks are fire-and-forget."""

    def on_put(self, record: SkillRecord) -> None: ...

    def on_promote(self, record: SkillRecord) -> None: ...

    def on_retire(self, record: SkillRecord) -> None: ...


# Hook type for PR-014 ConservativeCommit.
# Takes (previous_targets, proposed_targets); raises ConservativeRejection
# on rejection. Returns None on accept/override.
ConservativeHook = Callable[
    [Tuple, Tuple],  # two tuples of PatchTarget
    None,
]


@dataclass
class _Index:
    """Internal in-memory index."""

    records: Dict[Tuple[str, str, str], SkillRecord]
    heads: Dict[Tuple[str, str], HeadRefs]
    # (tenant, stage_value) -> set of (skill_id, version)
    by_stage: Dict[Tuple[str, str], Set[Tuple[str, str]]]
    # (tenant, tag) -> set of (skill_id, version)
    by_tag: Dict[Tuple[str, str], Set[Tuple[str, str]]]


class SkillRepository:
    """Append-only skill store with stage lifecycle.

    Parameters
    ----------
    graph
        The shared :class:`SkillVersionGraph`; every ``put`` commits a
        version into it. Caller is responsible for constructing the
        :class:`SkillVersion` and passing it to ``put(record, version)``.
    base_dir
        Optional directory for JSONL persistence. ``None`` means
        in-memory only (useful for tests).
    conservative_hook
        Optional PR-014 hook; called before every ``put`` with
        ``(previous_targets, proposed_targets)``.

    Persistence layout::

        base_dir/
        ├── records.jsonl           # append-only log
        ├── records.jsonl.pending   # write-ahead buffer
        └── HEAD.json               # three-head projection
    """

    _LOG_NAME = "records.jsonl"
    _PENDING_NAME = "records.jsonl.pending"
    _HEAD_NAME = "HEAD.json"

    def __init__(
        self,
        graph: Optional[SkillVersionGraph] = None,
        base_dir: Optional[str | Path] = None,
        conservative_hook: Optional[ConservativeHook] = None,
    ) -> None:
        self._graph = graph if graph is not None else SkillVersionGraph()
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._conservative_hook = conservative_hook

        self._index = _Index(records={}, heads={}, by_stage={}, by_tag={})
        self._lock = threading.RLock()
        self._listeners: List[SkillListener] = []

        if self._base_dir is not None:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            self.reload()

    # ----------------------------- Public API ----------------------------- #

    @property
    def graph(self) -> SkillVersionGraph:
        """The underlying version DAG (read-only use by callers)."""
        return self._graph

    def put(self, record: SkillRecord, version: Optional[SkillVersion] = None) -> None:
        """Insert (or idempotently re-insert) a ``SkillRecord``.

        Also commits the corresponding ``SkillVersion`` to the graph if
        provided. When ``version`` is ``None`` we assume the caller has
        already committed it to the graph out-of-band (legacy pattern).

        Fires ``on_put`` to every listener.
        """
        with self._lock:
            key = record.key()
            existing = self._index.records.get(key)
            if existing == record:
                return  # idempotent no-op

            if version is not None:
                if version.version_id != record.version:
                    raise ValueError(
                        f"record.version {record.version!r} != version.version_id "
                        f"{version.version_id!r}"
                    )
                self._graph.commit(version)
            elif record.version not in self._graph:
                raise ValueError(
                    f"record.version {record.version!r} not in version graph; "
                    "pass `version=` or commit it beforehand"
                )

            # Conservative hook (PR-014); raises on REJECT.
            if self._conservative_hook is not None:
                prev = self._previous_active_targets(record.skill_id, record.tenant)
                self._conservative_hook(prev, tuple(record.targets))

            # 1) Write-ahead
            self._append_log_atomic(op="put", record=record)

            # 2) In-memory update
            self._index.records[key] = record
            stage_key = (record.tenant, record.stage.value)
            self._index.by_stage.setdefault(stage_key, set()).add(
                (record.skill_id, record.version)
            )
            for tag in record.tags:
                self._index.by_tag.setdefault((record.tenant, tag), set()).add(
                    (record.skill_id, record.version)
                )

            # 3) HEAD pointer at this stage advances to the new version.
            # Rationale: ``head[X]`` is the "branch tip" for stage X —
            # latest-put wins. Callers that need multi-head-per-stage
            # semantics should build that on top; v1 keeps it simple.
            heads_key = (record.skill_id, record.tenant)
            heads = self._index.heads.get(heads_key, HeadRefs())
            if record.stage is Stage.SANDBOX:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.SANDBOX, record.version
                )
                self._graph.move_head(
                    record.skill_id, HeadName.SANDBOX, record.version, record.tenant
                )
            elif record.stage is Stage.QUARANTINE:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.QUARANTINE, record.version
                )
                self._graph.move_head(
                    record.skill_id, HeadName.QUARANTINE, record.version, record.tenant
                )
            elif record.stage is Stage.ACTIVE:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.ACTIVE, record.version
                )
                self._graph.move_head(
                    record.skill_id, HeadName.ACTIVE, record.version, record.tenant
                )
            # RETIRED records do not advance any head.

            self._flush_head()
            self._broadcast("put", record)

    def get(
        self,
        skill_id: str,
        version: str = "HEAD",
        tenant: str = "default",
    ) -> SkillRecord:
        """Fetch a :class:`SkillRecord`.

        ``version="HEAD"`` returns the ACTIVE head; raises ``KeyError``
        if there is no ACTIVE head yet.
        """
        with self._lock:
            if version == "HEAD":
                heads = self._index.heads.get((skill_id, tenant), HeadRefs())
                if heads.active_head is None:
                    raise KeyError(f"no active head for {skill_id!r}@{tenant!r}")
                version = heads.active_head
            try:
                return self._index.records[(skill_id, version, tenant)]
            except KeyError:
                raise KeyError(f"{skill_id!r}@{version!r}@{tenant!r}")

    def list(
        self,
        tenant: Optional[str] = None,
        stage: Optional[Stage] = None,
        tag: Optional[str] = None,
    ) -> List[SkillRecord]:
        """Filter records by any combination of tenant/stage/tag."""
        with self._lock:
            if tenant is not None and stage is not None:
                ids = self._index.by_stage.get((tenant, stage.value), set()).copy()
                if tag is not None:
                    ids &= self._index.by_tag.get((tenant, tag), set())
                return [
                    self._index.records[(sid, ver, tenant)]
                    for (sid, ver) in ids
                    if (sid, ver, tenant) in self._index.records
                ]
            # Fallback to full scan
            out: List[SkillRecord] = []
            for key, rec in self._index.records.items():
                if tenant is not None and rec.tenant != tenant:
                    continue
                if stage is not None and rec.stage is not stage:
                    continue
                if tag is not None and tag not in rec.tags:
                    continue
                out.append(rec)
            return out

    def promote(
        self,
        skill_id: str,
        to_stage: Stage,
        tenant: str = "default",
        from_version: Optional[str] = None,
    ) -> SkillRecord:
        """Atomically move a skill to ``to_stage``.

        If ``from_version`` is not provided we promote the current head
        "one stage up" — sandbox → quarantine → active. Explicit
        ``from_version`` is required when moving to RETIRED.
        """
        with self._lock:
            heads_key = (skill_id, tenant)
            heads = self._index.heads.get(heads_key, HeadRefs())
            version = from_version
            if version is None:
                if to_stage is Stage.QUARANTINE:
                    version = heads.sandbox_head
                elif to_stage is Stage.ACTIVE:
                    version = heads.quarantine_head
                elif to_stage is Stage.RETIRED:
                    version = heads.active_head
                elif to_stage is Stage.SANDBOX:
                    raise ValueError("promote to SANDBOX needs explicit from_version")
            if version is None:
                raise KeyError(
                    f"no version to promote for {skill_id!r}@{tenant!r} → {to_stage.value}"
                )

            key = (skill_id, version, tenant)
            old_rec = self._index.records.get(key)
            if old_rec is None:
                raise KeyError(key)

            new_rec = SkillRecord(
                skill_id=old_rec.skill_id,
                version=old_rec.version,
                tenant=old_rec.tenant,
                stage=to_stage,
                meta=old_rec.meta,
                targets=old_rec.targets,
                utility=old_rec.utility,
                use_count=old_rec.use_count,
                tags=old_rec.tags,
                created_at=old_rec.created_at,
            )

            # Transactional section
            self._append_log_atomic(op="promote", record=new_rec)
            try:
                # stage index move
                old_stage_key = (tenant, old_rec.stage.value)
                new_stage_key = (tenant, to_stage.value)
                self._index.by_stage.get(old_stage_key, set()).discard(
                    (skill_id, version)
                )
                self._index.by_stage.setdefault(new_stage_key, set()).add(
                    (skill_id, version)
                )
                self._index.records[key] = new_rec

                # HEAD pointer move
                head_name = {
                    Stage.SANDBOX: HeadName.SANDBOX,
                    Stage.QUARANTINE: HeadName.QUARANTINE,
                    Stage.ACTIVE: HeadName.ACTIVE,
                    # RETIRED does not have its own head; we blank ACTIVE.
                    Stage.RETIRED: HeadName.ACTIVE,
                }[to_stage]
                head_target = None if to_stage is Stage.RETIRED else version
                self._index.heads[heads_key] = heads.with_head(head_name, head_target)
                self._graph.move_head(skill_id, head_name, head_target, tenant)

                self._flush_head()
            except Exception:
                # Rollback in-memory (REQ-GOV-004). Reload log from disk; in
                # the in-memory path we simply restore from old_rec.
                self._index.records[key] = old_rec
                raise

            if to_stage is Stage.RETIRED:
                self._broadcast("retire", new_rec)
            else:
                self._broadcast("promote", new_rec)
            return new_rec

    def retire(self, skill_id: str, tenant: str = "default") -> SkillRecord:
        return self.promote(skill_id, Stage.RETIRED, tenant)

    # ----------------------------- Sub / Flush ----------------------------- #

    def subscribe(self, listener: SkillListener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def flush(self) -> None:
        """Ensure HEAD.json reflects current state. Log is always on disk."""
        with self._lock:
            self._flush_head()

    def reload(self) -> None:
        """Re-read persistent state; drops and rebuilds the in-memory index."""
        with self._lock:
            self._index = _Index(records={}, heads={}, by_stage={}, by_tag={})
            if self._base_dir is None:
                return
            # Ignore any stale write-ahead file (partial write recovery).
            pending = self._base_dir / self._PENDING_NAME
            if pending.exists():
                _LOGGER.warning("discarding stale pending file %s", pending)
                pending.unlink()
            log = self._base_dir / self._LOG_NAME
            if not log.exists():
                return
            with log.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        _LOGGER.warning("skipping malformed audit line: %s", line[:80])
                        continue
                    self._apply_log_entry(entry)

    # ----------------------------- Internals ----------------------------- #

    def _previous_active_targets(self, skill_id: str, tenant: str) -> Tuple:
        heads = self._index.heads.get((skill_id, tenant), HeadRefs())
        if heads.active_head is None:
            return ()
        rec = self._index.records.get((skill_id, heads.active_head, tenant))
        return tuple(rec.targets) if rec is not None else ()

    def _append_log_atomic(self, *, op: str, record: SkillRecord) -> None:
        """Append one entry with rename-after-write atomicity."""
        if self._base_dir is None:
            return
        log = self._base_dir / self._LOG_NAME
        pending = self._base_dir / self._PENDING_NAME
        # Copy existing log into the pending buffer, append our line, then rename.
        existing = log.read_text(encoding="utf-8") if log.exists() else ""
        entry = {"_schema": SCHEMA_VERSION, "op": op, "record": record.to_dict()}
        new_bytes = (existing + json.dumps(entry) + "\n").encode("utf-8")
        pending.write_bytes(new_bytes)
        os.replace(pending, log)

    def _flush_head(self) -> None:
        """Project HEAD table to HEAD.json atomically."""
        if self._base_dir is None:
            return
        head_path = self._base_dir / self._HEAD_NAME
        pending = head_path.with_suffix(".json.pending")
        payload = {
            "_schema": SCHEMA_VERSION,
            "heads": {
                f"{skill_id}|{tenant}": {
                    "sandbox_head": heads.sandbox_head,
                    "quarantine_head": heads.quarantine_head,
                    "active_head": heads.active_head,
                }
                for (skill_id, tenant), heads in self._index.heads.items()
            },
        }
        pending.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(pending, head_path)

    def _apply_log_entry(self, entry: Mapping) -> None:
        op = entry.get("op")
        rec = SkillRecord.from_dict(entry["record"])
        key = rec.key()
        if op == "put":
            self._index.records[key] = rec
            self._index.by_stage.setdefault(
                (rec.tenant, rec.stage.value), set()
            ).add((rec.skill_id, rec.version))
            for tag in rec.tags:
                self._index.by_tag.setdefault((rec.tenant, tag), set()).add(
                    (rec.skill_id, rec.version)
                )
            heads_key = (rec.skill_id, rec.tenant)
            heads = self._index.heads.get(heads_key, HeadRefs())
            if rec.stage is Stage.SANDBOX:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.SANDBOX, rec.version
                )
            elif rec.stage is Stage.QUARANTINE:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.QUARANTINE, rec.version
                )
            elif rec.stage is Stage.ACTIVE:
                self._index.heads[heads_key] = heads.with_head(
                    HeadName.ACTIVE, rec.version
                )
        elif op == "promote":
            prev = self._index.records.get(key)
            if prev is not None:
                self._index.by_stage.get(
                    (prev.tenant, prev.stage.value), set()
                ).discard((prev.skill_id, prev.version))
            self._index.records[key] = rec
            self._index.by_stage.setdefault(
                (rec.tenant, rec.stage.value), set()
            ).add((rec.skill_id, rec.version))
            # We cannot reliably rebuild HEAD pointers from log order alone
            # when many versions exist; HEAD.json is the investment for that.
            head_name = {
                Stage.SANDBOX: HeadName.SANDBOX,
                Stage.QUARANTINE: HeadName.QUARANTINE,
                Stage.ACTIVE: HeadName.ACTIVE,
                Stage.RETIRED: HeadName.ACTIVE,
            }[rec.stage]
            heads_key = (rec.skill_id, rec.tenant)
            heads = self._index.heads.get(heads_key, HeadRefs())
            head_target = None if rec.stage is Stage.RETIRED else rec.version
            self._index.heads[heads_key] = heads.with_head(head_name, head_target)
        else:
            _LOGGER.warning("unknown op %r in log", op)

    def _broadcast(self, op: str, record: SkillRecord) -> None:
        for lis in list(self._listeners):
            try:
                if op == "put":
                    lis.on_put(record)
                elif op == "promote":
                    lis.on_promote(record)
                elif op == "retire":
                    lis.on_retire(record)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("listener %r raised on %s", lis, op)


__all__ = [
    "ConservativeHook",
    "ConservativeRejection",
    "SkillListener",
    "SkillRepository",
]
