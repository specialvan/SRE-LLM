"""Governance container · SkillRepository, VersionGraph, ElitePool, ...

Implements the "version + stage + commit" layer for skills. See
``skill-research/architecture/00-system-architecture.md`` §C4.
"""

from attention_residuals.skill.governance.version_graph import (  # noqa: F401
    HeadName,
    HeadRefs,
    SkillVersionGraph,
)
from attention_residuals.skill.governance.repository import (  # noqa: F401
    ConservativeRejection,
    SkillListener,
    SkillRepository,
)
from attention_residuals.skill.governance.conservative import (  # noqa: F401
    CommitVerdict,
    ConservativeCommit,
    ConservativeConfig,
    ConservativeRule,
    RuleViolation,
)
from attention_residuals.skill.governance.elite_pool import (  # noqa: F401
    Elite,
    ElitePool,
    ElitePoolConfig,
    EvictionEvent,
    MemberState,
)
