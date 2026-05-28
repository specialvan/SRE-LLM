# Event Evidence Manifest

This document defines the machine-readable review index written by
`python -m analysis.evidence_manifest`.
Use `python -m analysis.evidence_report` to print the compact reviewer summary
and verify that the manifest parses as JSON, the top-level manifest and entry
shapes are valid, all manifest-linked study/contract entries use the documented
IDs, expose required fields with the expected value types, documented values
where fixed, and valid numeric ranges where bounded. Numeric and integer count
fields reject JSON booleans even though Python treats `bool` as an `int`
subclass. If the manifest file itself is missing, the report returns
`invalid_manifest missing_manifest` rather than raising a filesystem exception.
The manifest must contain exactly one entry for each documented study and
contract. Artifact paths are portable repo-relative paths with the
documented artifact keys and expected file extensions, files exist, parse as
JSON/JSONL or valid PNG where applicable, and have matching byte-identity
metadata. Each entry's `artifact_metadata` object must use the same keys as
`artifact_paths`; each metadata value must contain a lowercase hex `sha256`
digest and non-negative integer `size_bytes` value for the exact artifact bytes.
Artifacts must also keep JSON artifacts and JSONL rows as top-level objects,
carry valid runtime event payloads, keep stack-contract event kinds in the
runtime registry, route observed trace events to an allowed contract stage, and
match key manifest counts.

The manifest is synthetic research evidence. It indexes generated artifacts for
Sections 10, 11, and 12 so reviewers can inspect event and replay evidence
without parsing console banners. It is not a production incident trace contract.

## 1. Top-Level Shape

| Field | Required | Meaning |
|---|---|---|
| `evidence_scope` | yes | Must be `synthetic_sre_event_evidence`. |
| `studies` | yes | List of study entries. Current entries are Sections 10, 11, and 12. |
| `contracts` | yes | List of machine-readable research contracts referenced by the evidence packet. |

## 2. Study Entries

| Study | Section | Evidence label | Required fields | Artifact keys |
|---|---:|---|---|---|
| `s10_failure_trace` | 10 | `synthetic_fault_window_trace` | `study`, `section`, `evidence_label`, `event_count_total`, `background_event_fraction`, `artifact_paths`, `artifact_metadata` | `full_trace_jsonl`, `sample_trace_jsonl` |
| `s11_catch_sre_wrapper` | 11 | `synthetic_wrapper_boundary` | `study`, `section`, `evidence_label`, `event_visible_fraction`, `case_counts`, `artifact_paths`, `artifact_metadata` | `diagnostics_json`, `summary_png` |
| `s12_sre_replay` | 12 | `synthetic_replay_fixture` | `study`, `section`, `evidence_label`, `event_count_total`, `replay_tick_count`, `multi_signal_window_coverage`, `artifact_paths`, `artifact_metadata` | `trace_jsonl`, `diagnostics_json`, `fixture_jsonl` |

## 3. Contract Entries

| Contract | Evidence scope | Required fields | Artifact keys |
|---|---|---|---|
| `sre_stack_data_contract` | `research_stack_data_contract` | `contract`, `evidence_scope`, `production_claim`, `orchestration_model`, `artifact_paths`, `artifact_metadata` | `contract_json` |

## 4. Path Rules

All `artifact_paths` values must be repo-relative paths that resolve inside the
repo root, not absolute local paths or `..` escapes. This keeps the manifest
portable across reviewer machines and CI workspaces. `analysis.evidence_report`
rejects nonportable artifact paths before checking file existence or content
parseability.

## 5. Byte Identity Rules

Every study and contract entry must carry `artifact_metadata` keyed identically
to `artifact_paths`. Each value must be an object with exactly these fields:
`sha256`, a 64-character lowercase hexadecimal SHA-256 digest, and
`size_bytes`, a non-negative integer byte count. `analysis.evidence_report`
rejects missing metadata, metadata/path key mismatches, malformed digests or
sizes, and artifact bytes whose recomputed digest or size differs from the
manifest. A byte mismatch is reported as `artifact_identity_mismatch` with the
expected and actual digest and size.

## 6. Nested Shapes

The `s11_catch_sre_wrapper.case_counts` object is a closed set of non-negative
integer counters, not booleans, with exactly these keys: `feasible`,
`total_overload`, `placement_infeasible`. The S11 diagnostics artifact must
also expose `case_counts` with the same closed non-negative integer counter
shape before count consistency is checked. It must also expose bounded numeric
fraction fields `feasible_quiet_fraction`,
`total_overload_event_visible_fraction`, and
`placement_infeasible_event_visible_fraction`. The S11 manifest
`event_visible_fraction` must match the weighted visibility fraction recomputed
from the diagnostics fields for the `total_overload` and
`placement_infeasible` regimes.

The `s10_failure_trace` manifest `background_event_fraction` must match the
background event leakage recomputed from `s10_trace_full.jsonl` and the S10
synthetic injection windows. Its `s10_trace_sample.jsonl` reviewer sample must
be non-empty when the full trace has events, and must match the same-length
prefix of `s10_trace_full.jsonl`. S10 trace rows must expose non-negative
integer `tick` and non-negative numeric `t_seconds` fields alongside the shared
runtime event schema fields, with `t_seconds == tick * analysis.s10_failure_trace.DT`.

The `s12_sre_replay` diagnostics artifact must expose non-whitespace string
`evidence_label` and `fixture_path` descriptors that exactly match the manifest
study evidence label and fixture artifact path, non-negative integer
`expected_event_count` and `replay_tick_count`, non-negative numeric
`event_count_total`, `max_incident_window_ticks`,
`max_multi_signal_recovery_ticks`, `max_recovery_ticks`,
`multi_signal_window_count`, and `recovery_window_count`, and fraction-valued
numeric `background_event_fraction`,
`expected_event_visible_fraction`, `multi_signal_window_coverage`,
`multi_signal_window_recovered_fraction`, `operator_action_coverage`,
`recovered_window_fraction`, and `stability_event_visible_fraction`.
`operator_action_coverage` counts only non-whitespace operator action
annotations on expected-event fixture rows.
`recovery_window_count`, `recovered_window_fraction`, and `max_recovery_ticks`
must match the recovery windows recomputed from the S12 fixture and trace.
`expected_event_visible_fraction`, `background_event_fraction`, and
`stability_event_visible_fraction` must match the expected-event visibility,
background event leakage, and stability-event visibility recomputed from the
S12 fixture and trace.
`multi_signal_window_count`, `max_incident_window_ticks`,
`multi_signal_window_coverage`, `multi_signal_window_recovered_fraction`, and
`max_multi_signal_recovery_ticks` must match the multi-signal incident windows
recomputed from the S12 fixture and trace.
`observed_expected_kinds` must be a list of non-whitespace event kind strings
registered in `sre_control.events.EVENT_COUNTEREXAMPLES`, and must exactly
match the sorted event-kind set derived from the S12 fixture expected-event
annotations. `operator_actions_by_kind` must be a dictionary keyed by
registered event kind, with each value a non-empty list of non-whitespace
operator action strings, and must exactly match the per-kind map derived from
single-kind expected-event fixture annotations. `operator_actions_by_window` must be a dictionary
keyed by non-empty incident id, with each value a non-empty list of
non-whitespace operator action strings, and must exactly match the per-window
map derived from multi-signal fixture incident annotations.

The `s12_sre_replay` trace JSONL artifact must keep every row as an object. If a
row carries `runtime`, that field must be an object, and `runtime.events` must
be a list of event objects when present.

The `s12_sre_replay` fixture JSONL artifact must keep every row as an object.
When present, `expected_kind` must be a non-whitespace string or `null`, and
`expected_kinds` must be a non-empty list of non-whitespace strings. A row must
not carry both fields. Non-null expected event kind values must exist in
`sre_control.events.EVENT_COUNTEREXAMPLES`.

The `sre_stack_data_contract` artifact must keep `event_stage_routes` as the
current closed string-to-string map whose values name declared contract stages. Its `stages`
list must contain only stage boundary objects with string `producer` values and
string-list `inputs` and `outputs`. Its `split_ready_boundaries` field must
match the current closed set: `observe_to_plan`, `plan_to_guard`,
`guard_to_allocate`, and `allocate_to_execute`.

## 7. Test Coverage

`tests/test_evidence_manifest.py` verifies that generated manifest entries match
the study/contract IDs, required fields, artifact keys documented above, and
that `analysis.evidence_report` fails when the manifest file is missing with
`missing_manifest`, the manifest JSON is malformed, the top-level manifest shape
is invalid, a study/contract ID is unknown, a
study/contract entry is missing or duplicated, a study/contract entry is
missing generic or entry-specific required fields, a study/contract field has
the wrong value type, artifact path keys or artifact metadata keys are missing
or unexpected, artifact metadata digest/size fields are malformed or stale, fixed
study/contract values drift from the documented contract, bounded numeric
fields are booleans or out of range, integer counters are booleans or negative,
an artifact path value is not a string, an artifact path has the wrong
extension for its documented key, a referenced artifact is missing, uses an
absolute or parent-directory-escaping path, is malformed as JSON/JSONL/PNG, uses a
non-object JSON artifact where a diagnostic/contract object is required, uses a
non-object JSONL row where a trace/fixture row object is required, has malformed
S11 manifest or diagnostics case counters, has malformed S12 diagnostics fields
or replay trace/fixture nested fields, carries a
schema-invalid runtime event, omits required kind-specific event fields, has a
count mismatch, or lets the stack data contract claim production status, define
malformed stage entries, stage interface fields, or event-stage routes,
malformed, missing, or unexpected split-ready boundaries, reference an unknown
runtime event kind, or disallow an event observed in the generated traces.
