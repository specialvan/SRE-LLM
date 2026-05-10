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
