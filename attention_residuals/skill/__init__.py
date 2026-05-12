"""SkillOps control plane · skill self-evolution package.

This namespace is an *additive-only* extension of the existing
:mod:`attention_residuals.sre_control` stack. It introduces a skill-as-
first-class-object layer (see ``skill-research/architecture/``) without
modifying any existing public API (ADR-004).

Entry points for readers:

* :mod:`attention_residuals.skill.types` — shared data structures.
* :mod:`attention_residuals.skill.governance.version_graph` — DAG of
  skill versions (PR-013).
* :mod:`attention_residuals.skill.governance.repository` — SkillRecord
  CRUD + stage lifecycle (PR-012).
* ``skill-research/`` in the repository root contains the full
  architecture, requirements, tasks and refined specs.
"""

from attention_residuals.skill.types import (  # noqa: F401
    SCHEMA_VERSION,
    BlastRadius,
    ChangeKind,
    CommitDecision,
    ConflictReason,
    EventKind,
    Granularity,
    MergeConflict,
    MergedSkillPatch,
    OverrideInfo,
    PatchField,
    PatchTarget,
    RoutingDecision,
    RoutingRationale,
    SkillOpsEvent,
    SkillPatchCandidate,
    SkillRecord,
    SkillVariant,
    SkillVersion,
    Stage,
    VerifierFinding,
    compute_patch_id,
    compute_version_id,
)
