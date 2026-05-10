"""Tests for Hyper-Connections (HC / mHC) — §4."""

from __future__ import annotations

import torch
from torch import nn

from attention_residuals import HyperConnection


def test_hc_single_channel_matches_classic_residual():
    d = 8
    body = nn.Linear(d, d)
    hc = HyperConnection(body, d_model=d, channels=1, groups=1)
    x = torch.randn(2, 4, d)
    # HC expects [..., M, D]; insert the single channel axis.
    x_m = x.unsqueeze(-2)       # [2, 4, 1, 8]
    y = hc(x_m).squeeze(-2)
    # classic residual: y == x + body(x)
    expected = x + body(x)
    assert torch.allclose(y, expected, atol=1e-6)


def test_mhc_block_diagonal_mask():
    d, M, G = 4, 4, 2
    # Use a bias-free module so that a zero channel input stays zero.
    body = nn.Linear(d, d, bias=False)
    hc = HyperConnection(body, d_model=d, channels=M, groups=G)
    # Force A / B to non-trivial values; the forward pass must still be a
    # block-diagonal mixing.
    with torch.no_grad():
        hc.A.data = torch.ones_like(hc.A)
        hc.B.data = torch.ones_like(hc.B)
    x_m = torch.randn(1, 1, M, d)
    y = hc(x_m)
    assert y.shape == x_m.shape
    # With groups=2 and channels=4, channels {0,1} should mix only with
    # {0,1}; verify through a controlled input.
    x_probe = torch.zeros(1, 1, M, d)
    x_probe[..., 0, :] = 1.0       # only channel 0 has mass
    y_probe = hc(x_probe)
    # Channels 0 and 1 get contributions; 2 and 3 should not (cross-group).
    assert torch.all(y_probe[..., 2, :] == 0)
    assert torch.all(y_probe[..., 3, :] == 0)


def test_hc_invalid_groups_raises():
    d = 4
    body = nn.Linear(d, d)
    import pytest
    with pytest.raises(ValueError):
        HyperConnection(body, d_model=d, channels=4, groups=3)
