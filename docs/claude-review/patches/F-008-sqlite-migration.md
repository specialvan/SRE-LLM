# Patch · F-008 SQLite migration 正常化

## 当前代码锚点

### `gan_matchmaking/persistence/sqlite.py`（L164-200 附近）

```python
def _migrate(self) -> None:
    with self._lock:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT, applied_at REAL)"
        )
        applied = {row["version"] for row in self._conn.execute(
            "SELECT version FROM schema_migrations")}
        for version, name, sql in _MIGRATIONS:
            if version in applied:
                continue
            if version == 5:
                # ---- 特判 ---------------------------------------------
                cols = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(decisions)")
                }
                if "artifact_version" in cols:
                    # 列已存在(手工改过的老库)→仅写 migration 记录
                    self._conn.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) "
                        "VALUES(?,?,?)", (version, name, time.time()))
                    continue
                # ---- /特判 --------------------------------------------
            self._conn.executescript(sql)
            self._conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES(?,?,?)", (version, name, time.time()))
        self._conn.commit()
```

问题：
1. v5 的"列已存在跳过 DDL"逻辑用 `if version == 5:` 内联，未来每加一
   次列都会复制这个模式
2. 对老库的兼容性没有 ADR 引用
3. 没有 idempotent guarantee（同一 DDL 二次跑会炸）

## 目标代码

### 选项 A · 用 SQLite 3.35+ `ADD COLUMN IF NOT EXISTS`（推荐）

修改 `_MIGRATIONS` 表里 v5 的 SQL：

```python
_MIGRATIONS: list[tuple[int, str, str]] = [
    # ...v1-v4...
    (
        5,
        "add_decision_artifact_version",
        """
        ALTER TABLE decisions ADD COLUMN IF NOT EXISTS artifact_version TEXT;
        """,
    ),
]
```

`_migrate` 彻底删除特判：

```python
def _migrate(self) -> None:
    with self._lock:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT, applied_at REAL)"
        )
        applied = {row["version"] for row in self._conn.execute(
            "SELECT version FROM schema_migrations")}
        for version, name, sql in _MIGRATIONS:
            if version in applied:
                continue
            self._conn.executescript(sql)
            self._conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES(?,?,?)", (version, name, time.time()))
        self._conn.commit()
```

### 选项 B · 兼容 SQLite < 3.35（若目标部署不保证版本）

保留声明式结构，但把"是否需要 DDL"下沉到一个统一的 helper：

```python
def _migrate(self) -> None:
    with self._lock:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT, applied_at REAL)"
        )
        applied = {row["version"] for row in self._conn.execute(
            "SELECT version FROM schema_migrations")}
        for version, name, idempotent_sql in _MIGRATIONS:
            if version in applied:
                continue
            self._apply_idempotent_sql(idempotent_sql)
            self._conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES(?,?,?)", (version, name, time.time()))
        self._conn.commit()

def _apply_idempotent_sql(self, sql: str) -> None:
    """Apply SQL that must succeed even if some objects already exist."""
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        m = re.match(
            r"^ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)\s+(.+)$",
            stmt, re.IGNORECASE,
        )
        if m:
            table, column, coltype = m.groups()
            existing = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({table})")
            }
            if column in existing:
                continue
        self._conn.execute(stmt)
```

两个选项都消除了"某个特定版本号的 inline 特判"，属于统一机制。

## 预计 LOC

| 路径 | +/- |
|---|---|
| `persistence/sqlite.py` | +15 / -20（选项 A）或 +40 / -20（选项 B）|
| `tests/test_persistence_sqlite.py` | +80 / -0 |
| **合计** | **+95 / -20** 或 **+120 / -20** |

## 测试骨架

```python
# tests/test_persistence_sqlite.py

import sqlite3
import pytest
from pathlib import Path

from gan_matchmaking.persistence import SQLitePipelineStore


def test_migration_v5_idempotent_on_legacy_db(tmp_path: Path):
    """老库手工加过 artifact_version 列，启动不应爆。"""
    db_path = tmp_path / "legacy.sqlite"

    # 1. 手工构造 v4 schema + 已手动加过 artifact_version 列
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript("""
            CREATE TABLE decisions (
                correlation_id TEXT PRIMARY KEY,
                kind TEXT,
                risk_level TEXT,
                risk_prob REAL,
                confidence REAL,
                chosen_id TEXT,
                rationale_json TEXT,
                trace_json TEXT,
                created_at REAL,
                artifact_version TEXT  -- 手工加的列
            );
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY, name TEXT, applied_at REAL);
            INSERT INTO schema_migrations VALUES
                (1, 'init', 0), (2, 'x', 0), (3, 'y', 0), (4, 'z', 0);
        """)
        conn.commit()
    finally:
        conn.close()

    # 2. 启动 store，应无异常
    store = SQLitePipelineStore(db_path)
    try:
        # 3. v5 应被记录
        versions = [
            row["version"]
            for row in store._conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version")
        ]
        assert 5 in versions
    finally:
        store.close()


def test_migration_v5_on_empty_db(tmp_path: Path):
    """空库启动后全部 migration 到位。"""
    db_path = tmp_path / "fresh.sqlite"
    store = SQLitePipelineStore(db_path)
    try:
        cols = {
            row["name"]
            for row in store._conn.execute("PRAGMA table_info(decisions)")
        }
        assert "artifact_version" in cols
        versions = [
            row["version"]
            for row in store._conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version")
        ]
        # 假设最新是 v5
        assert versions == [1, 2, 3, 4, 5]
    finally:
        store.close()


def test_no_version_specific_branches_in_migrate():
    """确保不再出现 if version == N 的内联特判。"""
    from pathlib import Path
    src = Path("gan_matchmaking/persistence/sqlite.py").read_text(
        encoding="utf-8")
    # 允许在文档字符串 / 注释里引用 v5，只排除代码层特判
    import re
    code_branches = re.findall(r"^\s*if\s+version\s*==\s*\d+", src, re.MULTILINE)
    assert code_branches == [], \
        f"version-specific branches leaked back: {code_branches}"


def test_double_start_is_idempotent(tmp_path: Path):
    """连续两次 open 同一个 db，不抛异常，schema_migrations 无重复行。"""
    db_path = tmp_path / "double.sqlite"
    store1 = SQLitePipelineStore(db_path)
    store1.close()
    store2 = SQLitePipelineStore(db_path)
    try:
        counts = {
            row["version"]: 1
            for row in store2._conn.execute(
                "SELECT version, COUNT(*) AS n FROM schema_migrations "
                "GROUP BY version")
        }
        assert all(v == 1 for v in counts.values())
    finally:
        store2.close()
```
