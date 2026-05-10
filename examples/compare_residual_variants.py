"""Side-by-side training run comparing residual variants on a toy task.

Classic residual · Hyper-Connections · Full AttnRes · Multi-head AttnRes

Run with::

    python -m examples.compare_residual_variants
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List

import torch
from torch import nn

from attention_residuals import (
    AttnResConfig,
    ResidualMode,
    ResidualStack,
)


@dataclass
class RunResult:
    name: str
    losses: List[float]
    wall_ms: float
    num_params: int


def build(mode: ResidualMode, d_model: int, num_layers: int) -> nn.Module:
    kwargs: Dict = dict(
        d_model=d_model,
        mode=mode,
        num_layers=num_layers,
        attn_cfg=AttnResConfig(d_model=d_model, num_heads=4 if mode is ResidualMode.MULTI_HEAD_ATTN_RES else 1),
    )
    if mode is ResidualMode.HYPER:
        kwargs.update(hyper_channels=4, hyper_groups=1)
    return ResidualStack(**kwargs)


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)


def run_one(
    name: str, mode: ResidualMode, *, d_model: int, num_layers: int,
    steps: int = 200, batch: int = 4, tokens: int = 16, seed: int = 0,
) -> RunResult:
    torch.manual_seed(seed)
    stack = build(mode, d_model, num_layers)
    head = nn.Linear(d_model, d_model)
    opt = torch.optim.Adam(list(stack.parameters()) + list(head.parameters()), lr=1e-3)

    # Synthetic task: reconstruct a fixed random embedding from noisy input.
    target = torch.randn(batch, tokens, d_model)
    losses: List[float] = []
    t0 = time.perf_counter()
    for _ in range(steps):
        x = target + 0.1 * torch.randn_like(target)
        y = head(stack(x))
        loss = ((y - target) ** 2).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        losses.append(loss.item())
    wall = (time.perf_counter() - t0) * 1000.0
    return RunResult(name=name, losses=losses, wall_ms=wall,
                     num_params=count_params(stack) + count_params(head))


def main() -> None:
    d_model, num_layers = 32, 6
    configs = [
        ("Classic (§2)",            ResidualMode.CLASSIC),
        ("HyperConn (§4)",          ResidualMode.HYPER),
        ("Full AttnRes (§5.1)",     ResidualMode.FULL_ATTN_RES),
        ("Multi-head AttnRes (§6)", ResidualMode.MULTI_HEAD_ATTN_RES),
    ]
    results = [run_one(name, mode, d_model=d_model, num_layers=num_layers)
               for name, mode in configs]

    print(f"{'variant':<28}{'final loss':>14}{'Δloss':>12}{'params':>12}{'wall (ms)':>14}")
    for r in results:
        delta = r.losses[0] - r.losses[-1]
        print(f"{r.name:<28}{r.losses[-1]:>14.5f}{delta:>12.5f}{r.num_params:>12d}{r.wall_ms:>14.1f}")


if __name__ == "__main__":
    main()
