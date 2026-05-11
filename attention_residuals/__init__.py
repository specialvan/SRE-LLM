"""attention_residuals — explicit vertical self-attention over layer history.

Package entry points mirror the sections of the source article:

- ``classic_residual``      — §2 classic residual ``x + F(x)``
- ``norm``                  — §3 Pre-Norm / Post-Norm wrappers
- ``hyper_connections``     — §4 HC / mHC baseline
- ``attn_residual``         — §5.1 Full Attention Residuals (core)
- ``blocks``                — §5   Block Attention Residuals (sectioning)
- ``transformer_layer``     — §5.2 decoupled horizontal + vertical layer
- ``multi_head_vertical``   — §6   multi-head vertical attention
- ``layer_skip``            — §6   dynamic layer skipping
- ``stack``                 — unified, interchangeable residual stack
- ``metrics``               — §5.2 determinism indicators
"""

from .types import (
    AttnResConfig,
    BlockConfig,
    NormStyle,
    ResidualMode,
)
from .classic_residual import ClassicResidual
from .norm import NormWrapper
from .hyper_connections import HyperConnection
from .attn_residual import AttentionResidual, AttentionResidualConnector
from .blocks import BlockAttnResStack
from .multi_head_vertical import MultiHeadAttentionResidual
from .layer_skip import LayerSkipGate
from .transformer_layer import DecoupledTransformerLayer
from .stack import ResidualStack
from . import metrics
from . import sre_control
from .sre_control import (
    SignalSpec,
    WeightedConvexCombiner,
    AuditRecord, AuditTrail,
    DecoupledControlLoop,
    BlockSpec, HierarchicalBlockController,
    BudgetGate,
    MustAttendRegistry,
)
from . import sre_adaptive
from .sre_adaptive import (
    HedgeRegretLearner,
    AdaptiveCombiner,
    AdaptiveRecord,
)
from . import sre_safety
from .sre_safety import (
    SafetyEnvelope,
    ShadowRecord, ShadowRunner,
    CounterfactualResult, CounterfactualExplainer,
    WeightDriftDetector,
)
from . import sre_math
from .sre_math import (
    ScaleInvariantNormalizer,
    TemperatureScheduler,
    ViewSpec, MultiViewCombiner,
    FTRLLearner,
    JacobianContractionMonitor,
    CreditEntry, TemporalCreditAssigner,
    LossMapper, MetricLossSpec, MetricLossMapper, AuditCreditReplay,
    AuditReplayCursor, StreamingAuditCreditReplay,
    WassersteinDriftDetector,
)
from . import sre_metrics
from .sre_metrics import (
    MetricPoint,
    PrometheusQuery, PrometheusHTTPClient, PrometheusContextReader,
    OpenTelemetryJSONMetricReader,
    reduce_points,
)
from . import sre_self_envelope
from .sre_self_envelope import (
    OutcomeLabel, OutcomeEvidence, OutcomeLike, ActionOutcome,
    LearnedSafetyEnvelope, ContractionAwareEnvelope,
    Labeler, LearnerStats, EnvelopeLearner, CreditAwareLabeler,
)

__all__ = [
    # configs
    "AttnResConfig", "BlockConfig", "NormStyle", "ResidualMode",
    # residual operators
    "ClassicResidual", "NormWrapper", "HyperConnection",
    "AttentionResidual", "AttentionResidualConnector",
    "BlockAttnResStack", "MultiHeadAttentionResidual", "LayerSkipGate",
    "DecoupledTransformerLayer",
    # end-to-end
    "ResidualStack",
    # observability
    "metrics",
    # SRE control-plane distillation
    "sre_control",
    "SignalSpec", "WeightedConvexCombiner",
    "AuditRecord", "AuditTrail",
    "DecoupledControlLoop",
    "BlockSpec", "HierarchicalBlockController",
    "BudgetGate", "MustAttendRegistry",
    # Closed-loop adaptation
    "sre_adaptive",
    "HedgeRegretLearner", "AdaptiveCombiner", "AdaptiveRecord",
    # Industrial safety layer
    "sre_safety",
    "SafetyEnvelope",
    "ShadowRecord", "ShadowRunner",
    "CounterfactualResult", "CounterfactualExplainer",
    "WeightDriftDetector",
    # Deep-math primitives (per-equation distillations)
    "sre_math",
    "ScaleInvariantNormalizer", "TemperatureScheduler",
    "ViewSpec", "MultiViewCombiner",
    "FTRLLearner",
    "JacobianContractionMonitor",
    "CreditEntry", "TemporalCreditAssigner",
    "LossMapper", "MetricLossSpec", "MetricLossMapper", "AuditCreditReplay",
    "AuditReplayCursor", "StreamingAuditCreditReplay",
    "WassersteinDriftDetector",
    # Metric source adapters
    "sre_metrics",
    "MetricPoint",
    "PrometheusQuery", "PrometheusHTTPClient", "PrometheusContextReader",
    "OpenTelemetryJSONMetricReader",
    "reduce_points",
    # Self-learning envelope (audit → envelope closed loop)
    "sre_self_envelope",
    "OutcomeLabel", "OutcomeEvidence", "OutcomeLike", "ActionOutcome",
    "LearnedSafetyEnvelope", "ContractionAwareEnvelope",
    "Labeler", "LearnerStats", "EnvelopeLearner", "CreditAwareLabeler",
]

__version__ = "0.1.0"
