"""Lint review entrypoints so current ledgers stay before historical packets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CURRENT_LEDGER_ANCHORS = (
    "docs/codex-review/OPEN_RISKS.md",
    "wiki/review-backlog.md",
)
HISTORICAL_REVIEW_ANCHORS = (
    "docs/opus-review/OPUS_REVIEW_PACKET.md",
    "claude-review/docs/v2026-05-28/README.md",
    "claude-review/docs/v2026-05-26/README.md",
)


@dataclass(frozen=True)
class AuthoritySection:
    relative_path: str
    start_marker: str
    end_marker: str
    label: str
    required_current: tuple[str, ...] = CURRENT_LEDGER_ANCHORS
    historical: tuple[str, ...] = HISTORICAL_REVIEW_ANCHORS


AUTHORITY_SECTIONS = (
    AuthoritySection(
        "docs/opus-review/HANDOFF.md",
        "## 当前权威锚点",
        "## 当前基线",
        "当前权威锚点",
    ),
    AuthoritySection(
        "wiki/README.md",
        "## Current Recommended Entries",
        "## Current Baseline",
        "Current Recommended Entries",
    ),
)


def configured_authority_paths() -> tuple[str, ...]:
    return tuple(section.relative_path for section in AUTHORITY_SECTIONS)


def find_authority_order_errors(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    section_config = _section_for_path(path)
    section_text, label = _authority_section_text(text, section_config)

    errors: list[str] = []
    for current_anchor in section_config.required_current:
        if current_anchor not in section_text:
            errors.append(f"{path.name}: missing {current_anchor} in {label}")
            continue
        current_index = section_text.index(current_anchor)
        for historical_anchor in section_config.historical:
            if historical_anchor in section_text and section_text.index(historical_anchor) < current_index:
                errors.append(
                    f"{path.name}: {current_anchor} must appear before "
                    f"{historical_anchor} in {label}"
                )
    return errors


def _section_for_path(path: Path) -> AuthoritySection:
    normalized = path.as_posix()
    for section in AUTHORITY_SECTIONS:
        if normalized.endswith(section.relative_path):
            return section
    return AuthoritySection(
        path.name,
        "## 当前权威锚点",
        "## 当前基线",
        "当前权威锚点",
    )


def _authority_section_text(
    text: str, section: AuthoritySection
) -> tuple[str, str]:
    if section.start_marker not in text:
        return text, section.label
    section_text = text.split(section.start_marker, 1)[1]
    if section.end_marker in section_text:
        section_text = section_text.split(section.end_marker, 1)[0]
    return section_text, section.label

