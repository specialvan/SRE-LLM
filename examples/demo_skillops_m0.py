"""M0 · SkillOps foundation demo.

Exercises the PR-012 + PR-013 stack end-to-end *without* touching any
existing ``sre_control`` behaviour (ADR-004). The demo:

1. Boots a :class:`SkillRepository` with a fresh
   :class:`SkillVersionGraph`, persisting to a tempdir.
2. Creates three versions of one skill: ``v1`` (sandbox) → ``v2``
   (edit, sandbox) → promote both through ``quarantine`` and ``active``.
3. Simulates a regression by reverting ACTIVE back to ``v1`` via
   :meth:`SkillVersionGraph.revert_to`.
4. Proves JSONL round-trip by reloading the repo from disk and checking
   the ACTIVE head.

Run::

    python -m examples.demo_skillops_m0
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from attention_residuals.skill.governance import (
    SkillRepository,
    SkillVersionGraph,
)
from attention_residuals.skill.governance.version_graph import HeadName
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


_BLAST = BlastRadius.compute(
    affected_signals=("p99", "error_budget"),
    affected_tenants=("east",),
    estimated_traffic_share=0.1,
)


def _mk_version(
    skill_id: str,
    parents: tuple[str, ...],
    targets: tuple[PatchTarget, ...],
    author: str = "demo",
    summary: str = "",
    kind: ChangeKind = ChangeKind.EDIT,
) -> SkillVersion:
    vid = compute_version_id(skill_id, targets, parents, author)
    return SkillVersion(
        version_id=vid,
        skill_id=skill_id,
        parents=parents,
        author=author,
        timestamp=time.time(),
        summary=summary or f"{kind.value} @ {skill_id[:6]}",
        change_kind=kind,
        blast_radius=_BLAST,
    )


def _mk_record(
    skill_id: str,
    version: str,
    targets: tuple[PatchTarget, ...],
    stage: Stage,
    tenant: str = "east",
) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        version=version,
        tenant=tenant,
        stage=stage,
        meta={"name": skill_id, "desc": "demo skill"},
        targets=targets,
        created_at=time.time(),
    )


def main() -> None:
    skill_id = "err-budget-tighten"
    t_v1 = (
        PatchTarget(
            "error_budget", PatchField.FLOOR, 0.05, "observed under-attention"
        ),
    )
    t_v2 = (
        PatchTarget(
            "error_budget", PatchField.FLOOR, 0.08, "tighten further after v1"
        ),
        PatchTarget("cost", PatchField.CEILING, -0.1, "cap cost opportunism"),
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        graph = SkillVersionGraph()
        repo = SkillRepository(graph=graph, base_dir=base)

        # ---- Step 1: create v1 and park it in sandbox --------------------
        v1 = _mk_version(
            skill_id, parents=(), targets=t_v1, kind=ChangeKind.CREATE
        )
        r_v1 = _mk_record(skill_id, v1.version_id, t_v1, Stage.SANDBOX)
        repo.put(r_v1, version=v1)

        # ---- Step 2: promote v1 all the way to ACTIVE --------------------
        repo.promote(skill_id, to_stage=Stage.QUARANTINE, tenant="east")
        repo.promote(skill_id, to_stage=Stage.ACTIVE, tenant="east")
        print(f"[M0] v1 promoted to ACTIVE: {v1.version_id}")

        # ---- Step 3: author v2 (edit) ------------------------------------
        v2 = _mk_version(
            skill_id, parents=(v1.version_id,), targets=t_v2, kind=ChangeKind.EDIT
        )
        r_v2 = _mk_record(skill_id, v2.version_id, t_v2, Stage.SANDBOX)
        repo.put(r_v2, version=v2)
        assert graph.get_heads(skill_id, "east").sandbox_head == v2.version_id

        # We promote v2 past quarantine but decide it regresses in active.
        repo.promote(
            skill_id,
            to_stage=Stage.QUARANTINE,
            tenant="east",
            from_version=v2.version_id,
        )
        repo.promote(
            skill_id,
            to_stage=Stage.ACTIVE,
            tenant="east",
            from_version=v2.version_id,
        )
        print(f"[M0] v2 promoted to ACTIVE: {v2.version_id}")

        # ---- Step 4: regression detected → revert to v1 ------------------
        revert = graph.revert_to(target=v1.version_id, skill_id=skill_id, tenant="east")
        # Also sync the repo ACTIVE head back to v1 so that get("HEAD") works.
        # (In the full pipeline this is handled by MonotoneGuard → Repository;
        #  at M0 we wire it by hand.)
        repo.promote(
            skill_id,
            to_stage=Stage.ACTIVE,
            tenant="east",
            from_version=v1.version_id,
        )
        print(
            f"[M0] regression recovered · revert commit={revert.version_id[:8]} "
            f"parents={[p[:8] for p in revert.parents]}"
        )

        # ---- Step 5: reload from disk and verify -------------------------
        repo.flush()
        log = (base / "records.jsonl").read_text(encoding="utf-8")
        head = json.loads((base / "HEAD.json").read_text(encoding="utf-8"))
        graph2 = SkillVersionGraph()
        for version in [v1, v2, revert]:
            graph2.commit(version)
        repo2 = SkillRepository(graph=graph2, base_dir=base)
        active = repo2.get(skill_id, tenant="east")
        print(f"[M0] reload OK · active head = {active.version} (stage={active.stage.value})")

        # ---- Step 6: tiny stats dump --------------------------------------
        active_records = repo2.list(stage=Stage.ACTIVE, tenant="east")
        print(
            f"[M0] repo state · versions committed={len(graph2)}, "
            f"active={len(active_records)}, "
            f"log bytes={len(log)}, head.json keys={list(head.keys())}"
        )


if __name__ == "__main__":
    main()
