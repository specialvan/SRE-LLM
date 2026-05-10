"""Unified residual-connection stack — end-to-end assembly.

Supports six interchangeable strategies through :class:`ResidualMode`:

* ``CLASSIC``              — §2 classic residual only.
* ``HYPER``                — §4 Hyper-Connections (M channels).
* ``MANIFOLD_HYPER``       — §4 mHC (grouped HC).
* ``FULL_ATTN_RES``        — §5 Full Attention Residuals.
* ``BLOCK_ATTN_RES``       — §5 Block Attention Residuals.
* ``MULTI_HEAD_ATTN_RES``  — §6 multi-head vertical attention.

Each mode exposes the same ``forward(x)`` signature so higher-level code
can swap strategies for ablation.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

import torch
from torch import nn, Tensor

from .attn_residual import AttentionResidual, AttentionResidualConnector
from .blocks import BlockAttnResStack
from .classic_residual import ClassicResidual
from .hyper_connections import HyperConnection
from .multi_head_vertical import MultiHeadAttentionResidual
from .types import AttnResConfig, BlockConfig, ResidualMode


SublayerFactory = Callable[[int], nn.Module]


def _default_sublayer_factory(d_model: int) -> SublayerFactory:
    """Default F_l: a tiny feed-forward network (Linear → GELU → Linear)."""
    def make(_idx: int) -> nn.Module:
        return nn.Sequential(
            nn.Linear(d_model, d_model * 2),
            nn.GELU(),
            nn.Linear(d_model * 2, d_model),
        )
    return make


class _FullAttnResStack(nn.Module):
    """Stack where every layer uses Attention Residuals over all prior outputs."""

    def __init__(
        self,
        sublayer_factory: SublayerFactory,
        num_layers: int,
        attn_cfg: AttnResConfig,
        multi_head: bool = False,
    ) -> None:
        super().__init__()
        self.num_layers = num_layers
        self.sublayers = nn.ModuleList(sublayer_factory(i) for i in range(num_layers))
        attn_cls = MultiHeadAttentionResidual if multi_head else AttentionResidual
        self.attn_mods = nn.ModuleList(attn_cls(attn_cfg) for _ in range(num_layers))
        self._weights_trace: List[Tensor] = []

    def forward(self, x: Tensor) -> Tensor:
        self._weights_trace = []
        history: List[Tensor] = []
        current = x
        for sub, attn in zip(self.sublayers, self.attn_mods):
            ar = attn(history, current)
            current = ar + sub(current)
            w = attn.last_weights()
            if w is not None:
                self._weights_trace.append(w)
            history.append(current)
        return current

    def trace(self) -> List[Tensor]:
        return list(self._weights_trace)


class _ClassicStack(nn.Module):
    """Plain residual stack — the §2 baseline."""

    def __init__(self, sublayer_factory: SublayerFactory, num_layers: int) -> None:
        super().__init__()
        self.layers = nn.ModuleList(
            ClassicResidual(sublayer_factory(i)) for i in range(num_layers)
        )

    def forward(self, x: Tensor) -> Tensor:
        for layer in self.layers:
            x = layer(x)
        return x


class _HyperStack(nn.Module):
    """Hyper-Connections stack (HC / mHC) — the §4 baseline."""

    def __init__(
        self,
        sublayer_factory: SublayerFactory,
        num_layers: int,
        d_model: int,
        channels: int = 4,
        groups: int = 1,
    ) -> None:
        super().__init__()
        self.channels = channels
        self.layers = nn.ModuleList(
            HyperConnection(
                sublayer_factory(i),
                d_model=d_model,
                channels=channels,
                groups=groups,
            )
            for i in range(num_layers)
        )

    def forward(self, x: Tensor) -> Tensor:
        # Broadcast the single input over M parallel channels: [..., D] -> [..., M, D]
        x_m = x.unsqueeze(-2).expand(*x.shape[:-1], self.channels, x.shape[-1])
        for layer in self.layers:
            x_m = layer(x_m)
        # Collapse channels by mean (paper leaves this choice open; mean is
        # a neutral default that doesn't alter scale).
        return x_m.mean(dim=-2)


class ResidualStack(nn.Module):
    """Front-end that assembles one of the residual strategies above.

    Parameters
    ----------
    d_model : int
        Feature dimension.
    mode : ResidualMode
        Connection strategy to use.
    num_layers : int
        Only used for CLASSIC / HYPER / FULL_ATTN_RES / MULTI_HEAD_ATTN_RES.
    block_cfg : BlockConfig, optional
        Required when mode == BLOCK_ATTN_RES.
    attn_cfg : AttnResConfig, optional
        Config for vertical attention modules.
    sublayer_factory : Callable, optional
        Override for F_l. Defaults to a small 2-layer FFN.
    hyper_channels : int
        M for HYPER / MANIFOLD_HYPER.
    hyper_groups : int
        Groups for MANIFOLD_HYPER (must divide ``hyper_channels``).
    """

    def __init__(
        self,
        d_model: int = 64,
        mode: ResidualMode = ResidualMode.FULL_ATTN_RES,
        num_layers: int = 6,
        block_cfg: Optional[BlockConfig] = None,
        attn_cfg: Optional[AttnResConfig] = None,
        sublayer_factory: Optional[SublayerFactory] = None,
        hyper_channels: int = 4,
        hyper_groups: int = 1,
    ) -> None:
        super().__init__()
        self.mode = ResidualMode(mode)
        self.d_model = d_model
        factory = sublayer_factory or _default_sublayer_factory(d_model)
        attn_cfg = attn_cfg or AttnResConfig(d_model=d_model)

        if self.mode is ResidualMode.CLASSIC:
            self.impl: nn.Module = _ClassicStack(factory, num_layers)
        elif self.mode is ResidualMode.HYPER:
            self.impl = _HyperStack(factory, num_layers, d_model,
                                    channels=hyper_channels, groups=1)
        elif self.mode is ResidualMode.MANIFOLD_HYPER:
            self.impl = _HyperStack(factory, num_layers, d_model,
                                    channels=hyper_channels,
                                    groups=max(1, hyper_groups))
        elif self.mode is ResidualMode.FULL_ATTN_RES:
            self.impl = _FullAttnResStack(factory, num_layers, attn_cfg,
                                          multi_head=False)
        elif self.mode is ResidualMode.MULTI_HEAD_ATTN_RES:
            self.impl = _FullAttnResStack(factory, num_layers, attn_cfg,
                                          multi_head=True)
        elif self.mode is ResidualMode.BLOCK_ATTN_RES:
            if block_cfg is None:
                block_cfg = BlockConfig()
            self.impl = BlockAttnResStack(factory, attn_cfg, block_cfg)
        else:  # pragma: no cover
            raise ValueError(f"Unknown mode: {self.mode}")

    # ------------------------------------------------------------------ forward
    def forward(self, x: Tensor) -> Tensor:
        return self.impl(x)

    # ------------------------------------------------------------------ trace
    def trace(self) -> List[Tensor]:
        """Return attention weights when available; empty list otherwise."""
        if hasattr(self.impl, "trace"):
            return self.impl.trace()  # type: ignore[no-any-return]
        return []
