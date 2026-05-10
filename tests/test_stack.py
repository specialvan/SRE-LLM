"""Tests for the unified ResidualStack — end-to-end assembly."""

from __future__ import annotations

import torch

from attention_residuals import (
    AttnResConfig,
    BlockConfig,
    DecoupledTransformerLayer,
    ResidualMode,
    ResidualStack,
)


def _run(mode: ResidualMode, **extra):
    d = 16
    stack = ResidualStack(
        d_model=d, mode=mode, num_layers=4,
        attn_cfg=AttnResConfig(d_model=d,
                               num_heads=4 if mode is ResidualMode.MULTI_HEAD_ATTN_RES else 1),
        **extra,
    )
    x = torch.randn(2, 8, d)
    y = stack(x)
    assert y.shape == x.shape
    y.pow(2).mean().backward()


def test_stack_classic():
    _run(ResidualMode.CLASSIC)


def test_stack_hyper():
    _run(ResidualMode.HYPER, hyper_channels=4, hyper_groups=1)


def test_stack_manifold_hyper():
    _run(ResidualMode.MANIFOLD_HYPER, hyper_channels=4, hyper_groups=2)


def test_stack_full_attn_res():
    _run(ResidualMode.FULL_ATTN_RES)


def test_stack_multi_head_attn_res():
    _run(ResidualMode.MULTI_HEAD_ATTN_RES)


def test_stack_block_attn_res():
    d = 16
    stack = ResidualStack(
        d_model=d,
        mode=ResidualMode.BLOCK_ATTN_RES,
        attn_cfg=AttnResConfig(d_model=d),
        block_cfg=BlockConfig(num_blocks=3, layers_per_block=2,
                              inner_residual=False),
    )
    x = torch.randn(2, 8, d)
    y = stack(x)
    assert y.shape == x.shape


def test_decoupled_layer_gradients_reach_both_paths():
    """§5.2: horizontal MHA params and vertical AttnRes W_Q both receive grad."""
    d = 16
    layer = DecoupledTransformerLayer(d_model=d, num_heads=4)
    x = torch.randn(2, 8, d)
    history = [torch.randn(2, 8, d) for _ in range(2)]
    y = layer(history, x)
    y.pow(2).mean().backward()

    # Horizontal path gradient.
    assert layer.mha.in_proj_weight.grad is not None
    assert layer.mha.in_proj_weight.grad.abs().sum() > 0
    # Vertical path gradient.
    assert layer.attn_res.w_q.weight.grad is not None
    assert layer.attn_res.w_q.weight.grad.abs().sum() > 0
