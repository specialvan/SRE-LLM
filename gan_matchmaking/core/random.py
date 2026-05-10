"""Deterministic seed management.

Every module that needs randomness (GNN weight init, EOMM ε-exploration,
synthetic benchmarks) asks :class:`SeedManager` for a named generator. Given
the same top-level seed the results are reproducible end-to-end — a hard
requirement for SRE decision auditing.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

import numpy as np


@dataclass
class SeedManager:
    """Generate named, deterministic generators from one root seed."""

    root_seed: int = 0

    def _derive(self, name: str) -> int:
        """Derive a stable 64-bit integer from the (root_seed, name) pair."""
        h = hashlib.sha256(f"{self.root_seed}::{name}".encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big", signed=False) & ((1 << 64) - 1)

    def numpy(self, name: str) -> np.random.Generator:
        return np.random.default_rng(self._derive(name))

    def python(self, name: str) -> random.Random:
        return random.Random(self._derive(name))

    def int_seed(self, name: str) -> int:
        # 32-bit seed suitable for tf/torch/scikit helpers.
        return self._derive(name) & 0x7FFFFFFF
