# V3 Knowledge Base · Agent & Developer Navigation

> V3 在 V2 基础上增加了**可视化深度**和**决策辅助**，同时保持 agent-first 的导航定位。

| | V1 | V2 | V3 |
| --- | --- | --- | --- |
| **角色** | 教科书式深度拆解 | 接手 agent 的导航图 | 导航图 + 决策辅助 + 可视化 |
| **节数** | 27 节 + 附录 | 7 个 zone | 9 个 zone（+依赖图 +闭环流 +变更日志） |
| **篇幅** | 160 KB | ~40 KB | ~60 KB |
| **读者** | 第一次学这个课题的工程师 | 中途接手的 AI agent | AI agent + 人类 reviewer + 新开发者 |
| **更新频率** | 新机制落地时扩 | 每次 handoff 同步 | 每次 handoff 同步 |
| **优先回答** | "这个机制是什么" | "现在我该读/改哪个文件" | "现在状态 + 下一步 + 为什么这样设计" |

---

## V3 相比 V2 的增量

1. **Z8 · Dependency & interaction graph** — 模块间依赖关系 SVG，一眼看出改一个文件会影响哪些
2. **Z9 · Changelog & evolution** — 从 R1 到当前的变更日志，带 diff 统计
3. **Z1 架构图升级** — 增加闭环数据流 SVG（不只是层级，还有 tick 内的数据路径）
4. **Z5 不变量增加"破坏影响"列** — 帮助 agent 评估风险
5. **Z7 增加 open_gaps 可视化** — 让 agent 知道哪些能力还没有
6. **Print CSS 优化** — A4 打印友好

---

## Files

| File | Purpose |
| --- | --- |
| [`index.html`](./index.html) | **入口**。单页导航 HTML，9 个 zone + 全部 SVG 内联 |
| [`state.json`](./state.json) | 机器可读的当前状态快照（与 V2 共享同一份，symlink 或 copy） |
| [`README.md`](./README.md) | 你正在看的这份 |

---

## How an agent should use this

1. **打开 [`index.html`](./index.html)** — 3 分钟建立全貌 + 依赖关系。
2. **如果目标是 evaluate**（reviewer）：
   - Z7 (Status) → Z6 (Actions) → Z5 (Invariants) → Z8 (Dependencies)
   - 必要时跳转 `docs/claude-review/` 深读
3. **如果目标是 develop**（codex / 新 agent）：
   - Z7 (Status) → Z8 (Dependencies，看改动影响面) → Z6 (Actions，选任务) → Z4 (Demos，验证)
4. **如果目标是 understand**（深入学习）：
   - 打开 V1 `docs/knowledge-base.html`
   - 本 V3 只做索引 + 决策辅助

## Regeneration policy

与 V2 相同。state.json 是 SSOT，index.html 从 state.json 派生。
重大 handoff 时由 reviewer 重建快照：

```powershell
python docs\V2_Knowledge\_regenerate_state.py --write
# 然后手动 copy state.json 到 V3_Knowledge/ 或保持引用 V2 的
```

---

## Version history

| Version | Date | Author | Headline |
| --- | --- | --- | --- |
| V1 | 2026-05 | Claude R1-R2 | 27 节深度拆解 + 30 SVG |
| V2 | 2026-05-12 | Claude R10 | 7 zone agent 导航 |
| V3 | 2026-05-12 | Claude R10 close-out | 9 zone + 依赖图 + 闭环流 + changelog |
