"""Determinism-oriented metrics — §5.2 三项确定性保障.

Three observable indicators corresponding to the three determinism
guarantees in §5.2:

1. **Mandatory attention** — entropy and near-one-hot statistics of
   ``a_{l,k}`` weights. Low entropy indicates the layer is decisively
   selecting a specific history; any non-uniform distribution means
   "必然关注" has something to bite on.

2. **Vertical / horizontal decoupling** — cosine similarity between
   gradient flows through the two paths; closer to 0 ⇒ better decoupling.

3. **Complexity report** — report theoretical per-layer cost for both
   Full and Block Attention Residuals so the engineering trade-off is
   explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import torch
from torch import Tensor


# ---------------------------------------------------------------------------
# 1. Mandatory attention
# ---------------------------------------------------------------------------

def attention_entropy(weights: Tensor, dim: int = 0, eps: float = 1e-12) -> Tensor:
    """Shannon entropy of softmax weights along ``dim``.

    Parameters
    ----------
    weights : Tensor
        Output of a softmax, e.g. shape ``[K, B, T]`` along ``dim=0``.
    """
    p = weights.clamp(min=eps)
    return -(p * p.log()).sum(dim=dim)


def mandatory_attention_score(weights: Tensor, dim: int = 0) -> float:
    """Scalar score in [0, 1]: ``1 - H(a) / log(K)``.

    ``1`` means the layer concentrates its entire mass on one history state
    (maximum "mandatory attention"), ``0`` means uniform (no preference).
    """
    K = weights.size(dim)
    if K <= 1:
        return 1.0
    max_entropy = torch.log(torch.tensor(float(K), device=weights.device))
    ent = attention_entropy(weights, dim=dim).mean()
    return float((1.0 - ent / max_entropy).clamp(0.0, 1.0).item())


# ---------------------------------------------------------------------------
# 2. Vertical / horizontal decoupling
# ---------------------------------------------------------------------------

def _flatten_grads(params: Iterable[torch.nn.Parameter]) -> Optional[Tensor]:
    grads = [p.grad.detach().flatten() for p in params if p.grad is not None]
    if not grads:
        return None
    return torch.cat(grads)


def vertical_horizontal_decoupling(
    vertical_params: Iterable[torch.nn.Parameter],
    horizontal_params: Iterable[torch.nn.Parameter],
) -> Optional[float]:
    """Absolute cosine similarity between gradient vectors of the two paths.

    Run a forward + backward before calling this. Returns ``None`` if either
    side has no gradient yet.
    """
    gv = _flatten_grads(vertical_params)
    gh = _flatten_grads(horizontal_params)
    if gv is None or gh is None:
        return None
    denom = gv.norm() * gh.norm() + 1e-12
    return float((gv @ gh).abs().item() / denom.item())


# ---------------------------------------------------------------------------
# 3. Complexity report
# ---------------------------------------------------------------------------

@dataclass
class ComplexityReport:
    """Very rough FLOP / param accounting per layer or per stack."""
    num_layers: int
    d_model: int
    layers_per_block: int                # 1 → Full, >1 → Block
    new_params_per_layer: int            # parameters introduced by Attn Res
    vertical_flops_total: int            # across the whole stack

    def as_dict(self) -> dict:
        return self.__dict__


def complexity_report(
    num_layers: int,
    d_model: int,
    layers_per_block: int = 1,
    shared_key: bool = True,
) -> ComplexityReport:
    """Estimate the vertical cost of an Attention-Residual stack.

    - Full Attention Residuals (``layers_per_block = 1``):
        Σ_{l=1..L} l·D² FLOPs  → O(L² · D²)

    - Block Attention Residuals (``layers_per_block = B > 1``):
        Σ_{b=1..G} b·D²  with G = L/B  → O((L/B)² · D²)  + inner O(L)
    """
    G = max(1, num_layers // layers_per_block)
    # Per-layer new params: 1 Query matrix; optional shared Key.
    new_params = d_model * d_model * (1 if shared_key else 2)
    # Vertical FLOPs: each boundary attends to prior boundaries (approx).
    vertical_flops = sum(b * d_model * d_model for b in range(1, G + 1))
    return ComplexityReport(
        num_layers=num_layers,
        d_model=d_model,
        layers_per_block=layers_per_block,
        new_params_per_layer=new_params,
        vertical_flops_total=int(vertical_flops),
    )
