"""Forward / backward sanity-check for Full Attention Residuals (§5.1).

Run with::

    python -m examples.demo_attn_residual
"""

from __future__ import annotations

import torch

from attention_residuals import AttnResConfig, ResidualMode, ResidualStack
from attention_residuals.metrics import mandatory_attention_score


def main() -> None:
    torch.manual_seed(0)
    B, T, D = 2, 8, 32
    L = 6

    stack = ResidualStack(
        d_model=D,
        mode=ResidualMode.FULL_ATTN_RES,
        num_layers=L,
        attn_cfg=AttnResConfig(d_model=D, num_heads=1),
    )

    x = torch.randn(B, T, D, requires_grad=True)
    y = stack(x)
    loss = y.pow(2).mean()
    loss.backward()

    # Σ_k a_{l,k} must be 1 on every layer.
    traces = stack.trace()
    for l, w in enumerate(traces):
        # w shape: [K, B, T]
        s = w.sum(dim=0)
        assert torch.allclose(s, torch.ones_like(s), atol=1e-5), (
            f"Layer {l}: weights do not sum to 1 (max err {(s - 1).abs().max().item():.2e})"
        )

    print(f"input  : {tuple(x.shape)}")
    print(f"output : {tuple(y.shape)}")
    print(f"loss   : {loss.item():.6f}")
    for l, w in enumerate(traces):
        score = mandatory_attention_score(w)
        print(
            f"layer {l}: K={w.size(0)}, Σa≈1 ✓, mandatory-attention-score={score:.3f}"
        )
    print("OK — §5.1 invariant Σ_k a_{l,k} = 1 holds across all layers.")


if __name__ == "__main__":
    main()
