"""Tail AuditTrail JSONL into TemporalCreditAssigner incrementally.

Run with::

    python -m examples.demo_streaming_audit_replay
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from attention_residuals.sre_math import (
    AuditCreditReplay,
    MetricLossMapper,
    MetricLossSpec,
    StreamingAuditCreditReplay,
    TemporalCreditAssigner,
)


def audit_line(step: int, weights: list[float], controller_error: float, traffic_spike: float) -> str:
    return json.dumps({
        "step": step,
        "signals": ["controller", "traffic"],
        "weights": weights,
        "action": [weights[0] * 2.0 + weights[1] * 1.0],
        "context": {
            "controller_error": controller_error,
            "traffic_spike": traffic_spike,
        },
    })


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


def main() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        tca = TemporalCreditAssigner(decay=0.95)
        replay = AuditCreditReplay(
            tca,
            MetricLossMapper({
                "controller": MetricLossSpec("controller_error", mode="raw"),
                "traffic": MetricLossSpec("traffic_spike", mode="raw"),
            }),
        )
        tail = StreamingAuditCreditReplay(replay, str(path), missing_ok=True)

        first = tail.poll()
        append(path, audit_line(0, [0.2, 0.8], 0.1, 3.0) + "\n")
        second = tail.poll()
        append(path, audit_line(1, [0.9, 0.1], 4.0, 0.2))
        partial = tail.poll()
        append(path, "\n" + audit_line(2, [0.85, 0.15], 3.0, 0.1) + "\n")
        final = tail.poll()
        skip_tail = StreamingAuditCreditReplay(
            replay,
            str(path),
            missing_ok=True,
            skip_bad_lines=True,
            cursor=tail.cursor,
        )
        append(path, "{bad-json}\n" + audit_line(3, [0.95, 0.05], 5.0, 0.1) + "\n")
        recovered = skip_tail.poll()

        blamed = tca.attribute(incident_tick=3, window=5, top_k=6)

        print("=" * 78)
        print("Streaming Audit JSONL -> TemporalCreditAssigner")
        print("=" * 78)
        print(
            "Poll counts: "
            f"missing={first}, first={second}, partial={partial}, "
            f"final={final}, recovered_after_bad_line={recovered}"
        )
        print(
            f"Cursor offset={skip_tail.cursor.offset}, "
            f"pending={len(skip_tail.cursor.pending)} bytes, "
            f"dead_letters={skip_tail.dead_letters_count}"
        )
        print()
        print(f"{'rank':>4} {'tick':>4} {'signal':>12} {'weight':>8} {'loss':>8} {'score':>8}")
        for i, entry in enumerate(blamed, start=1):
            print(
                f"{i:>4} {entry.tick:>4} {entry.signal_name:>12} "
                f"{entry.weight:>8.3f} {entry.loss:>8.3f} {entry.score:>8.3f}"
            )

        print()
        print("Reading: partial JSONL stays buffered until the newline arrives.")
        print("With skip_bad_lines=True, malformed JSON is captured as a dead letter.")


if __name__ == "__main__":
    main()
