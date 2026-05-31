"""Lint review entrypoints so current ledgers stay before historical packets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


CURRENT_LEDGER_ANCHORS = (
    "wiki/review-backlog.md",
    "docs/codex-review/OPEN_RISKS.md",
    "docs/codex-review/QUALITY_GATES.md",
)
HISTORICAL_REVIEW_ANCHORS = (
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
    "docs/codex-review/CLAUDE_REFINED_SPEC.md",
    "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
    "claude-review/docs/v2026-05-31/README.md",
    "claude-review/docs/v2026-05-28/README.md",
    "claude-review/docs/v2026-05-26/README.md",
)
GIT_SCOPE_ROUTING_ANCHORS = (
    "docs/opus-review/HANDOFF.md",
    "Git Review Scope Snapshot",
    "git status --short --branch --untracked-files=all",
    "git ls-files --others --exclude-standard",
    "dirty/untracked",
)
OPUS_HANDOFF_GIT_SCOPE_ANCHORS = GIT_SCOPE_ROUTING_ANCHORS[1:]


@dataclass(frozen=True)
class AuthoritySection:
    relative_path: str
    start_marker: str
    end_marker: str
    label: str
    required_current: tuple[str, ...] = CURRENT_LEDGER_ANCHORS
    historical: tuple[str, ...] = HISTORICAL_REVIEW_ANCHORS
    anchor_aliases: dict[str, tuple[str, ...]] | None = None


AUTHORITY_SECTIONS = (
    AuthoritySection(
        "docs/CODEX_HANDOFF.md",
        "Opus review should start from",
        "- ",
        "historical Codex handoff routing",
    ),
    AuthoritySection(
        "docs/CODEX_REVIEW_REPORT.md",
        "Opus review should start from",
        "## Historical Snapshot Status",
        "historical Codex review report routing",
    ),
    AuthoritySection(
        "docs/codex-review/CODEX_SUMMARY.md",
        "live execution order is",
        "## Current State",
        "Codex summary live execution order",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
            "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
        },
    ),
    AuthoritySection(
        "docs/codex-review/CLAUDE_DEEP_REVIEW.md",
        "## Current Status Routing",
        "## Historical Findings Now Resolved",
        "Claude deep review current status routing",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
            "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
        },
    ),
    AuthoritySection(
        "docs/codex-review/CLAUDE_REFINED_SPEC.md",
        "Current status",
        "## Current verdict and source of truth",
        "Claude refined spec current status routing",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
            "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
        },
    ),
    AuthoritySection(
        "docs/codex-review/CLAUDE_REVIEW_REQUEST.md",
        "## Current Status Routing",
        "## Expected Output",
        "Claude review request current status routing",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": ("OPEN_RISKS.md",),
            "docs/codex-review/QUALITY_GATES.md": ("QUALITY_GATES.md",),
        },
    ),
    AuthoritySection(
        "docs/codex-review/ENGINEERING_PACKET.md",
        "## Entry Points",
        "## Runtime Chain",
        "Engineering packet entry points",
    ),
    AuthoritySection(
        "docs/CONTROL_CENTER_HANDOFF.md",
        "## Review Authority",
        "## Entry Points",
        "Control center handoff review authority",
    ),
    AuthoritySection(
        "docs/V2_Knowledge/knowledge-base.html",
        '<section id="handoff">',
        "<!-- ===================== Next Work",
        "V2 knowledge-base handoff routing",
        historical=HISTORICAL_REVIEW_ANCHORS
        + ("docs/claude-review/README.md", "docs/CODEX_HANDOFF.md"),
    ),
    AuthoritySection(
        'docs/codex-review/README.md',
        '## Contents',
        '## Reading Order',
        'Contents',
        anchor_aliases={
            'docs/codex-review/OPEN_RISKS.md': ('OPEN_RISKS.md', './OPEN_RISKS.md'),
            'wiki/review-backlog.md': ('../../wiki/README.md', '../../wiki/review-backlog.md'),
            'docs/codex-review/QUALITY_GATES.md': ('QUALITY_GATES.md', './QUALITY_GATES.md'),
            'docs/codex-review/CLAUDE_DEEP_REVIEW.md': ('CLAUDE_DEEP_REVIEW.md', './CLAUDE_DEEP_REVIEW.md'),
            'docs/codex-review/CLAUDE_REFINED_SPEC.md': ('CLAUDE_REFINED_SPEC.md', './CLAUDE_REFINED_SPEC.md'),
            'docs/codex-review/CLAUDE_REVIEW_REQUEST.md': ('CLAUDE_REVIEW_REQUEST.md', './CLAUDE_REVIEW_REQUEST.md'),
            'claude-review/docs/v2026-05-31/README.md': ('../../claude-review/docs/v2026-05-31/README.md',),
            'claude-review/docs/v2026-05-28/README.md': ('../../claude-review/docs/v2026-05-28/README.md',),
            'claude-review/docs/v2026-05-26/README.md': ('../../claude-review/docs/v2026-05-26/README.md',),
        },
    ),
    AuthoritySection(
        'docs/codex-review/README.md',
        '## Reading Order',
        '## Current Baseline',
        'Reading Order',
        anchor_aliases={
            'docs/codex-review/OPEN_RISKS.md': ('OPEN_RISKS.md', './OPEN_RISKS.md'),
            'wiki/review-backlog.md': ('../../wiki/review-backlog.md',),
            'docs/codex-review/QUALITY_GATES.md': ('QUALITY_GATES.md', './QUALITY_GATES.md'),
            'docs/opus-review/OPUS_REVIEW_PACKET.md': ('../opus-review/OPUS_REVIEW_PACKET.md',),
            'claude-review/docs/v2026-05-31/README.md': ('../../claude-review/docs/v2026-05-31/README.md',),
            'claude-review/docs/v2026-05-28/README.md': ('../../claude-review/docs/v2026-05-28/README.md',),
            'claude-review/docs/v2026-05-26/README.md': ('../../claude-review/docs/v2026-05-26/README.md',),
        },
    ),
    AuthoritySection(
        'docs/opus-review/OPUS_REVIEW_PACKET.md',
        '## 0. How To Review This Packet Now',
        '## Historical Context',
        'How To Review This Packet Now',
    ),
    AuthoritySection(
        "docs/opus-review/README.md",
        "## First-Read Files",
        "## Historical Inputs",
        "First-Read Files",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": (
                "../codex-review/OPEN_RISKS.md",
            ),
            "wiki/review-backlog.md": ("../../wiki/review-backlog.md",),
            "docs/codex-review/QUALITY_GATES.md": (
                "../codex-review/QUALITY_GATES.md",
            ),
            "docs/opus-review/OPUS_REVIEW_PACKET.md": (
                "OPUS_REVIEW_PACKET.md",
            ),
            "claude-review/docs/v2026-05-31/README.md": (
                "../../claude-review/docs/v2026-05-31/README.md",
            ),
            "claude-review/docs/v2026-05-28/README.md": (
                "../../claude-review/docs/v2026-05-28/README.md",
            ),
            "claude-review/docs/v2026-05-26/README.md": (
                "../../claude-review/docs/v2026-05-26/README.md",
            ),
        },
    ),
    AuthoritySection(
        "docs/opus-review/README.md",
        "## Authority Order",
        "## Boundaries",
        "Authority Order",
        required_current=(
            "docs/opus-review/HANDOFF.md",
            "wiki/review-backlog.md",
            "docs/codex-review/OPEN_RISKS.md",
            "docs/codex-review/QUALITY_GATES.md",
        ),
        historical=("docs/opus-review/OPUS_REVIEW_PACKET.md",)
        + HISTORICAL_REVIEW_ANCHORS,
    ),
    AuthoritySection(
        "docs/opus-review/HANDOFF.md",
        "live ledgers as the source of truth",
        "## Current Baseline",
        "Opus handoff live ledger order",
    ),
    AuthoritySection(
        "wiki/README.md",
        "## Current Recommended Entries",
        "## Current Baseline",
        "Current Recommended Entries",
    ),
    AuthoritySection(
        "wiki/project-overview.md",
        "## Current Execution Authority",
        "## ",
        "Current Execution Authority",
        historical=("docs/codex-review/CLAUDE_REFINED_SPEC.md",)
        + HISTORICAL_REVIEW_ANCHORS,
        anchor_aliases={
            "wiki/review-backlog.md": ("./review-backlog.md",),
            "docs/codex-review/OPEN_RISKS.md": (
                "../docs/codex-review/OPEN_RISKS.md",
            ),
            "docs/codex-review/QUALITY_GATES.md": (
                "../docs/codex-review/QUALITY_GATES.md",
            ),
            "docs/codex-review/CLAUDE_REFINED_SPEC.md": (
                "../docs/codex-review/CLAUDE_REFINED_SPEC.md",
            ),
        },
    ),
    AuthoritySection(
        "docs/claude-development-audit/README.md",
        "## Current Status Routing",
        "Use the reports and evidence snapshots",
        "Claude development audit current status routing",
    ),
    AuthoritySection(
        "docs/superpowers/plans/README.md",
        "Current review state is authoritative in this order:",
        "## Current Artifact Inventory",
        "Superpowers plan inventory authority order",
    ),
    AuthoritySection(
        "docs/superpowers/specs/README.md",
        "Current review state is authoritative in this order:",
        "## Current Artifact Inventory",
        "Superpowers spec inventory authority order",
    ),
)


def configured_authority_paths() -> tuple[str, ...]:
    return tuple(dict.fromkeys(section.relative_path for section in AUTHORITY_SECTIONS))


def find_authority_order_errors(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    section_configs = _sections_for_path(path)

    errors: list[str] = []
    for section_config in section_configs:
        marker_errors = _authority_section_marker_errors(text, section_config)
        if marker_errors:
            errors.extend(marker_errors)
            continue
        section_text, label = _authority_section_text(text, section_config)
        path_label = section_config.relative_path

        current_indexes: dict[str, int] = {}
        for current_anchor in section_config.required_current:
            current_index = _anchor_index(section_text, current_anchor, section_config)
            if current_index is None:
                errors.append(f"{path_label}: missing {current_anchor} in {label}")
                continue
            current_indexes[current_anchor] = current_index
            for historical_anchor in section_config.historical:
                historical_index = _anchor_index(
                    section_text, historical_anchor, section_config
                )
                if historical_index is not None and historical_index < current_index:
                    errors.append(
                        f"{path_label}: {current_anchor} must appear before "
                        f"{historical_anchor} in {label}"
                    )
        for earlier_index, earlier_anchor in enumerate(section_config.required_current):
            if earlier_anchor not in current_indexes:
                continue
            for later_anchor in section_config.required_current[earlier_index + 1 :]:
                if later_anchor not in current_indexes:
                    continue
                if current_indexes[later_anchor] < current_indexes[earlier_anchor]:
                    errors.append(
                        f"{path_label}: {earlier_anchor} must appear before "
                        f"{later_anchor} in {label}"
                    )
    return errors


def find_git_scope_routing_errors(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    section_configs = _sections_for_path(path)
    path_label = section_configs[0].relative_path
    marker_errors = [
        error
        for section_config in section_configs
        for error in _authority_section_marker_errors(text, section_config)
    ]
    if marker_errors:
        return marker_errors
    routing_text = "\n".join(
        _authority_section_text(text, section_config)[0]
        for section_config in section_configs
    )
    required_anchors = (
        OPUS_HANDOFF_GIT_SCOPE_ANCHORS
        if path_label == "docs/opus-review/HANDOFF.md"
        else GIT_SCOPE_ROUTING_ANCHORS
    )

    return [
        f"{path_label}: missing {anchor} in git review scope routing"
        for anchor in required_anchors
        if anchor not in routing_text
    ]


def check_authority_order(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_path in configured_authority_paths():
        path = repo_root / relative_path
        errors.extend(find_authority_order_errors(path))
        errors.extend(find_git_scope_routing_errors(path))
    return errors


def _sections_for_path(path: Path) -> tuple[AuthoritySection, ...]:
    normalized = path.as_posix()
    matches = tuple(
        section for section in AUTHORITY_SECTIONS if normalized.endswith(section.relative_path)
    )
    if matches:
        return matches
    return (
        AuthoritySection(
            path.name,
            "live ledgers as the source of truth",
            "## Current Baseline",
            "review authority order",
        ),
    )


def _section_for_path(path: Path) -> AuthoritySection:
    for section in AUTHORITY_SECTIONS:
        if path.as_posix().endswith(section.relative_path):
            return section
    return AuthoritySection(
        path.name,
        "live ledgers as the source of truth",
        "## Current Baseline",
        "review authority order",
    )


def _anchor_index(
    text: str, canonical_anchor: str, section: AuthoritySection
) -> int | None:
    candidates = (canonical_anchor,) + tuple(
        (section.anchor_aliases or {}).get(canonical_anchor, ())
    )
    indexes = [text.index(candidate) for candidate in candidates if candidate in text]
    if not indexes:
        return None
    return min(indexes)


def _authority_section_marker_errors(
    text: str, section: AuthoritySection
) -> list[str]:
    if section.start_marker not in text:
        return [
            f"{section.relative_path}: missing start marker "
            f"{section.start_marker} for {section.label}"
        ]
    section_text = text.split(section.start_marker, 1)[1]
    if section.end_marker not in section_text:
        return [
            f"{section.relative_path}: missing end marker "
            f"{section.end_marker} for {section.label}"
        ]
    return []


def _authority_section_text(
    text: str, section: AuthoritySection
) -> tuple[str, str]:
    if section.start_marker not in text:
        return text, section.label
    section_text = text.split(section.start_marker, 1)[1]
    if section.end_marker in section_text:
        section_text = section_text.split(section.end_marker, 1)[0]
    return section_text, section.label


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    errors = check_authority_order(repo_root)
    if errors:
        raise SystemExit("\n".join(errors))
    print("review authority order ok")


if __name__ == "__main__":
    main()
