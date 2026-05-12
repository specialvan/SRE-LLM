"""M2 · Online routing demo.

Walks through the full online loop:

* mine + merge + admit a skill (borrowed from M1 demo);
* build a :class:`DualGranularitySkillBank`, register the admitted skill;
* index the skill's embedding in :class:`UtilityAwareRetriever`;
* simulate 60 ticks of traffic where the ACTIVE skill outperforms a
  baseline competitor — :class:`HindsightUtilityTracker` pushes its
  ``u_ema`` up, :class:`ExplorationBiasScheduler` decays β as it gets used;
* have the :class:`SkillRouter` pick at each tick and log the rationale.

At the end we print the TCA skill-level attribution that a post-mortem
tool would show on an incident.

Run::

    python -m examples.demo_skillops_m2
"""

from __future__ import annotations

import math

import numpy as np

from attention_residuals.sre_math import TemporalCreditAssigner
from attention_residuals.skill.policy_skill import (
    DualGranularitySkillBank,
    ExplorationBiasScheduler,
    ExploreConfig,
    HindsightConfig,
    HindsightUtilityTracker,
    RetrieverConfig,
    RouterConfig,
    SkillRouter,
    StepSkill,
    UtilityAwareRetriever,
)
from attention_residuals.skill.types import (
    Granularity,
    PatchField,
    PatchTarget,
)


def _unit(*v: float) -> np.ndarray:
    arr = np.array(v, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


def main() -> None:
    bank = DualGranularitySkillBank()
    retriever = UtilityAwareRetriever(
        dim=2,
        config=RetrieverConfig(lambda_util=0.8, lambda_explore=0.2),
    )
    tca = TemporalCreditAssigner(decay=0.95)
    utility = HindsightUtilityTracker(
        HindsightConfig(alpha_ema=0.3, min_uses_for_judgment=5),
        tca=tca,
    )
    explore = ExplorationBiasScheduler(
        ExploreConfig(beta0=0.4, min_protection_uses=5, global_budget=5.0)
    )
    router = SkillRouter(
        bank=bank,
        retriever=retriever,
        utility=utility,
        explore=explore,
        config=RouterConfig(default_top_k=2),
    )

    # Two candidate step-skills. "tighten" is the M1-admitted winner;
    # "loosen" is a competing variant the router will be shown but
    # shouldn't favour once utility evidence accumulates.
    bank.put_step(
        StepSkill(
            skill_id="tighten",
            targets=(
                PatchTarget("error_budget", PatchField.FLOOR, 0.05, "tighten"),
                PatchTarget("cost", PatchField.CEILING, -0.10, "cap cost"),
            ),
        )
    )
    bank.put_step(
        StepSkill(
            skill_id="loosen",
            targets=(
                PatchTarget("cost", PatchField.BIAS, 0.03, "loosen cost"),
            ),
        )
    )
    # The two skills have similar embeddings so the router needs utility
    # evidence to separate them.
    retriever.upsert("tighten", _unit(1.0, 0.05))
    retriever.upsert("loosen", _unit(1.0, 0.0))

    print("[M2] bootstrap: 2 step skills registered")

    # ---- simulate 60 ticks ----
    query = _unit(1.0, 0.0)
    for step in range(1, 61):
        decisions = router.pick(query, top_k=2)
        top = decisions[0] if decisions else None
        if top is None:
            continue

        # "Ground truth" rewards: tighten is the right move, loosen is not.
        if top.skill_id == "tighten":
            m_with = 1.0 + np.random.default_rng(step).normal(0, 0.05)
            m_without = 0.3
        else:
            m_with = 0.2 + np.random.default_rng(step).normal(0, 0.05)
            m_without = 0.6
        utility.observe(
            top.skill_id,
            m_with=float(m_with),
            m_without=m_without,
            step=step,
            signals=[("cost" if top.skill_id == "loosen" else "error_budget", 1.0)],
            context={"tenant": 1.0},
        )

        if step in (1, 5, 15, 30, 60):
            snap_util = utility.snapshot(top.skill_id)
            print(
                f"[tick {step:>3}] pick={top.skill_id:<7} "
                f"conf={top.confidence:.2f}  "
                f"sim={top.rationale.sim_score:+.3f} "
                f"u={top.rationale.utility_score:+.3f} "
                f"β={top.rationale.exploration_bonus:+.3f} "
                f"→ u_ema({top.skill_id})={snap_util.utility_ema:+.3f} "
                f"n={snap_util.n_observed}"
            )

    # ---- post-mortem attribution ----
    good = utility.snapshot("tighten")
    bad = utility.snapshot("loosen")
    print(
        f"[summary] tighten: u_ema={good.utility_ema:+.3f}, n={good.n_observed}, "
        f"conf={good.confidence:.2f}"
    )
    print(
        f"[summary] loosen:  u_ema={bad.utility_ema:+.3f}, n={bad.n_observed}, "
        f"conf={bad.confidence:.2f}"
    )
    blame = tca.attribute_skill(incident_tick=60, window=60, top_k=5)
    if blame:
        print("[TCA skill attribution]")
        for entry in blame[:5]:
            print(
                f"    score={entry.score:.3f} "
                f"tick={entry.tick:>3} "
                f"loss={entry.loss:.2f}  {entry.signal_name}"
            )
    else:
        print("[TCA skill attribution] (no negative utility in window)")


if __name__ == "__main__":
    main()
