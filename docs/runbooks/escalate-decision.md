# Runbook · Escalation from the pipeline

**When to use**: The pipeline emitted `DecisionKind.ESCALATE` for a
release. An `ESCALATE` is intentional — the pipeline refuses to decide
and asks a human to look.

## Triage in <5 minutes

1. Pull the decision trace:
   ```
   jq '. | select(.correlation_id=="<id>")' /var/log/gan/trace.jsonl
   ```

2. Inspect `rationale` — it is a list of plain-English tokens. Look for:
   - `unknown strategy '<X>'` → someone added a new candidate strategy
     without updating `_resolve_decision`. Block the release, fix
     `sre/self_iteration.py`, re-run.
   - `no candidate satisfied min_entropy → HOLD` (note: HOLD, not
     ESCALATE — if you see an ESCALATE with this reason, the pipeline is
     in a broken state; open a P1).
   - Any `stage.*.degraded` → a math module raised. Check stderr for the
     `span.failed` event with the same correlation id.

3. If the service is in `critical` tier and risk is `ALARM`: follow the
   normal rollback procedure regardless of the escalation.

## Remediation

- If the ESCALATE was caused by a config regression, revert the last
  pushed config and re-decide.
- If caused by a new strategy string, add the strategy to the
  `_resolve_decision` switch and add a test.
- Always write an ADR if the remediation changes behaviour for other
  services too.
