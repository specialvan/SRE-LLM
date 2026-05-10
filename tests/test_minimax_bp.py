"""Tests for Minimax / zero-sum Nash solver (§9)."""
from __future__ import annotations

import numpy as np

from gan_matchmaking import zero_sum_nash


def test_rock_paper_scissors_is_uniform():
    # Row player: 0=rock, 1=paper, 2=scissors. Payoffs in {-1,0,1}.
    U = np.array([
        [ 0, -1,  1],
        [ 1,  0, -1],
        [-1,  1,  0],
    ], dtype=float)
    x, y, v = zero_sum_nash(U)
    assert np.allclose(x, [1/3, 1/3, 1/3], atol=1e-5)
    assert np.allclose(y, [1/3, 1/3, 1/3], atol=1e-5)
    assert abs(v) < 1e-6


def test_dominant_row_strategy():
    # Row 0 dominates row 1 (always >= with strict >).
    U = np.array([
        [2.0, 3.0],
        [1.0, 2.0],
    ])
    x, y, v = zero_sum_nash(U)
    assert x[0] > 0.99
    assert abs(v - 2.0) < 1e-6


def test_minimax_equality():
    rng = np.random.default_rng(0)
    U = rng.normal(size=(4, 5))
    x, y, v = zero_sum_nash(U)
    # Row player guarantee: min over y* of x*^T U y* == v.
    row_worst = float(np.min(x @ U))
    col_worst = float(np.max(U @ y))
    assert abs(row_worst - v) < 1e-4
    assert abs(col_worst - v) < 1e-4
