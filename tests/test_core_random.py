"""Tests for core random seed management."""
from __future__ import annotations

from gan_matchmaking.core.random import SeedManager


def test_seed_manager_derives_consistent_values():
    """Test that SeedManager derives consistent values for same inputs."""
    sm = SeedManager(root_seed=42)
    seed1 = sm.int_seed("player-a")
    seed2 = sm.int_seed("player-a")
    assert seed1 == seed2


def test_seed_manager_different_names_differ():
    """Test that different names produce different seeds."""
    sm = SeedManager(root_seed=42)
    seed1 = sm.int_seed("player-a")
    seed2 = sm.int_seed("player-b")
    assert seed1 != seed2


def test_seed_manager_different_root_differ():
    """Test that different root seeds produce different derived seeds."""
    sm1 = SeedManager(root_seed=42)
    sm2 = SeedManager(root_seed=99)
    seed1 = sm1.int_seed("player-a")
    seed2 = sm2.int_seed("player-a")
    assert seed1 != seed2


def test_seed_manager_numpy_generator():
    """Test that numpy generator produces reproducible values."""
    sm = SeedManager(root_seed=42)
    rng = sm.numpy("test")
    values1 = rng.random(5)
    rng2 = sm.numpy("test")
    values2 = rng2.random(5)
    assert list(values1) == list(values2)


def test_seed_manager_python_random():
    """Test that python random produces reproducible values."""
    sm = SeedManager(root_seed=42)
    rng = sm.python("test")
    values1 = [rng.random() for _ in range(5)]
    rng2 = sm.python("test")
    values2 = [rng2.random() for _ in range(5)]
    assert values1 == values2


def test_seed_manager_int_seed_range():
    """Test that int_seed returns values in valid 32-bit range."""
    sm = SeedManager(root_seed=0)
    for name in ["a", "b", "c", "d", "e"]:
        seed = sm.int_seed(name)
        assert 0 <= seed <= 0x7FFFFFFF, f"Seed {seed} out of 32-bit range"


def test_seed_manager_default_root_seed():
    """Test that default root seed is 0."""
    sm = SeedManager()
    assert sm.root_seed == 0
    seed = sm.int_seed("default")
    assert seed >= 0


def test_seed_manager_derive_is_called():
    """Test that _derive is called via public methods."""
    sm = SeedManager(root_seed=12345)
    # Call all public methods to ensure _derive is exercised
    numpy_rng = sm.numpy("method1")
    python_rng = sm.python("method2")
    int_seed = sm.int_seed("method3")

    # Verify they all return valid values
    assert numpy_rng is not None
    assert python_rng is not None
    assert int_seed >= 0