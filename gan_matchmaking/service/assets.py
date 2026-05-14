"""Allowlisted static assets for the stdlib dashboard."""
from __future__ import annotations

from importlib import resources
from typing import Dict, Tuple


ASSET_CONTENT_TYPES: Dict[str, str] = {
    "dashboard.html": "text/html; charset=utf-8",
    "dashboard.css": "text/css; charset=utf-8",
    "dashboard.js": "application/javascript; charset=utf-8",
}


def load_dashboard_asset(name: str) -> Tuple[bytes, str] | None:
    """Return allowlisted dashboard asset bytes and content type."""
    content_type = ASSET_CONTENT_TYPES.get(name)
    if content_type is None:
        return None
    asset = resources.files(__package__).joinpath("static", name)
    return asset.read_bytes(), content_type
