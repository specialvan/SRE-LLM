"""Hyper-Connections (HC / mHC) — §4 演进探索.

Reference formula (simplified)::

    X^{(m)}_{l+1} = Σ_n A_{m,n} · X^{(n)}_l + F_l( Σ_n B_{m,n} · X^{(n)}_l )

where {X^{(m)}} are M parallel residual channels and A, B ∈ R^{M x M}
are learnable mixing matrices.

Note (from §4):
    HC / mHC do not introduce cross-layer mixing — "历史学习成果作为一个不
    可分割的整体看待". This module is kept here as a baseline so that the
    Attention-Residuals advantage can be measured empirically.
"""

from __future__ import annotations

from typing import Optional

import torch
from torch import nn, Tensor


class HyperConnection(nn.Module):
    """Multi-channel residual connection with learnable mixing.

    Parameters
    ----------
    sublayer : nn.Module
        Function ``F`` applied to the mixed-input channel combination.
    d_model : int
        Feature dimension (only used to expose it on the module).
    channels : int
        Number of parallel residual channels M (M=1 → classic residual).
    groups : int
        If ``groups > 1``, both A and B are block-diagonal — this yields
        the mHC variant (grouped mixing). Must divide ``channels`` evenly.
    """

    def __init__(
        self,
        sublayer: nn.Module,
        d_model: int = 64,
        channels: int = 4,
        groups: int = 1,
    ) -> None:
        super().__init__()
        if channels < 1:
            raise ValueError("channels must be >= 1")
        if groups < 1 or channels % groups != 0:
            raise ValueError("groups must divide channels evenly")
        self.sublayer = sublayer
        self.channels = channels
        self.groups = groups
        self.d_model = d_model

        # Identity init keeps behaviour close to a plain residual at step 0.
        eye = torch.eye(channels)
        self.A = nn.Parameter(eye.clone())
        self.B = nn.Parameter(eye.clone())

    # --- helpers ---------------------------------------------------------
    def _masked_mix_matrix(self, M: Tensor) -> Tensor:
        """Project a full mixing matrix onto its block-diagonal structure.

        Matches the mHC idea: channels inside the same group may mix, but
        cross-group mixing is zeroed out.
        """
        if self.groups == 1:
            return M
        per = self.channels // self.groups
        mask = torch.block_diag(*[torch.ones(per, per) for _ in range(self.groups)])
        mask = mask.to(M.device, dtype=M.dtype)
        return M * mask

    # --- forward ---------------------------------------------------------
    def forward(self, x_channels: Tensor) -> Tensor:
        """Run one HC / mHC step.

        Parameters
        ----------
        x_channels : Tensor, shape ``[..., M, D]``
            Stack of M residual channels. The leading dims (batch, tokens)
            are preserved. M must match ``self.channels``.

        Returns
        -------
        Tensor, shape ``[..., M, D]``
            Updated stack of channels.
        """
        if x_channels.size(-2) != self.channels:
            raise ValueError(
                f"x_channels last-but-one dim ({x_channels.size(-2)}) "
                f"!= channels ({self.channels})"
            )
        A = self._masked_mix_matrix(self.A)
        B = self._masked_mix_matrix(self.B)

        # Mix channels: [..., M, D] = einsum("ij, ...jd -> ...id", A, x)
        mixed_identity = torch.einsum("mn, ...nd -> ...md", A, x_channels)
        mixed_input = torch.einsum("mn, ...nd -> ...md", B, x_channels)

        # Apply F to each channel independently so shapes stay consistent.
        fx = self.sublayer(mixed_input)
        return mixed_identity + fx
