"""Command-line entry point.

Usage::

    python -m gan_matchmaking.cli decide --input context.json [--config cfg.json]
    python -m gan_matchmaking.cli metrics [--config cfg.json]
    python -m gan_matchmaking.cli export-replay --state-db state.sqlite --correlation-id dec-1

The CLI exists for code review and light integration (airflow / cron).
Anything complex belongs in :class:`SelfIterationPipeline` directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .core import AppConfig, GanError, MetricsRegistry, load_config
from .sre import (
    ReleaseCandidate,
    ReleaseContext,
    SelfIterationPipeline,
    Service,
)
from .sre.replay import export_replay_fixture


def _ctx_from_dict(payload: Dict[str, Any]) -> ReleaseContext:
    """Reconstruct a :class:`ReleaseContext` from JSON-friendly input."""
    svc_raw = payload["service"]
    service = Service(
        id=svc_raw["id"],
        mu=float(svc_raw.get("mu", 0.99)),
        sigma=float(svc_raw.get("sigma", 0.02)),
        win_streak=int(svc_raw.get("win_streak", 0)),
        loss_streak=int(svc_raw.get("loss_streak", 0)),
        total_releases=int(svc_raw.get("total_releases", 0)),
        tier=str(svc_raw.get("tier", "standard")),
    )
    candidates = [
        ReleaseCandidate(
            id=c["id"],
            service_id=service.id,
            strategy=c["strategy"],
            canary_fraction=float(c.get("canary_fraction", 0.0)),
            rollback_budget_seconds=float(c.get("rollback_budget_seconds", 300.0)),
            expected_success=float(c.get("expected_success", 0.99)),
            notes=c.get("notes", ""),
        )
        for c in payload["candidates"]
    ]
    return ReleaseContext(
        service=service,
        candidates=candidates,
        telemetry=payload.get("telemetry"),
        dependencies=list(payload.get("dependencies", [])),
        error_budget_remaining=float(payload.get("error_budget_remaining", 1.0)),
        freeze_window=bool(payload.get("freeze_window", False)),
        correlation_id=payload.get("correlation_id"),
    )


def _cmd_decide(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    ctx = _ctx_from_dict(payload)
    pipeline = SelfIterationPipeline(config=cfg, metrics=MetricsRegistry())
    decision = pipeline.decide(ctx)
    output = decision.to_dict()
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_metrics(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    # Running a single bogus decide just to make the registry non-empty.
    registry = MetricsRegistry()
    SelfIterationPipeline(config=cfg, metrics=registry)
    sys.stdout.write(registry.export_prometheus())
    return 0


def _cmd_export_replay(args: argparse.Namespace) -> int:
    config = None
    if args.config is not None:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    payload = export_replay_fixture(
        args.state_db,
        args.correlation_id,
        output=args.output,
        config=config,
        name=args.name,
        allow_fitted_artifacts=args.allow_fitted_artifacts,
    )
    if args.output:
        json.dump(
            {"status": "exported", "output": args.output, "name": payload["name"]},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gan-matchmaking",
        description="SRE self-iteration decider (the nine-mechanism gan pipeline).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_decide = sub.add_parser("decide", help="emit a Decision for a ReleaseContext")
    p_decide.add_argument("--input", required=True,
                          help="path to JSON with {service, candidates, ...}")
    p_decide.add_argument("--config", default=None,
                          help="optional path to AppConfig JSON")
    p_decide.set_defaults(func=_cmd_decide)

    p_metrics = sub.add_parser("metrics", help="print the Prometheus exposition text")
    p_metrics.add_argument("--config", default=None,
                           help="optional path to AppConfig JSON")
    p_metrics.set_defaults(func=_cmd_metrics)

    p_export = sub.add_parser(
        "export-replay",
        help="export one SQLite decision audit row as a replay fixture",
    )
    p_export.add_argument("--state-db", required=True,
                          help="path to the SQLite state db")
    p_export.add_argument("--correlation-id", required=True,
                          help="decision correlation_id to export")
    p_export.add_argument("--output", default=None,
                          help="optional output JSON path; stdout if omitted")
    p_export.add_argument("--config", default=None,
                          help="optional AppConfig JSON to embed in the fixture")
    p_export.add_argument("--name", default=None,
                          help="optional fixture name; defaults to correlation_id")
    p_export.add_argument(
        "--allow-fitted-artifacts",
        action="store_true",
        help="export non-bootstrap decisions that require a matching artifact bundle",
    )
    p_export.set_defaults(func=_cmd_export_replay)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GanError as exc:
        json.dump({"error": exc.to_dict()}, sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        return 2
    except Exception as exc:  # pragma: no cover — last-resort safety net.
        json.dump({"error": {"code": "gan.cli.unhandled",
                             "message": str(exc),
                             "type": type(exc).__name__}},
                  sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
