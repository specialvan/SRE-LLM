"""Lint review entrypoints so current ledgers stay before historical packets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


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
    anchor_aliases: dict[str, tuple[str, ...]] | None = None


AUTHORITY_SECTIONS = (
    AuthoritySection(
        'docs/codex-review/README.md',
        '## Reading Order',
        '## Current Baseline',
        'Reading Order',
        anchor_aliases={
            'docs/codex-review/OPEN_RISKS.md': ('OPEN_RISKS.md', './OPEN_RISKS.md'),
            'wiki/review-backlog.md': ('../../wiki/review-backlog.md',),
            'docs/opus-review/OPUS_REVIEW_PACKET.md': ('../opus-review/OPUS_REVIEW_PACKET.md',),
            'claude-review/docs/v2026-05-28/README.md': ('../../claude-review/docs/v2026-05-28/README.md',),
            'claude-review/docs/v2026-05-26/README.md': ('../../claude-review/docs/v2026-05-26/README.md',),
        },
    ),
    AuthoritySection(
        'docs/opus-review/OPUS_REVIEW_PACKET.md',
        '## 0. Review Position',
        '## 1. Verification Snapshot For Current Handoff',
        'Review Position',
    ),
    AuthoritySection(
        "docs/opus-review/README.md",
        "## 首读文件",
        "## 历史输入",
        "首读文件",
        anchor_aliases={
            "docs/codex-review/OPEN_RISKS.md": (
                "../codex-review/OPEN_RISKS.md",
            ),
            "wiki/review-backlog.md": ("../../wiki/review-backlog.md",),
            "docs/opus-review/OPUS_REVIEW_PACKET.md": (
                "OPUS_REVIEW_PACKET.md",
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
        current_index = _anchor_index(section_text, current_anchor, section_config)
        if current_index is None:
            errors.append(f"{path.name}: missing {current_anchor} in {label}")
            continue
        for historical_anchor in section_config.historical:
            historical_index = _anchor_index(
                section_text, historical_anchor, section_config
            )
            if historical_index is not None and historical_index < current_index:
                errors.append(
                    f"{path.name}: {current_anchor} must appear before "
                    f"{historical_anchor} in {label}"
                )
    return errors


def check_authority_order(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_path in configured_authority_paths():
        errors.extend(find_authority_order_errors(repo_root / relative_path))
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
