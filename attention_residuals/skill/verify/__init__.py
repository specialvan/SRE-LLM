"""Route-2 · verify & diagnose components.

See ``skill-research/02-route-verify-diagnose/`` for the spec.
"""

from attention_residuals.skill.verify.patcher import (  # noqa: F401
    PatcherConfig,
    SkillPatcher,
)
from attention_residuals.skill.verify.regression_gate import (  # noqa: F401
    GateConfig,
    GateDecision,
    GateVerdict,
    ReplayCase,
    SkillRegressionGate,
)
from attention_residuals.skill.verify.shadow_verifier import (  # noqa: F401
    CombinerHarness,
    SkillShadowVerifier,
    VerificationHarness,
    VerifierConfig,
    VerifyResult,
    CaseResult,
)
