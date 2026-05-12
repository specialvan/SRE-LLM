"""Route-1 · trajectory distillation components.

See ``skill-research/01-route-trajectory-distillation/`` for the spec.
"""

from attention_residuals.skill.trajectory.merger import (  # noqa: F401
    HierarchicalPatchMerger,
    MergerConfig,
    MustAttendSnapshot,
)
from attention_residuals.skill.trajectory.miner import (  # noqa: F401
    MinerConfig,
    Trace2SkillMiner,
)
