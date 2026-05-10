"""Dynamic layer-skip gating — §6 开放讨论（第 2 问）.

Formula
-------
    g_l = σ(w_l)                          # w_l is a learnable scalar
    x_{l+1} = g_l * (AttnRes_l + F_l(x_l)) + (1 - g_l) * x_l

At inference time, layers with ``g_l < skip_threshold`` can be short-circuited
entirely to save compute.
"""

from __future__ import annotations

from typing import Optional, Sequence

import torch
from torch import nn, Tensor

from .attn_residual import AttentionResidual


class LayerSkipGate(nn.Module):
    """Wraps a layer's AttnRes + F(x) block with a learnable sigmoid gate.

    Parameters
    ----------
    sublayer : nn.Module
        The per-layer function ``F_l``.
    attn_res : AttentionResidual
        The vertical attention module for this layer.
    init_gate : float
        Initial value of the pre-sigmoid logit. ``init_gate=4.6`` gives
        σ ≈ 0.99, i.e. "skip gate is open by default".
    skip_threshold : float
        Inference-time threshold. Layers with σ(w) < threshold are skipped
        during :meth:`forward` when ``inference_skip`` is True.
    """

    def __init__(
        self,
        sublayer: nn.Module,
        attn_res: AttentionResidual,
        init_gate: float = 4.6,
        skip_threshold: float = 0.1,
    ) -> None:
        super().__init__()
        self.sublayer = sublayer
        self.attn_res = attn_res
        self.logit = nn.Parameter(torch.tensor(float(init_gate)))
        self.skip_threshold = float(skip_threshold)

    @property
    def gate(self) -> Tensor:
        """Sigmoid-activated gate value g_l ∈ (0, 1)."""
        return torch.sigmoid(self.logit)

    def forward(
        self,
        history: Sequence[Tensor],
        x: Tensor,
        *,
        inference_skip: bool = False,
    ) -> Tensor:
        g = self.gate
        if inference_skip and not self.training and g.item() < self.skip_threshold:
            # Hard short-circuit: keep the input verbatim.
            return x
        body = self.attn_res(history, x) + self.sublayer(x)
        return g * body + (1.0 - g) * x
