"""Skill version DAG · PR-013.

Refined spec: ``skill-research/refined/PR-013-skill-version-graph-refined.md``.

Implements:

* ``commit(version)`` — O(|parents|); rejects self-parent, dangling
  parent and id collisions with different content (but is idempotent on
  identical re-commits).
* ``ancestors(v)`` / ``descendants(v)`` — DFS + memoisation.
* ``merge_base(a, b)`` — lowest common ancestor by graph depth.
* ``revert_to(target)`` — creates a new ``SkillVersion`` whose parents
  are ``(target, current_head)``; HEAD moves to the new node.
* Three HEAD pointers per ``(skill_id, tenant)``.

Requirements covered:

* REQ-GOV-002 · 3 HEAD pointers
* REQ-GOV-005 · revert_to emits new version with both parents
* REQ-GOV-010 · ancestors/descendants < 10 ms on 1000 nodes

Complexity (N = node count, E = edge count):

* ``commit``        : O(|parents|)  amortised O(1)
* ``ancestors``     : cold O(N+E); hot O(1) via LRU memo
* ``merge_base``    : two ``ancestors`` calls + set intersection
* ``revert_to``     : single ``commit``
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Dict, FrozenSet, Iterator, Optional, Set, Tuple

from attention_residuals.skill.types import (
    BlastRadius,
    ChangeKind,
    SkillVersion,
    compute_version_id,
)


class HeadName(str, Enum):
    SANDBOX = "sandbox_head"
    QUARANTINE = "quarantine_head"
    ACTIVE = "active_head"


@dataclass(frozen=True)
class HeadRefs:
    """Three HEAD pointers for one ``(skill_id, tenant)`` pair."""

    sandbox_head: Optional[str] = None
    quarantine_head: Optional[str] = None
    active_head: Optional[str] = None

    def with_head(self, name: HeadName, version_id: Optional[str]) -> "HeadRefs":
        return replace(self, **{name.value: version_id})


@dataclass
class _Node:
    version: SkillVersion
    children: Set[str]


class SkillVersionGraph:
    """DAG of :class:`SkillVersion` nodes plus per-skill HEAD pointers."""

    def __init__(self) -> None:
        self._nodes: Dict[str, _Node] = {}
        self._heads: Dict[Tuple[str, str], HeadRefs] = {}
        self._lock = threading.RLock()
        self._ancestor_cache: Dict[str, FrozenSet[str]] = {}
        self._descendant_cache: Dict[str, FrozenSet[str]] = {}
        self._depth_cache: Dict[str, int] = {}

    # ---------------- Commit ----------------

    def commit(self, version: SkillVersion) -> None:
        """Insert ``version`` into the graph.

        - Idempotent if an identical version already exists.
        - Raises ``ValueError`` on id collision with different content,
          self-parent, or dangling parent.
        """
        with self._lock:
            existing = self._nodes.get(version.version_id)
            if existing is not None:
                if existing.version == version:
                    return  # idempotent
                raise ValueError(
                    f"version_id {version.version_id!r} already exists with different content"
                )
            if version.version_id in version.parents:
                raise ValueError("SkillVersion cannot be its own parent")
            for p in version.parents:
                if p not in self._nodes:
                    raise ValueError(f"dangling parent: {p!r}")

            self._nodes[version.version_id] = _Node(version=version, children=set())
            for p in version.parents:
                self._nodes[p].children.add(version.version_id)

            # Invalidate caches — new node may alter every ancestor/descendant set
            self._ancestor_cache.clear()
            self._descendant_cache.clear()
            self._depth_cache.clear()

    # ---------------- Queries ----------------

    def ancestors(self, v: str) -> FrozenSet[str]:
        """Set of all transitively-reachable parents (excluding ``v``)."""
        with self._lock:
            cached = self._ancestor_cache.get(v)
            if cached is not None:
                return cached
            if v not in self._nodes:
                raise KeyError(v)
            result = self._traverse(v, lambda n: n.version.parents)
            result.discard(v)
            frozen = frozenset(result)
            self._ancestor_cache[v] = frozen
            return frozen

    def descendants(self, v: str) -> FrozenSet[str]:
        """Set of all transitively-reachable children (excluding ``v``)."""
        with self._lock:
            cached = self._descendant_cache.get(v)
            if cached is not None:
                return cached
            if v not in self._nodes:
                raise KeyError(v)
            result = self._traverse(v, lambda n: tuple(n.children))
            result.discard(v)
            frozen = frozenset(result)
            self._descendant_cache[v] = frozen
            return frozen

    def merge_base(self, a: str, b: str) -> Optional[str]:
        """Lowest common ancestor by depth; None if disjoint components."""
        if a not in self._nodes or b not in self._nodes:
            raise KeyError((a, b))
        if a == b:
            return a
        anc_a = self.ancestors(a) | {a}
        anc_b = self.ancestors(b) | {b}
        common = anc_a & anc_b
        if not common:
            return None
        return max(common, key=self._depth)

    def is_divergent(self, a: str, b: str) -> bool:
        base = self.merge_base(a, b)
        if base is None:
            return True
        return base != a and base != b

    def nodes(self) -> Iterator[SkillVersion]:
        return (n.version for n in self._nodes.values())

    def __contains__(self, version_id: str) -> bool:
        return version_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    # ---------------- HEAD pointers ----------------

    def get_heads(self, skill_id: str, tenant: str = "default") -> HeadRefs:
        return self._heads.get((skill_id, tenant), HeadRefs())

    def move_head(
        self,
        skill_id: str,
        head: HeadName,
        version_id: Optional[str],
        tenant: str = "default",
    ) -> HeadRefs:
        with self._lock:
            if version_id is not None and version_id not in self._nodes:
                raise KeyError(version_id)
            cur = self.get_heads(skill_id, tenant)
            new = cur.with_head(head, version_id)
            self._heads[(skill_id, tenant)] = new
            return new

    # ---------------- Revert ----------------

    def revert_to(
        self,
        target: str,
        skill_id: str,
        author: str = "system",
        tenant: str = "default",
        summary: Optional[str] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> SkillVersion:
        """Emit a new ``SkillVersion`` with parents ``(target, active_head)``.

        Sets ``active_head`` to the new version. If ``target`` equals the
        current ``active_head``, still creates a no-op revert commit (so
        the event chain is auditable).

        REQ-GOV-005 · revert emits new version whose parents include both.
        """
        with self._lock:
            if target not in self._nodes:
                raise KeyError(target)
            target_node = self._nodes[target]
            if target_node.version.skill_id != skill_id:
                raise ValueError(
                    f"target {target!r} belongs to skill "
                    f"{target_node.version.skill_id!r}, not {skill_id!r}"
                )

            heads = self.get_heads(skill_id, tenant)
            current = heads.active_head
            parents = (target,) if current is None or current == target else (target, current)

            ts = (now or time.time)()
            summary_text = summary or f"revert to {target[:8]}"
            # Blast radius of a revert inherits from the target version (we
            # are "going back" to its surface area).
            blast = target_node.version.blast_radius

            # Revert hash includes timestamp so that two reverts of the
            # same target from the same current head produce distinct
            # version_ids (normal commits are time-free; reverts aren't).
            revert_vid = compute_version_id(
                skill_id=skill_id,
                targets=(),
                parents=list(parents) + [f"revert@{ts:.9f}"],
                author=author,
            )
            revert = SkillVersion(
                version_id=revert_vid,
                skill_id=skill_id,
                parents=parents,
                author=author,
                timestamp=ts,
                summary=summary_text[:80],
                change_kind=ChangeKind.REVERT,
                blast_radius=blast,
            )
            self.commit(revert)
            self.move_head(skill_id, HeadName.ACTIVE, revert.version_id, tenant)
            return revert

    # ---------------- Internals ----------------

    def _traverse(
        self,
        start: str,
        neighbours: Callable[[_Node], Tuple[str, ...]],
    ) -> Set[str]:
        seen: Set[str] = {start}
        stack = deque([start])
        while stack:
            cur = stack.pop()
            node = self._nodes[cur]
            for nb in neighbours(node):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return seen

    def _depth(self, v: str) -> int:
        """Longest path from a root to ``v``."""
        cached = self._depth_cache.get(v)
        if cached is not None:
            return cached
        node = self._nodes[v]
        if not node.version.parents:
            d = 0
        else:
            d = 1 + max(self._depth(p) for p in node.version.parents)
        self._depth_cache[v] = d
        return d


__all__ = ["HeadName", "HeadRefs", "SkillVersionGraph"]
