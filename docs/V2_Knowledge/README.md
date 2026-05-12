# V2 Knowledge Base · Agent Navigation Index

> V2 的定位与 V1 (`docs/knowledge-base.html`) 明确不同：
>
> | | V1 | V2 |
> | --- | --- | --- |
> | **角色** | 教科书式深度拆解 | 接手 agent 的导航图 |
> | **节数** | 27 节 + 附录 | 7 个 zone（每 zone 一张图 + 一个表） |
> | **篇幅** | 160 KB | ≤ 40 KB |
> | **读者** | 第一次学这个课题的工程师 | 中途接手的 AI agent / 新 reviewer |
> | **更新频率** | 新机制落地时扩 | 每次 handoff 或 review 同步 |
> | **优先回答** | "这个机制是什么" | "现在我该读/改哪个文件" |

---

## Files

| File | Purpose |
| --- | --- |
| [`index.html`](./index.html) | **入口**。单页导航 HTML，7 个 zone + 状态摘要 + 文件指路牌 |
| [`state.json`](./state.json) | 机器可读的当前状态快照（tests / demos / modules / open actions / invariants） |
| [`_regenerate_state.py`](./_regenerate_state.py) | 重建 state.json 客观字段的脚本（`--dry-run` / `--write`） |
| [`README.md`](./README.md) | 你正在看的这份 |

---

## How an agent should use this

1. **打开 [`index.html`](./index.html)** — 2 分钟建立全貌。
2. **如果目标是 evaluate**（reviewer）：
   - 先看 Zone 7 (Current Status)
   - 再看 Zone 6 (Open Actions) 了解已知问题
   - 必要时跳转 `docs/claude-review/` 深读
3. **如果目标是 develop**（codex）：
   - 先看 Zone 7 (Current Status) 确认 baseline
   - 再看 Zone 6 (Open Actions) 选一条 P1 开干
   - 跟 `docs/claude-review/02-action-items.md` 对照实现
4. **如果目标是 understand**（深入学习）：
   - 打开 V1 `docs/knowledge-base.html`
   - 本 V2 只做索引作用

## Where to find what

| 如果想知道… | 去这里 |
| --- | --- |
| 整个系统的 7 层架构 | `index.html` Zone 1 |
| 每个模块对应哪篇论文段落 | `index.html` Zone 2 |
| Attention Residuals 机制的数学/实现 | V1 `knowledge-base.html` §02–§11 |
| SRE 控制原语的公式推导 | V1 `knowledge-base.html` §12–§20 |
| 自学习外壳细节 | V1 `knowledge-base.html` §21–§26 |
| 现在有什么未解决问题 | `claude-review/02-action-items.md` |
| 完整模块源码位置 | `index.html` Zone 3 |
| 所有 demo 一键跑通 | `index.html` Zone 4 |

---

## Regeneration policy

V2 不要手工长期维护。下一次重大 handoff 时由 reviewer 重建一次快照：

- 运行 `python docs/V2_Knowledge/_regenerate_state.py`（dry-run）看 diff
- 运行 `python docs/V2_Knowledge/_regenerate_state.py --write` 落盘
- 手工更新 `snapshot_date` / `snapshot_author` / 过时的 `open_actions`
- 在 CODEX-HANDOFF.md 的"变更日志"里补一行

这个脚本只重写 **客观字段**：
- `repository.head_commit_short` / `head_commit_subject`
- `health.tests_total` / `demos_total`
- `demos[]` / `docs[]`（保留已有 `purpose` 文案）
- `public_api_symbols[]`（从 `__init__.py` 的 `__all__` 解析）

**不碰** 的字段（reviewer-curated，需要语义判断）：
`hard_invariants` / `pr_review_guardrails` / `open_actions` / `open_gaps` /
`layers` / `closed_loops` / `notes_for_next_agent`。

### 范围过滤

脚本会跳过：
- `tests/skill/` 目录下的测试（属于并行的 skill-research feature）
- `examples/demo_skillops_*.py`（同上）

如果未来有新的并行 feature 混进 `tests/` 或 `examples/`，请在
`_regenerate_state.py` 里扩展 `count_tests` 和 `list_demos` 的过滤列表。

### 如果你看到 state.json 与 live repo 不一致

这是**预期的**。snapshot 定格在某个 commit（见 `repository.head_commit_short`），
而 live repo 在持续前进。两种情况：
1. codex 正在执行 `open_actions` → 不要重新生成，等 P1 全部关闭再 snapshot。
2. 一个 review cycle 结束 → 跑 `--write` 重新生成，更新 snapshot_date 手填。
