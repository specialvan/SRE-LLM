"""M1 · Offline SkillOps loop demo.

Exercises PR-001 + PR-002 + PR-014 + PR-015 together. The demo builds
an audit trail on top of the existing :mod:`attention_residuals.sre_control`
autoscaler demo ingredients, then runs the full offline pipeline:

    AuditRecord batch
        └─▶ Trace2SkillMiner  (PR-001)
                └─▶ HierarchicalPatchMerger  (PR-002)
                        └─▶ ConservativeCommit  (PR-014, via Repository hook)
                                └─▶ SkillRepository.put + promote  (PR-012/013)
                                        └─▶ ElitePool.try_admit  (PR-015)

It then intentionally proposes a **regressing** patch (lower floor) and
confirms that the conservative hook rejects it without corrupting repo
state. Everything runs against a ``tmp`` JSONL store so it's idempotent.

Run::

    python -m examples.demo_skillops_m1
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import numpy as np

from attention_residuals.sre_control import AuditRecord
from attention_residuals.skill.governance import (
    ConservativeCommit,
    Elite,
    ElitePool,
    ElitePoolConfig,
    SkillRepository,
    SkillVersionGraph,
)
from attention_residuals.skill.governance.conservative import CommitDecision
from attention_residuals.skill.trajectory import (
    HierarchicalPatchMerger,
    MustAttendSnapshot,
    Trace2SkillMiner,
)
from attention_residuals.skill.trajectory.miner import MinerConfig
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


def _build_audit_batch() -> list[AuditRecord]:
    """Simulate 60 tick autoscaler audit with an error-budget burn."""
    signals = ["p99", "cost", "error_budget"]
    records: list[AuditRecord] = []
    # Healthy steady state (0–19): balanced weights.
    for step in range(20):
        w = np.array([0.45, 0.45, 0.10])
        records.append(
            AuditRecord(
                step=step,
                signal_names=signals,
                weights=w,
                action=np.zeros(1),
                context={"slo_breach": 0.1, "tenant": "east"},
            )
        )
    # Burst (20–49): cost dominates, error_budget starved, SLO breaches.
    for step in range(20, 50):
        w = np.array([0.20, 0.75, 0.05])
        records.append(
            AuditRecord(
                step=step,
                signal_names=signals,
                weights=w,
                action=np.zeros(1),
                context={"slo_breach": 3.5, "tenant": "east"},
            )
        )
    # Recovery (50–59): weights rebalance but SLO still recovering.
    for step in range(50, 60):
        w = np.array([0.30, 0.55, 0.15])
        records.append(
            AuditRecord(
                step=step,
                signal_names=signals,
                weights=w,
                action=np.zeros(1),
                context={"slo_breach": 1.0, "tenant": "east"},
            )
        )
    return records


def main() -> None:
    records = _build_audit_batch()
    print(f"[M1] collected {len(records)} audit records")

    snapshot = MustAttendSnapshot(
        floors={"error_budget": 0.25},           # SLO safety floor
        registry_hash="reg-m1-v1",
    )

    miner = Trace2SkillMiner(
        config=MinerConfig(
            support_min=10,
            cost_quantile=0.5,   # keep top-half-cost records
            cluster_k_max=1,
            max_candidates=5,
        )
    )
    candidates = miner.mine(records, snapshot)
    print(f"[M1] miner produced {len(candidates)} candidate(s)")
    for c in candidates:
        for t in c.targets:
            print(
                f"       · {t.signal_name:<14} {t.field.value:<11} "
                f"Δ={t.delta:+.3f}  support={c.support}  score={c.score:.2f}"
            )

    merger = HierarchicalPatchMerger(snapshot)
    merged = merger.merge(candidates)
    print(
        f"[M1] merged into {len(merged.targets)} target(s) "
        f"(dropped={len(merged.dropped)}, conflicts={len(merged.conflicts)})"
    )
    for t in merged.targets:
        print(f"       · {t.signal_name} {t.field.value} Δ={t.delta:+.3f}")

    # Conservative hook wired into the repository.
    conservative = ConservativeCommit()

    def hook(prev, proposed) -> None:
        verdict = conservative.check(prev, proposed)
        if verdict.decision is CommitDecision.REJECT:
            raise RuntimeError(f"conservative rejected: {verdict.reason}")

    with tempfile.TemporaryDirectory() as tmp:
        graph = SkillVersionGraph()
        repo = SkillRepository(
            graph=graph, base_dir=Path(tmp), conservative_hook=hook
        )
        pool = ElitePool(ElitePoolConfig(capacity=4, min_probation_steps=1))

        # ---- commit merged patch as a new skill ----
        skill_id = "m1-error-budget-tighten"
        targets = merged.targets
        if not targets:
            print("[M1] merger produced no targets; nothing to commit")
            return

        version = SkillVersion(
            version_id=compute_version_id(skill_id, targets, (), "m1-bot"),
            skill_id=skill_id,
            parents=(),
            author="m1-bot",
            timestamp=time.time(),
            summary="offline distillation",
            change_kind=ChangeKind.CREATE,
            blast_radius=BlastRadius.compute(
                [t.signal_name for t in targets], ["east"], 0.1
            ),
        )
        record = SkillRecord(
            skill_id=skill_id,
            version=version.version_id,
            tenant="east",
            stage=Stage.SANDBOX,
            meta={"author": "M1 demo"},
            targets=targets,
        )
        repo.put(record, version=version)
        repo.promote(skill_id, to_stage=Stage.QUARANTINE, tenant="east")
        repo.promote(skill_id, to_stage=Stage.ACTIVE, tenant="east")
        print(f"[M1] put + promoted to ACTIVE · version={version.version_id[:8]}")

        ev = pool.try_admit(Elite(variant_id=version.version_id, score=0.87))
        pool.evict_probation_breakers(step=5)
        print(
            f"[M1] elite pool · size={len(pool)}  event={ev!r}  "
            f"elite_ids={pool.elite_ids()[:3]}"
        )

        # ---- try a deliberately regressing patch ----
        regressing_targets = (
            PatchTarget(
                "error_budget",
                PatchField.FLOOR,
                max(
                    0.0,
                    targets[0].delta - 0.05  # drop it below current by 0.05
                    if targets[0].field is PatchField.FLOOR
                    else 0.02,
                ),
                "regression test",
            ),
        )
        bad_version = SkillVersion(
            version_id=compute_version_id(
                skill_id, regressing_targets, (version.version_id,), "m1-bot"
            ),
            skill_id=skill_id,
            parents=(version.version_id,),
            author="m1-bot",
            timestamp=time.time() + 1,
            summary="regression",
            change_kind=ChangeKind.EDIT,
            blast_radius=BlastRadius.compute(
                [t.signal_name for t in regressing_targets], ["east"], 0.1
            ),
        )
        bad_record = SkillRecord(
            skill_id=skill_id,
            version=bad_version.version_id,
            tenant="east",
            stage=Stage.SANDBOX,
            meta={"note": "should be blocked"},
            targets=regressing_targets,
        )

        try:
            repo.put(bad_record, version=bad_version)
            print("[M1] WARNING: conservative hook did not block regression!")
        except RuntimeError as exc:
            print(f"[M1] conservative hook blocked regression: {exc}")

        # ---- Sanity: still exactly one skill in repo for this skill_id ----
        active = repo.get(skill_id, tenant="east")
        print(
            f"[M1] final state · active_version={active.version[:8]} "
            f"stage={active.stage.value}  "
            f"repo_size={len(repo.list(tenant='east'))}"
        )


if __name__ == "__main__":
    main()
