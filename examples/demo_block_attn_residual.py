"""Block Attention Residuals vs Full — complexity / cost trade-off (§5).

Run with::

    python -m examples.demo_block_attn_residual
"""

from __future__ import annotations

import time

import torch

from attention_residuals import (
    AttnResConfig,
    BlockConfig,
    ResidualMode,
    ResidualStack,
)
from attention_residuals.metrics import complexity_report


def benchmark(stack: torch.nn.Module, x: torch.Tensor, n: int = 20) -> float:
    # Warm-up
    for _ in range(3):
        _ = stack(x)
    t0 = time.perf_counter()
    for _ in range(n):
        _ = stack(x)
    return (time.perf_counter() - t0) / n * 1000.0  # ms / fwd


def main() -> None:
    torch.manual_seed(0)
    B, T, D = 2, 16, 32

    print(f"{'L':>5}  {'Full (ms)':>12}  {'Block(B=4) (ms)':>18}  "
          f"{'Full FLOPs':>14}  {'Block FLOPs':>14}")
    for L in (8, 16, 32, 64):
        full = ResidualStack(
            d_model=D, mode=ResidualMode.FULL_ATTN_RES, num_layers=L,
            attn_cfg=AttnResConfig(d_model=D),
        )
        block_cfg = BlockConfig(num_blocks=max(1, L // 4), layers_per_block=4,
                                inner_residual=False)
        block = ResidualStack(
            d_model=D, mode=ResidualMode.BLOCK_ATTN_RES,
            attn_cfg=AttnResConfig(d_model=D),
            block_cfg=block_cfg,
        )

        x = torch.randn(B, T, D)
        t_full = benchmark(full, x)
        t_block = benchmark(block, x)

        r_full = complexity_report(L, D, layers_per_block=1)
        r_block = complexity_report(L, D, layers_per_block=4)
        print(
            f"{L:>5}  {t_full:>12.3f}  {t_block:>18.3f}  "
            f"{r_full.vertical_flops_total:>14}  {r_block.vertical_flops_total:>14}"
        )


if __name__ == "__main__":
    main()
