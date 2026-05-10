"""Tests for Attention Residuals — §5.1 (core module)."""

from __future__ import annotations

import torch

from attention_residuals import (
    AttentionResidual,
    AttentionResidualConnector,
    AttnResConfig,
    MultiHeadAttentionResidual,
)


def test_weights_sum_to_one():
    cfg = AttnResConfig(d_model=8, num_heads=1)
    mod = AttentionResidual(cfg)
    history = [torch.randn(2, 4, 8) for _ in range(3)]
    x = torch.randn(2, 4, 8)
    _ = mod(history, x)
    w = mod.last_weights()
    assert w is not None
    assert w.size(0) == 4           # 3 history + self
    s = w.sum(dim=0)
    assert torch.allclose(s, torch.ones_like(s), atol=1e-5)


def test_identical_history_produces_identity_output():
    """If every x_k equals x_l, any convex combination equals x_l."""
    cfg = AttnResConfig(d_model=8, num_heads=1)
    mod = AttentionResidual(cfg)
    x = torch.randn(2, 4, 8)
    history = [x.clone() for _ in range(4)]
    y = mod(history, x)
    assert torch.allclose(y, x, atol=1e-5)


def test_no_history_no_self_fallback():
    cfg = AttnResConfig(d_model=8, num_heads=1, include_self=False)
    mod = AttentionResidual(cfg)
    x = torch.randn(2, 4, 8)
    y = mod([], x)
    assert torch.allclose(y, x)


def test_gradient_flows_to_wq():
    cfg = AttnResConfig(d_model=8, num_heads=1)
    mod = AttentionResidual(cfg)
    history = [torch.randn(2, 4, 8) for _ in range(2)]
    x = torch.randn(2, 4, 8, requires_grad=True)
    y = mod(history, x)
    y.sum().backward()
    assert mod.w_q.weight.grad is not None
    assert mod.w_q.weight.grad.abs().sum() > 0


def test_connector_x_plus_f_shape():
    cfg = AttnResConfig(d_model=8, num_heads=1)
    attn = AttentionResidual(cfg)

    class _Sub(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lin = torch.nn.Linear(8, 8)

        def forward(self, x):       # noqa: D401
            return self.lin(x)

    conn = AttentionResidualConnector(_Sub(), attn)
    x = torch.randn(2, 4, 8)
    history = [torch.randn(2, 4, 8)]
    y = conn(history, x)
    assert y.shape == x.shape


def test_multi_head_num_heads_one_is_equivalent_shape():
    """MultiHead with num_heads=1 must still produce matching shapes."""
    cfg = AttnResConfig(d_model=8, num_heads=1)
    mod = MultiHeadAttentionResidual(cfg)
    history = [torch.randn(2, 4, 8) for _ in range(3)]
    x = torch.randn(2, 4, 8)
    y = mod(history, x)
    assert y.shape == x.shape


def test_multi_head_weights_sum_to_one_per_head():
    cfg = AttnResConfig(d_model=12, num_heads=3)
    mod = MultiHeadAttentionResidual(cfg)
    history = [torch.randn(2, 4, 12) for _ in range(2)]
    x = torch.randn(2, 4, 12)
    _ = mod(history, x)
    w = mod.last_weights()
    assert w is not None                    # [K, B, T, H]
    s = w.sum(dim=0)
    assert torch.allclose(s, torch.ones_like(s), atol=1e-5)
