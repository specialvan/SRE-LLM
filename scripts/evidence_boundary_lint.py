"""Lint wording that overstates synthetic research evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re


PUBLIC_EVIDENCE_BOUNDARY_DOCS = (
    "README.md",
    "PR-REQUIREMENTS.md",
    "wiki/README.md",
    "wiki/evidence-ledger.md",
    "wiki/project-overview.md",
    "wiki/review-backlog.md",
    "wiki/pillar-mapping.md",
    "docs/V2_Knowledge/knowledge-base.html",
    "docs/codex-review/README.md",
    "docs/codex-review/CODEX_SUMMARY.md",
    "docs/codex-review/OPEN_RISKS.md",
    "docs/codex-review/QUALITY_GATES.md",
    "docs/codex-review/ENGINEERING_PACKET.md",
    "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
    "docs/codex-review/CLAUDE_REFINED_SPEC.md",
    "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
    "docs/opus-review/README.md",
    "docs/opus-review/HANDOFF.md",
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "docs/claude-development-audit/backlog.md",
)


@dataclass(frozen=True)
class OverclaimFinding:
    phrase: str
    line: int
    column: int


OVERCLAIM_PATTERNS = (
    re.compile(r"\bproves?\s+production\s+readiness\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ]ready\b", re.IGNORECASE),
    re.compile(r"\bofficial\s+SpaceX\s+implementation\b", re.IGNORECASE),
    re.compile(r"\bSpaceX\s+internal\s+implementation\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+proof\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+theorem\b", re.IGNORECASE),
    re.compile(r"\bproduction\s+benchmark\b", re.IGNORECASE),
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


def _is_negated_boundary_wording(
    context_prefix: str, line: str, match_start: int, match_end: int
) -> bool:
    prefix = line[:match_start].lower()
    suffix = line[match_end : match_end + 100].lower()
    window = f"{context_prefix.lower()}\n{prefix}"[-200:] + suffix
    return any(cue in window for cue in NEGATION_CUES)
