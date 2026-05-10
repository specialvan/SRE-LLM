"""Classic residual connection — §2.

    x_{l+1} = x_l + F_l(x_l)

This is the baseline against which Attention Residuals are compared.
"""

from __future__ import annotations

from typing import Callable

import torch
from torch import nn, Tensor


class ClassicResidual(nn.Module):
    """Wraps a sublayer ``F`` with an additive identity shortcut.

    Parameters
    ----------
    sublayer : nn.Module
        Any module whose input and output share the same trailing dims.
    drop_path : float
        Probability of replacing ``F(x)`` with 0 during training
        (stochastic depth). Default 0 keeps the plain residual.
    """

    def __init__(self, sublayer: nn.Module, drop_path: float = 0.0) -> None:
        super().__init__()
        self.sublayer = sublayer
        self.drop_path = float(drop_path)

    def forward(self, x: Tensor) -> Tensor:                    # noqa: D401
        fx = self.sublayer(x)
        if self.training and self.drop_path > 0.0:
            # Per-sample bernoulli drop (stochastic depth).
            mask = torch.rand(x.size(0), device=x.device) > self.drop_path
            shape = [x.size(0)] + [1] * (x.dim() - 1)
            fx = fx * mask.view(shape).to(fx.dtype)
        return x + fx
