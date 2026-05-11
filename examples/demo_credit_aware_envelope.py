"""Round 7 demo: soft labels + temporal credit for self-learning envelopes.

The previous self-learning envelope reacted to hard SAFE/UNSAFE labels.
This demo adds a more production-shaped question:

    "The SLO was breached, but was the controller action actually to blame?"

We feed the same UNSAFE outcome through a TemporalCreditAssigner. If blame
mostly lands on exogenous traffic, the label is downgraded to weak UNSAFE
evidence. If blame lands on the controller, the evidence stays strong and
the envelope ratchets tighter.

Run with::

    python -m examples.demo_credit_aware_envelope
"""

from __future__ import annotations

import numpy as np

from attention_residuals.sre_math import TemporalCreditAssigner
from attention_residuals.sre_self_envelope import (
    CreditAwareLabeler,
    EnvelopeLearner,
    LearnedSafetyEnvelope,
    OutcomeLabel,
)


def make_env() -> LearnedSafetyEnvelope:
    return LearnedSafetyEnvelope(
        action_dim=1,
        hard_low=np.array([-5.0]),
        hard_high=np.array([+5.0]),
        hard_max_delta=np.array([5.0]),
        min_max_delta=np.array([0.25]),
        safe_quantile=0.9,
        hysteresis=0.1,
        unsafe_quorum=2,
        min_safe_samples=12,
        buffer_size=200,
    )


def base_labeler(ctx: dict) -> OutcomeLabel:
    return OutcomeLabel.UNSAFE if ctx["breach"] else OutcomeLabel.SAFE


def scenario(tick: int) -> tuple[float, bool, np.ndarray, np.ndarray, str]:
    """Return action, breach, credit weights, credit losses, phase name."""
    if tick < 20:
        return 1.0, False, np.array([0.5, 0.5]), np.array([0.1, 0.1]), "warmup"
    if 20 <= tick < 25:
        # SLO breach driven by upstream traffic, not by the controller.
        return 1.1, True, np.array([0.1, 0.9]), np.array([0.1, 1.0]), "traffic"
    if 40 <= tick < 45:
        # Same hard UNSAFE label, but now credit says controller overshoot.
        return 4.0, True, np.array([0.9, 0.1]), np.array([1.0, 0.1]), "controller"
    return 1.0, False, np.array([0.5, 0.5]), np.array([0.1, 0.1]), "recovery"


def main() -> None:
    env = make_env()
    credit = TemporalCreditAssigner(decay=1.0)
    labeler = CreditAwareLabeler(
        base_labeler=base_labeler,
        credit_assigner=credit,
        controllable_signals=["controller"],
        window=8,
    )
    learner = EnvelopeLearner(env, labeler=labeler, fit_every=1)

    print("=" * 86)
    print("Round 7: credit-aware self-learning envelope")
    print("=" * 86)
    print(
        f"{'t':>2} {'phase':>10} {'raw':>5} {'hard':>6} {'ctrl_ratio':>10} "
        f"{'unsafe_ev':>9} {'low..high':>18} {'tighten':>8}"
    )

    last_fit_len = 0
    for tick in range(60):
        action, breach, weights, losses, phase = scenario(tick)
        credit.record(
            tick,
            weights=weights,
            losses=losses,
            signal_names=["controller", "traffic"],
        )
        evidence = learner.ingest(
            np.array([action]),
            {"tick": tick, "breach": breach},
            step=tick,
        )
        bounds = env.current_bounds()
        fit_history = env.fit_history()
        new_fits = fit_history[last_fit_len:]
        last_fit_len = len(fit_history)
        tightened = any(
            f.get("tightened_high") or f.get("tightened_low")
            or f.get("tightened_max_delta")
            for f in new_fits
        )
        if breach or tightened or tick in {0, 19, 25, 39, 45, 59}:
            adj = labeler.last_adjustment()
            print(
                f"{tick:>2} {phase:>10} {action:>+5.1f} "
                f"{base_labeler({'breach': breach}).value:>6} "
                f"{adj.get('controllable_ratio', 1.0):>10.2f} "
                f"{evidence.unsafe_weight:>9.2f} "
                f"[{bounds['low'][0]:>+5.2f},{bounds['high'][0]:>+5.2f}] "
                f"{'YES' if tightened else '':>8}"
            )

    print()
    print("Final stats")
    print("  hard UNSAFE events        :", learner.stats.unsafe)
    print("  accumulated unsafe evidence:", f"{learner.stats.unsafe_evidence:.2f}")
    print("  final bounds              :",
          f"[{env.current_low[0]:+.2f}, {env.current_high[0]:+.2f}]")
    print()
    print("Reading: traffic breaches stay weak; controller-caused breaches ratchet.")


if __name__ == "__main__":
    main()
