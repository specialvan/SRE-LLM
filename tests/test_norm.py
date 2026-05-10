"""Tests for classic residual and Pre/Post-Norm wrappers — §2 / §3."""

from __future__ import annotations

import torch
from torch import nn

from attention_residuals import ClassicResidual, NormWrapper, NormStyle


class _Zero(nn.Module):
    def forward(self, x):                # noqa: D401
        return torch.zeros_like(x)


def test_classic_residual_identity_when_F_is_zero():
    model = ClassicResidual(_Zero())
    x = torch.randn(2, 4, 8)
    y = model(x)
    assert torch.allclose(y, x, atol=1e-6)


def test_norm_wrapper_shapes():
    d = 8
    body = nn.Linear(d, d)
    x = torch.randn(2, 4, d)
    for style in (NormStyle.NONE, NormStyle.PRE_NORM, NormStyle.POST_NORM):
        m = NormWrapper(body, style=style, d_model=d)
        y = m(x)
        assert y.shape == x.shape


def test_norm_none_matches_classic():
    d = 8
    body = nn.Linear(d, d)
    x = torch.randn(3, 5, d)

    torch.manual_seed(0)
    body.weight.data = body.weight.data.clone()

    a = NormWrapper(body, style=NormStyle.NONE, d_model=d)(x)
    b = ClassicResidual(body)(x)
    assert torch.allclose(a, b, atol=1e-6)
