"""``python -m gan_matchmaking.service`` entry point."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

from ..core import GanError, load_config
from ..persistence import SQLitePipelineStore
from ..sre.leases import FileLease, LeaseRefreshLoop
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
    parser.add_argument("--lease-file",
                        default=os.environ.get("GAN_LEASE_FILE"),
                        help="optional local lease file guarding one writable state db")
    parser.add_argument("--lease-owner",
                        default=os.environ.get("GAN_LEASE_OWNER")
                        or f"{socket.gethostname()}:{os.getpid()}")
    parser.add_argument("--lease-ttl-seconds", type=float,
                        default=float(os.environ.get("GAN_LEASE_TTL_SECONDS", "60")))
    args = parser.parse_args(argv)

    store = None
    try:
        cfg = load_config(args.config) if args.config else load_config()
        store = SQLitePipelineStore(Path(args.state_db))
        app = build_app(config=cfg, store=store)
        if args.lease_file:
            lease = FileLease(
                Path(args.lease_file),
                owner=args.lease_owner,
                ttl_seconds=args.lease_ttl_seconds,
            )
            app.bind_lease_metadata(
                path=str(args.lease_file),
                owner=str(args.lease_owner),
            )
            with LeaseRefreshLoop(lease, on_failure=app.mark_lease_unhealthy):
                run_wsgi(app, host=args.host, port=args.port)
        else:
            run_wsgi(app, host=args.host, port=args.port)
        return 0
    except GanError as exc:
        json.dump({"error": exc.to_dict()}, sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
