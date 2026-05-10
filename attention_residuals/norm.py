"""Pre-Norm / Post-Norm wrappers around a residual sublayer — §3.

Post-Norm:   x_{l+1} = LN(x_l + F_l(x_l))
Pre-Norm:    x_{l+1} = x_l + F_l(LN(x_l))
None:        x_{l+1} = x_l + F_l(x_l)       (falls back to ClassicResidual)

The article argues that both Post-Norm and Pre-Norm carry trade-offs — this
module lets you A/B them under an identical sublayer and input.
"""

from __future__ import annotations

import torch
from torch import nn, Tensor

from .types import NormStyle


class NormWrapper(nn.Module):
    """Apply a residual connection with a selectable LayerNorm placement.

    Parameters
    ----------
    sublayer : nn.Module
        The function ``F`` in the residual formula.
    style : NormStyle
        Where to place the LayerNorm.
    d_model : int
        Feature dimension used by the ``nn.LayerNorm`` instance.
    eps : float
        LayerNorm epsilon.
    """

    def __init__(
        self,
        sublayer: nn.Module,
        style: NormStyle = NormStyle.PRE_NORM,
        d_model: int = 64,
        eps: float = 1e-5,
    ) -> None:
        super().__init__()
        self.sublayer = sublayer
        self.style = NormStyle(style)
        # Always construct LN so the wrapper is serializable, but only
        # consult it for PRE_NORM / POST_NORM.
        self.norm = nn.LayerNorm(d_model, eps=eps)

    def forward(self, x: Tensor) -> Tensor:
        if self.style is NormStyle.POST_NORM:
            return self.norm(x + self.sublayer(x))
        if self.style is NormStyle.PRE_NORM:
            return x + self.sublayer(self.norm(x))
        # NONE — classic residual.
        return x + self.sublayer(x)
