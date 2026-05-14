"""Tests for Handicap Elo (§6)."""
from __future__ import annotations

from gan_matchmaking import HandicapElo


def test_expected_win_no_penalty_is_standard_elo():
    e = HandicapElo.expected_win(1500, 1500, penalty=0.0)
    assert abs(e - 0.5) < 1e-9


def test_penalty_pulls_expected_win_toward_half():
    h = HandicapElo(max_penalty=200.0, tau=3.0)
    # Player A is 200 points ahead — baseline ~76% win rate.
    base = HandicapElo.expected_win(1700, 1500, penalty=0.0)
    assert base > 0.7
    pen = h.penalty(win_streak=10, loss_streak=0)
    adj = HandicapElo.expected_win(1700, 1500, penalty=pen)
    assert adj < base
    assert 0.45 < adj < 0.7


def test_penalty_zero_when_streaks_equal():
    h = HandicapElo()
    pen = h.penalty(win_streak=5, loss_streak=5)
    assert abs(pen) < 1e-9


def test_loss_streak_produces_negative_penalty():
    h = HandicapElo()
    pen = h.penalty(win_streak=0, loss_streak=8)
    assert pen < 0


def test_update_static_method():
    """Test HandicapElo.update updates ratings correctly."""
    # Perfect win for A
    r_a2, r_b2 = HandicapElo.update(1500, 1500, score_a=1.0, k=32.0, penalty=0.0)
    assert r_a2 > 1500
    assert r_b2 < 1500
    # Perfect loss for A
    r_a2, r_b2 = HandicapElo.update(1500, 1500, score_a=0.0, k=32.0, penalty=0.0)
    assert r_a2 < 1500
    assert r_b2 > 1500
    # Draw
    r_a2, r_b2 = HandicapElo.update(1500, 1500, score_a=0.5, k=32.0, penalty=0.0)
    assert abs(r_a2 - 1500) < 1e-9
    assert abs(r_b2 - 1500) < 1e-9


def test_update_with_penalty():
    """Test HandicapElo.update with non-zero penalty."""
    # Penalty affects the expected win calculation
    r_a2, r_b2 = HandicapElo.update(1500, 1500, score_a=1.0, k=32.0, penalty=100.0)
    # With penalty, A's expected win is lower, so gain is larger
    assert r_a2 > 1500


def test_update_with_custom_k():
    """Test HandicapElo.update with different K factors."""
    r_a2_standard, r_b2_standard = HandicapElo.update(1500, 1500, score_a=1.0, k=32.0)
    r_a2_low, r_b2_low = HandicapElo.update(1500, 1500, score_a=1.0, k=10.0)
    # Lower K means smaller rating changes
    assert abs(r_a2_low - 1500) < abs(r_a2_standard - 1500)
