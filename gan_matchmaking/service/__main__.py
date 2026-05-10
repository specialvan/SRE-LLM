"""``python -m gan_matchmaking.service`` entry point."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..core import load_config
from ..persistence import SQLitePipelineStore
from .app import build_app, run_wsgi


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gan-matchmaking-http",
                                     description="Run the SRE decision HTTP server.")
    parser.add_argument("--host", default=os.environ.get("GAN_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("GAN_PORT", "8080")))
    parser.add_argument("--config", default=os.environ.get("GAN_CONFIG"))
    parser.add_argument("--state-db",
                        default=os.environ.get("GAN_STATE_DB", "state.sqlite"))
    args = parser.parse_args(argv)

    cfg = load_config(args.config) if args.config else load_config()
    store = SQLitePipelineStore(Path(args.state_db))
    app = build_app(config=cfg, store=store)
    run_wsgi(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
