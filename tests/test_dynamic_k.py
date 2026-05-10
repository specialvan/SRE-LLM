"""Tests for Dynamic K-Factor (§3)."""
from __future__ import annotations

from gan_matchmaking import DynamicK


def test_k_monotonic_decrease_on_win_streak():
    dk = DynamicK(k_max=32, k_min=4, lam=0.7, theta=5)
    ks = [dk.k(s) for s in range(0, 20)]
    for a, b in zip(ks, ks[1:]):
        assert a >= b - 1e-9


def test_win_on_long_streak_earns_fewer_points():
    dk = DynamicK()
    delta_short = dk.delta_rating(expected=0.5, actual=1.0, streak=0)
    delta_long = dk.delta_rating(expected=0.5, actual=1.0, streak=15)
    assert delta_short > delta_long
    assert delta_long > 0


def test_loss_on_long_streak_punished_softer_only_when_penalize_wins_false():
    # When penalize_wins=True (default), K decays → loss cost also shrinks.
    # That's OK — the article's "loss hurts more" effect is captured by Handicap,
    # not by K itself. This test pins the mathematical behaviour.
    dk = DynamicK()
    loss_short = dk.delta_rating(expected=0.5, actual=0.0, streak=0)
    loss_long = dk.delta_rating(expected=0.5, actual=0.0, streak=15)
    assert loss_short < 0 and loss_long < 0
    assert abs(loss_long) < abs(loss_short)
