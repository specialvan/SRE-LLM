"""Lint wording that overstates synthetic research evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


PUBLIC_EVIDENCE_BOUNDARY_DOCS = (
    "README.md",
    "PR-REQUIREMENTS.md",
    "spacex-Session.md",
    "wiki/README.md",
    "wiki/evidence-ledger.md",
    "wiki/project-overview.md",
    "wiki/review-backlog.md",
    "wiki/pillar-mapping.md",
    "docs/CODEX_REVIEW_REPORT.md",
    "docs/CODEX_HANDOFF.md",
    "docs/knowledge-base.html",
    "docs/V2_Knowledge/knowledge-base.html",
    "docs/control-center.html",
    "docs/API_CONTRACTS.md",
    "docs/ARCHITECTURE.md",
    "docs/ENGINEERING_CHECKLIST.md",
    "docs/EQUATION_DEEP_DIVE.md",
    "docs/EVENT_SCHEMA.md",
    "docs/FORMULA_MAP.md",
    "docs/RUNTIME_STATES.md",
    "docs/SPECIAL_SOLUTIONS_DERIVATIONS.md",
    "wiki/runtime-lifecycle.md",
    "docs/codex-review/README.md",
    "docs/codex-review/CODEX_SUMMARY.md",
    "docs/codex-review/OPEN_RISKS.md",
    "docs/codex-review/QUALITY_GATES.md",
    "docs/codex-review/ENGINEERING_PACKET.md",
    "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
    "docs/codex-review/CLAUDE_REFINED_SPEC.md",
    "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
    "docs/CONTROL_CENTER_HANDOFF.md",
    "docs/EVENT_EVIDENCE_MANIFEST.md",
    "docs/STACK_DATA_CONTRACT.md",
    "docs/claude-review/README.md",
    "docs/claude-review/HANDOFF_CHECKLIST.md",
    "docs/claude-review/CODEX_TRIAGE.md",
    "docs/claude-review/REVIEW_OF_CODEX_SESSION.md",
    "docs/claude-review/DETAILED_ARCHITECTURE.md",
    "docs/claude-review/EVENT_LIFECYCLE.md",
    "docs/claude-review/FAILURE_MODES.md",
    "claude-review/docs/v2026-05-28/README.md",
    "claude-review/docs/v2026-05-28/00-blocker-summary.md",
    "claude-review/docs/v2026-05-28/01-line-level-findings.md",
    "claude-review/docs/v2026-05-28/02-evidence-chain-audit.md",
    "claude-review/docs/v2026-05-28/03-security-and-doc-consistency.md",
    "claude-review/docs/v2026-05-28/04-deeper-dive-addendum.md",
    "claude-review/docs/v2026-05-28/evidence/rerun-log-2026-05-28.md",
    "claude-review/docs/v2026-05-31/README.md",
    "claude-review/docs/v2026-05-31/00-executive-summary.md",
    "claude-review/docs/v2026-05-31/01-handoff-analysis.md",
    "claude-review/docs/v2026-05-31/02-quality-gates-analysis.md",
    "claude-review/docs/v2026-05-31/03-open-risks-analysis.md",
    "claude-review/docs/v2026-05-31/04-opus-packet-analysis.md",
    "claude-review/docs/v2026-05-31/05-comprehensive-review-report.md",
    "claude-review/docs/v2026-05-31/AGENT-REVIEW-GUIDE.md",
    "claude-review/docs/v2026-05-31/HANDOFF-KNOWLEDGE-BASE.md",
    "claude-review/docs/v2026-05-26/README.md",
    "claude-review/docs/v2026-05-26/00-executive-brief.md",
    "claude-review/docs/v2026-05-26/01-scope-and-baseline.md",
    "claude-review/docs/v2026-05-26/02-resolved-findings-spot-check.md",
    "claude-review/docs/v2026-05-26/03-new-findings.md",
    "claude-review/docs/v2026-05-26/04-evidence-manifest-audit.md",
    "claude-review/docs/v2026-05-26/05-merge-gate-checklist.md",
    "claude-review/docs/v2026-05-26/evidence/verification-rerun-2026-05-26.md",
    "docs/opus-review/v1.0/README.md",
    "docs/opus-review/v1.0/DEEP_REVIEW_REPORT.md",
    "docs/opus-review/v1.0/QUALITY_GATE_VERIFICATION.md",
    "docs/opus-review/v1.0/MODULE_INSPECTION.md",
    "docs/opus-review/v1.0/LINE_LEVEL_FINDINGS.md",
    "docs/opus-review/v1.0/REPRODUCTION_EVIDENCE.md",
    "docs/opus-review/v1.0/FOLLOWUP_BACKLOG.md",
    "docs/claude-review/v1.0/README.md",
    "docs/claude-development-audit/README.md",
    "claude-review/docs/README.md",
    "docs/claude-development-audit/reports/2026-05-15-completion-audit.md",
    "docs/claude-development-audit/reports/2026-05-15-continuation-review.md",
    "docs/claude-development-audit/reports/2026-05-15-deep-review.md",
    "docs/claude-development-audit/reports/2026-05-15-encoding-repair-note.md",
    "docs/claude-development-audit/reports/2026-05-15-joseph-form-cleanup.md",
    "docs/claude-development-audit/reports/2026-05-15-post-commit-review.md",
    "docs/claude-development-audit/reports/2026-05-15-quality-gates-html-canonical.md",
    "docs/claude-development-audit/reports/2026-05-16-adapter-cause-taxonomy.md",
    "docs/claude-development-audit/reports/2026-05-16-control-center-exposure.md",
    "docs/claude-development-audit/reports/2026-05-16-package-smoke.md",
    "docs/claude-development-audit/reports/2026-05-16-release-hygiene.md",
    "docs/claude-development-audit/reports/2026-05-16-synthetic-evidence-boundaries.md",
    "docs/claude-development-audit/evidence/2026-05-15-continuation-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-joseph-form-cleanup-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-post-commit-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-quality-gates-html-canonical-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-15-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-adapter-cause-taxonomy-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-control-center-exposure-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-package-smoke-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-release-hygiene-snapshot.md",
    "docs/claude-development-audit/evidence/2026-05-16-synthetic-evidence-boundaries-snapshot.md",
    "docs/claude-development-audit/git/timeline.md",
    "docs/superpowers/plans/README.md",
    "docs/superpowers/specs/README.md",
    "docs/superpowers/plans/2026-05-15-claude-development-audit.md",
    "docs/superpowers/plans/2026-05-29-evidence-artifact-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-consistency-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-contract-report-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-manifest-check-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-manifest-generation-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-replay-artifact-report-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-report-manifest-shape-test-split.md",
    "docs/superpowers/plans/2026-05-29-evidence-s10-trace-report-test-split.md",
    "docs/superpowers/plans/2026-05-30-control-center-browser-dom-test-split.md",
    "docs/superpowers/plans/2026-05-30-control-center-browser-manifest-test-split.md",
    "docs/superpowers/plans/2026-05-30-evidence-contract-report-follow-on-split.md",
    "docs/superpowers/plans/2026-05-30-evidence-report-orchestrator-cleanup.md",
    "docs/superpowers/specs/2026-05-29-evidence-artifact-test-split-design.md",
    "docs/superpowers/specs/2026-05-29-evidence-consistency-split-design.md",
    "docs/opus-review/README.md",
    "docs/opus-review/HANDOFF.md",
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "docs/claude-development-audit/backlog.md",
)

PUBLIC_PROSE_ROOTS = ('.', 'docs', 'claude-review', 'wiki')
PUBLIC_PROSE_SUFFIXES = ('.md', '.html')


@dataclass(frozen=True)
class OverclaimFinding:
    phrase: str
    line: int
    column: int


OVERCLAIM_PATTERNS = (
    re.compile(r"\bproves?\s+production\s+readiness\b", re.IGNORECASE),
    re.compile(r"\bready\s+for\s+production\b", re.IGNORECASE),
    re.compile(r"\bsafe\s+for\s+production\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ]ready\b", re.IGNORECASE),
    re.compile(r"\bofficial\s+SpaceX\s+implementation\b", re.IGNORECASE),
    re.compile(r"\bSpaceX\s+internal\s+implementation\b", re.IGNORECASE),
    re.compile(
        r"\bSpaceX(?:'s\s+|-|\s+)"
        r"(?:official|internal|production|real|actual|flight|"
        r"proprietary|private|confidential)(?:-|\s+)"
        r"(?:implementation|algorithm|software|controller|"
        r"control(?:-|\s+)(?:algorithm|software|controller))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bSpaceX(?:'s\s+|-|\s+)"
        r"(?:official|internal|production|real|actual|flight|"
        r"proprietary|private|confidential)(?:-|\s+)"
        r"(?:data|telemetry|logs?|traces?|sensor(?:-|\s+)data)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:real|actual|field)(?:-|\s+)"
        r"(?:(?:flight|sensor|incident)(?:-|\s+))?"
        r"(?:data|telemetry|logs?|traces?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\blive(?:-|\s+)(?:flight|sensor|incident)(?:-|\s+)"
        r"(?:data|telemetry|logs?|traces?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?<!non-)(?<!SpaceX\s)(?<!SpaceX-)(?<!SpaceX's\s)"
        r"(?:production|prod)(?:-|\s+)"
        r"(?:(?:flight|sensor|incident|traffic|customer)(?:-|\s+)"
        r"(?:data|telemetry|logs?|traces?)|(?:data|telemetry|logs?))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcustomer(?:-|\s+)traffic(?:-|\s+)"
        r"(?:data|telemetry|logs?|traces?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:validat(?:es?|ed|ing)|calibrat(?:es?|ed|ing)|"
        r"train(?:s|ed|ing)?|benchmark(?:s|ed|ing)?)"
        r"(?:-|\s+)(?:against|on|from|with)(?:-|\s+)"
        r"(?:real|actual|field|live|production|prod|customer)(?:-|\s+)"
        r"(?:incidents?|traffic|workloads?|data|telemetry|logs?|traces?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bproduction\s+proof\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ]grade\s+proof\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+theorem\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+benchmark\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ](?:level|caliber|quality)\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ](?:like|representative)\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ](?:realistic|scale)\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ]equivalent\b", re.IGNORECASE),
    re.compile(r"\bprod[- ](?:ready|like|grade|quality|equivalent)\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+equivalence\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+guarantees?\b", re.IGNORECASE),
    re.compile(r"\b(?:prod|production)\s+parity\b", re.IGNORECASE),
    re.compile(r"\bcomparable\s+to\s+production\b", re.IGNORECASE),
    re.compile(r"\bparity\s+with\s+(?:prod|production)\b", re.IGNORECASE),
    re.compile(r"\brealistic\s+production\b", re.IGNORECASE),
    re.compile(r"\brepresentative\s+of\s+production\b", re.IGNORECASE),
    re.compile(
        r"\bvalidates?\s+production\s+(?:deployment|readiness|safety|viability)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bequivalent\s+to\s+a?\s*production\s+"
        r"(?:benchmark|trace|incident\s+coverage|incident\s+timeline)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bguarantees?\s+production\s+(?:readiness|safety|viability)\b",
        re.IGNORECASE,
    ),
    re.compile(r"证明生产(?:就绪|可用|安全|级别|可上线)"),
    re.compile(r"(?<!证明)生产(?:证明|定理|基准|就绪|可用|安全|级别|可上线)"),
    re.compile(r"SpaceX\s*(?:官方|内部|内参|真实|生产)\s*实现", re.IGNORECASE),
)

NEGATION_CUES = (
    "avoid",
    "cannot",
    "can't",
    "do not",
    "does not",
    "don't",
    "linted for",
    "must not",
    "never",
    "no ",
    "not ",
    "rather than",
    "reject ",
    "rejected",
    "rejects",
    "without",
    "不要",
    "不能",
    "不能被写成",
    "不代表",
    "不是",
    "不得",
    "没有",
    "拦截",
    "拒绝",
)

NEGATION_SCOPE_BOUNDARIES = (
    ".",
    ";",
    "。",
    "；",
    " but ",
    " however ",
    " yet ",
    " nevertheless ",
    "，但",
    "但是",
    "然而",
    "不过",
)
IMMEDIATE_NEGATION_PREFIXES = ("非", "合成证据 vs", "合成证据 vs ")
FORBIDDEN_EXAMPLE_CUES = (
    "avoid:",
    "forbidden examples:",
    "unsafe examples:",
    "rejected examples:",
    "盲区",
    "常见陷阱",
    "陷阱 ",
)


def find_overclaim_phrases(text: str) -> list[OverclaimFinding]:
    findings: list[OverclaimFinding] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        context_prefix = "\n".join(lines[max(0, line_number - 8) : line_number - 1])
        for pattern in OVERCLAIM_PATTERNS:
            for match in pattern.finditer(line):
                if _is_negated_boundary_wording(
                    context_prefix, line, match.start(), match.end()
                ):
                    continue
                findings.append(
                    OverclaimFinding(
                        phrase=match.group(0),
                        line=line_number,
                        column=match.start() + 1,
                    )
                )
    return findings


def uncovered_public_prose_docs(repo_root: Path) -> list[str]:
    covered = set(PUBLIC_EVIDENCE_BOUNDARY_DOCS)
    uncovered: list[str] = []
    for root_name in PUBLIC_PROSE_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        paths = root.glob('*') if root_name == '.' else root.rglob('*')
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in PUBLIC_PROSE_SUFFIXES:
                continue
            relative_path = path.relative_to(repo_root).as_posix()
            if relative_path not in covered:
                uncovered.append(relative_path)
    return sorted(uncovered)


def check_public_evidence_boundaries(repo_root: Path) -> list[str]:
    errors = [
        f'uncovered public prose doc: {relative_path}'
        for relative_path in uncovered_public_prose_docs(repo_root)
    ]
    for relative_path in PUBLIC_EVIDENCE_BOUNDARY_DOCS:
        path = repo_root / relative_path
        if not path.exists():
            errors.append(f'missing public evidence-boundary doc: {relative_path}')
            continue
        for finding in find_overclaim_phrases(path.read_text(encoding='utf-8')):
            errors.append(
                f'{relative_path}:{finding.line}:{finding.column}: '
                f'unqualified evidence-boundary phrase: {finding.phrase}'
            )
    return errors


def _is_negated_boundary_wording(
    context_prefix: str, line: str, match_start: int, match_end: int
) -> bool:
    if _is_forbidden_example_context(context_prefix, line):
        return True
    if _is_markdown_does_not_support_cell(context_prefix, line, match_start):
        return True
    prefix = line[:match_start].lower()
    suffix = line[match_end : match_end + 100].lower()
    if prefix.rstrip().endswith(IMMEDIATE_NEGATION_PREFIXES):
        return True
    prefix_scope = f"{context_prefix.lower()}\n{prefix}"[-200:]
    normalized_prefix_scope = re.sub(r"[\s>]+", "", prefix_scope)
    if "不代表" in normalized_prefix_scope:
        return True
    for boundary in NEGATION_SCOPE_BOUNDARIES:
        boundary_index = prefix_scope.rfind(boundary)
        if boundary_index != -1:
            prefix_scope = prefix_scope[boundary_index + len(boundary) :]
    window = re.sub(r"\s+", " ", prefix_scope + suffix)
    return any(cue in window for cue in NEGATION_CUES)


def _is_markdown_does_not_support_cell(
    context_prefix: str, line: str, match_start: int
) -> bool:
    if not line.lstrip().startswith("|"):
        return False
    cell_index = _markdown_cell_index(line, match_start)
    if cell_index is None:
        return False
    for previous_line in reversed(context_prefix.splitlines()):
        if not previous_line.lstrip().startswith("|"):
            continue
        if _is_markdown_separator_row(previous_line):
            continue
        header_cells = _markdown_cells(previous_line)
        if cell_index >= len(header_cells):
            return False
        header = header_cells[cell_index].lower()
        return any(
            cue in header
            for cue in ("does not support", "doesn't support", "not supported")
        )
    return False


def _markdown_cell_index(line: str, match_start: int) -> int | None:
    prefix_pipe_count = line[:match_start].count("|")
    if line.lstrip().startswith("|"):
        return max(0, prefix_pipe_count - 1)
    return prefix_pipe_count


def _markdown_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_separator_row(line: str) -> bool:
    stripped = line.strip().strip("|").replace("|", "")
    return bool(stripped) and set(stripped) <= {"-", ":", " "}


def _is_forbidden_example_context(context_prefix: str, line: str) -> bool:
    context_lines = [entry.strip().lower() for entry in context_prefix.splitlines()]
    current_line = line.strip().lower()
    if current_line.startswith("-") or current_line.startswith("*"):
        recent_context = context_lines[-5:]
    else:
        recent_context = context_lines[-1:]
    return any(
        cue in entry
        for entry in recent_context + [current_line]
        for cue in FORBIDDEN_EXAMPLE_CUES
    )


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    errors = check_public_evidence_boundaries(repo_root)
    if errors:
        raise SystemExit('\n'.join(errors))
    print('evidence boundary lint ok')


if __name__ == '__main__':
    main()
