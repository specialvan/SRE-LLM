"""Tests for Block Attention Residuals — §5."""

from __future__ import annotations

import torch
from torch import nn

from attention_residuals import (
    AttnResConfig,
    BlockAttnResStack,
    BlockConfig,
)


def _sublayer_factory(d: int):
    def make(_i: int) -> nn.Module:
        return nn.Linear(d, d)
    return make


def test_num_blocks_one_is_classic_residual_stack():
    """num_blocks == 1 → no between-block attention is exercised."""
    d = 8
    stack = BlockAttnResStack(
        _sublayer_factory(d),
        attn_cfg=AttnResConfig(d_model=d),
        block_cfg=BlockConfig(num_blocks=1, layers_per_block=3,
                              inner_residual=False),
    )
    x = torch.randn(2, 4, d)
    y = stack(x)
    assert y.shape == x.shape
    assert stack.trace() == []      # no block-level attention was used


def test_layers_per_block_one_is_full_attention_residuals():
    """layers_per_block == 1 → every layer attends to block boundaries."""
    d = 8
    L = 4
    stack = BlockAttnResStack(
        _sublayer_factory(d),
        attn_cfg=AttnResConfig(d_model=d),
        block_cfg=BlockConfig(num_blocks=L, layers_per_block=1,
                              inner_residual=False),
    )
    x = torch.randn(2, 4, d)
    y = stack(x)
    weights = stack.trace()
    # Between-block attention runs L - 1 times.
    assert len(weights) == L - 1
    for w in weights:
        s = w.sum(dim=0)
        assert torch.allclose(s, torch.ones_like(s), atol=1e-5)
    assert y.shape == x.shape


def test_backward_updates_block_attention_params():
    d = 8
    stack = BlockAttnResStack(
        _sublayer_factory(d),
        attn_cfg=AttnResConfig(d_model=d),
        block_cfg=BlockConfig(num_blocks=3, layers_per_block=2,
                              inner_residual=False),
    )
    x = torch.randn(2, 4, d)
    y = stack(x)
    y.pow(2).mean().backward()
    # At boundary b=1 only a single prior block is in history, so softmax
    # degenerates to a constant and W_Q carries no gradient information.
    # At boundary b=2 there are two prior blocks, so W_Q does receive grad.
    wq = stack.block_attn[1].w_q.weight
    assert wq.grad is not None and wq.grad.abs().sum() > 0
