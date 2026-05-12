"""SkillOps facade + cross-cutting concerns.

Holds the orchestrator (``SkillOpsPipeline``) that ties evidence →
knowledge-edit → verify → govern → route in one place, plus the event
bus / observability / snapshot helpers (M4+).
"""

from attention_residuals.skill.skillops.pipeline import (  # noqa: F401
    PhaseTiming,
    PipelineDeps,
    PipelineReport,
    SkillOpsPipeline,
)
