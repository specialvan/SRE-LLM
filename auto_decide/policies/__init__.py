"""Nominal policy implementations.

The planner keeps orchestration in ``planner.py``. Policy variants that
make the nominal action smarter live here so the hard safety gates stay
separate from the soft decision layer.
"""

from .predictive_brake import PredictiveBrakePolicy

__all__ = ["PredictiveBrakePolicy"]
