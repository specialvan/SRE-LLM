"""``python -m gan_matchmaking.training`` — run both trainers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..persistence import SQLitePipelineStore
from .cox import train_cox_from_store
from .retention import train_retention_from_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gan-matchmaking-train")
    parser.add_argument("--state-db", required=True)
    parser.add_argument("--output-dir", default="training_artifacts")
    parser.add_argument("--what", choices=("cox", "retention", "all"),
                        default="all")
    args = parser.parse_args(argv)

    store = SQLitePipelineStore(Path(args.state_db))
    reports = {}
    try:
        if args.what in ("cox", "all"):
            reports["cox"] = train_cox_from_store(
                store, output_dir=args.output_dir).as_dict()
        if args.what in ("retention", "all"):
            reports["retention"] = train_retention_from_store(
                store, output_dir=args.output_dir).as_dict()
    finally:
        store.close()
    json.dump(reports, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
