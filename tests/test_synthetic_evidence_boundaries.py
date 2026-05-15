from __future__ import annotations

import pytest

from analysis import s05_ekf, s08_catch_allocation


@pytest.mark.parametrize("seed", [0])
def test_ekf_report_keeps_position_tail_regression_visible(seed: int) -> None:
    result = s05_ekf.main(seed=seed)

    before = result["before"]
    after = result["after"]

    assert after["vel_rmse"] < before["vel_rmse"]
    assert after["pos_p95"] > before["pos_p95"]


@pytest.mark.parametrize("seed", [0])
def test_catch_allocation_report_keeps_residual_tradeoff_visible(seed: int) -> None:
    result = s08_catch_allocation.main(seed=seed)

    before = result["before"]
    after = result["after"]

    assert after["saturation_violation_pct"] == 0
    assert after["mean_residual"] >= before["mean_residual"]
