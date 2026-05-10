"""Common data types and configs shared across the package.

Article reference:
    §5.1 / §5.3 — 默认"纯粹配置"中唯一新增的参数是每层的 Query 矩阵 W_Q。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NormStyle(str, Enum):
    """Placement of LayerNorm around a residual sublayer (§3)."""
    NONE = "none"
    PRE_NORM = "pre"           # x + F(LN(x))
    POST_NORM = "post"         # LN(x + F(x))


class ResidualMode(str, Enum):
    """Which vertical connection strategy a :class:`ResidualStack` should use."""
    CLASSIC = "classic"                 # §2
    HYPER = "hyper"                     # §4 HC
    MANIFOLD_HYPER = "manifold_hyper"   # §4 mHC
    FULL_ATTN_RES = "full_attn_res"     # §5 Full Attention Residuals
    BLOCK_ATTN_RES = "block_attn_res"   # §5 Block Attention Residuals
    MULTI_HEAD_ATTN_RES = "mh_attn_res" # §6 多头纵向


@dataclass
class AttnResConfig:
    """Config for :class:`AttentionResidual` and related modules.

    ``d_model``:
        Feature dimension D.
    ``num_heads``:
        1 in the "pure" default (§5.3). Multi-head version lives in
        :mod:`attention_residuals.multi_head_vertical`.
    ``temperature``:
        Divisor for the scaled dot product (default: sqrt(d_head)).
        Set to a custom float to override.
    ``share_key``:
        If True, every history layer uses the same W_K; otherwise each
        layer keeps its own W_K. Article defaults to a shared key.
    """
    d_model: int = 64
    num_heads: int = 1
    temperature: Optional[float] = None
    share_key: bool = True
    include_self: bool = True   # whether x_l itself is part of the history {x_0..x_l}


@dataclass
class BlockConfig:
    """Config for :class:`BlockAttnResStack` (§5 分段机制)."""
    num_blocks: int = 4
    layers_per_block: int = 4
    inner_residual: bool = False   # §5 末段的"2 选 1"，默认关闭

    @property
    def total_layers(self) -> int:
        return self.num_blocks * self.layers_per_block
