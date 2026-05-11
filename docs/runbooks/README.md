# Runbooks

Step-by-step procedures for on-call operators and reviewers of this
pipeline. Each runbook is intentionally short; linked ADRs carry the
"why".

| Runbook | When to read |
| --- | --- |
| [reproduce-decision.md](reproduce-decision.md) | Post-incident review, reproduce a `Decision` byte-for-byte. |
| [escalate-decision.md](escalate-decision.md) | The pipeline emitted `ESCALATE`. |
| [tune-risk-thresholds.md](tune-risk-thresholds.md) | Too many `ROLLBACK` / `HOLD` signals. |
| [bootstrap-new-service.md](bootstrap-new-service.md) | Onboarding a service so the pipeline has enough state to decide. |
| [multi-instance-lease.md](multi-instance-lease.md) | Before changing replicas or debugging lease ownership. |
