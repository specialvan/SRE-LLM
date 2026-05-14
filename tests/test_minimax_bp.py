"""Tests for Minimax / zero-sum Nash solver (§9)."""
from __future__ import annotations

import numpy as np
import pytest

from gan_matchmaking import zero_sum_nash
from gan_matchmaking.minimax_bp import BPSession


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


def test_zero_sum_nash_with_negative_payoffs():
    """Test that negative payoffs are shifted correctly."""
    U = np.array([
        [-3.0, -1.0],
        [-2.0, -4.0],
    ])
    x, y, v = zero_sum_nash(U)
    # After shift, should still find valid equilibrium
    assert abs(x[0] + x[1] - 1.0) < 1e-6
    assert abs(y[0] + y[1] - 1.0) < 1e-6
    # Nash value should be between min and max of original matrix
    assert U.min() <= v <= U.max()


def test_zero_sum_nash_single_row():
    """Test 1xn game."""
    U = np.array([[1.0, 2.0, 3.0]])
    x, y, v = zero_sum_nash(U)
    assert x[0] == 1.0  # Only one strategy
    assert abs(v - 1.0) < 1e-4  # Single element value


def test_zero_sum_nash_single_col():
    """Test nx1 game."""
    U = np.array([[1.0], [2.0], [3.0]])
    x, y, v = zero_sum_nash(U)
    assert y[0] == 1.0  # Only one strategy
    assert abs(v - 3.0) < 1e-4  # Row player max over the single column


def test_zero_sum_nash_mixed_strategy():
    """Test a game requiring a mixed strategy."""
    # Matching pennies variant
    U = np.array([
        [1.0, -1.0],
        [-1.0, 1.0],
    ])
    x, y, v = zero_sum_nash(U)
    # Both should be 50/50 at equilibrium
    assert np.allclose(x, [0.5, 0.5], atol=1e-5)
    assert np.allclose(y, [0.5, 0.5], atol=1e-5)
    assert abs(v) < 1e-6


def test_bp_session_nash_step():
    """Test BPSession.nash_step returns valid equilibrium."""
    def payoff(i: int, j: int) -> float:
        return 1.0 if i == j else -1.0

    session = BPSession(payoff_fn=payoff, pool=["a", "b", "c"])
    x, y, v = session.nash_step()

    assert len(x) == 3
    assert len(y) == 3
    assert abs(x.sum() - 1.0) < 1e-6
    assert abs(y.sum() - 1.0) < 1e-6
    assert all(0 <= xi <= 1 for xi in x)
    assert all(0 <= yi <= 1 for yi in y)


def test_bp_session_empty_pool_raises():
    """Test BPSession raises on empty pool."""
    session = BPSession(payoff_fn=lambda i, j: 0.0, pool=[])
    with pytest.raises(RuntimeError, match="pool is empty"):
        session.nash_step()


def test_bp_session_apply_choice():
    """Test BPSession.apply_choice removes items from pool."""
    def payoff(i: int, j: int) -> float:
        return float(i - j)

    session = BPSession(payoff_fn=payoff, pool=["a", "b", "c", "d"])
    assert len(session.pool) == 4

    session.apply_choice("pick", 0, 2)  # Remove "a" and "c"
    assert len(session.pool) == 2
    assert session.pool == ["b", "d"]
    assert session.history == [("pick", 0, 2)]


def test_bp_session_apply_choice_out_of_bounds():
    """Test BPSession.apply_choice handles out of bounds gracefully."""
    def payoff(i: int, j: int) -> float:
        return 0.0

    session = BPSession(payoff_fn=payoff, pool=["a", "b"])
    session.apply_choice("ban", 5, 10)  # Out of bounds
    # Should not crash, just ignore invalid indices
    assert len(session.pool) == 2
    assert session.history == [("ban", 5, 10)]


def test_bp_session_multiple_choices():
    """Test BPSession through multiple rounds."""
    def payoff(i: int, j: int) -> float:
        return 1.0 if i < j else (-1.0 if i > j else 0.0)

    session = BPSession(payoff_fn=payoff, pool=["p1", "p2", "p3"])

    # Round 1
    x1, _, _ = session.nash_step()
    assert len(x1) == 3

    session.apply_choice("pick", 0, 1)
    assert len(session.pool) == 1

    # Round 2 (only 1 left)
    x2, _, v2 = session.nash_step()
    assert len(x2) == 1
    assert x2[0] == 1.0


def test_bp_session_payoff_matrix():
    """Test BPSession._payoff_matrix computes correct matrix."""
    def payoff(i: int, j: int) -> float:
        return float(i * 2 + j)

    session = BPSession(payoff_fn=payoff, pool=["a", "b"])
    U = session._payoff_matrix()

    expected = np.array([
        [0.0, 1.0],  # i=0: 0*2+j
        [2.0, 3.0],   # i=1: 1*2+j
    ], dtype=float)
    assert np.array_equal(U, expected)


def test_zero_sum_nash_identical_rows():
    """Test game where all rows have same payoff."""
    U = np.array([
        [1.0, 1.0],
        [1.0, 1.0],
    ])
    x, y, v = zero_sum_nash(U)
    # Any strategy is optimal
    assert abs(x.sum() - 1.0) < 1e-6
    assert abs(v - 1.0) < 1e-4


def test_zero_sum_nash_degenerate_zero():
    """Test zero matrix game."""
    U = np.zeros((3, 3))
    x, y, v = zero_sum_nash(U)
    assert abs(v) < 1e-6
