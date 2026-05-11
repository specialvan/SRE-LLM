# Spec · codex 可执行版

本目录是 `docs/claude-review/` 的"可执行"层。前几份文档（评审报告、findings、
action-items、test-coverage-gaps）告诉你 **what & why**；本目录告诉你
**exactly what to patch**。

## 本轮覆盖范围（B + A2 方案）

只覆盖**合入前 P1 + 上产前 P2** 三条 finding：

- [F-001](../findings.md#f-001--leaserefreshloop-续租失败静默化) — `LeaseRefreshLoop` 续租失败必须翻转 readiness
- [F-002](../findings.md#f-002--shadow-rewrite-导致监控日志与最终决策不一致) — Shadow rewrite 后 metrics/log 与最终 kind 对齐
- [F-003](../findings.md#f-003--traceinputconfig-无-allowlist未来易泄密) — `trace.input.config` 走 allowlist，防泄密

其余 findings（F-004 ~ F-010）仍按 `action-items.md` 的推荐顺序推进，
只是不在本轮 spec 范围内。

## 文件

| 文件 | 作用 | 格式 |
|---|---|---|
| [`requirements.md`](requirements.md) | 每条 finding 转成 EARS-A2 acceptance criteria | `WHEN ... THE SYSTEM SHALL ...` |
| [`design.md`](design.md) | 每个修复的组件变更 + mermaid 图 + 调用时序 | 结构化说明 |
| [`tasks.md`](tasks.md) | 按依赖排序的 checkbox 任务清单 | TODO 列表 |
| [`verification.md`](verification.md) | 每条 finding 的验证命令 + metric/log 快照 | 跑完就能 close finding |

## codex 使用约定

- **执行顺序**: 从 `tasks.md` 进入，每勾掉一个 checkbox 就跑一次对应验证命令。
- **PR 描述**: 必须引用 finding id（`F-001`）+ 满足的 requirement id（`R-001`）。
- **完结动作**: PR merge 后，把 `findings.md` 里对应条目的 `status: open`
  改成 `status: resolved (commit <sha>)`，`tasks.md` 里所有 checkbox 勾掉。
- **verification 失败的处理**: 不改 verification.md，改自己的代码；
  verification 本身是契约。
- **新增 finding**: 追加到 `findings.md`，对应在 spec 里开新一轮
  （比如 `spec/v2/`），不动本轮 spec。

## patches 目录

[`../patches/`](../patches/) 里放了 F-001/F-002/F-003 的 **before/after
代码片段 + 测试 shape**。每个 patch 文件都是"可直接 git apply"的颗粒度——
codex 拿到不需要再推导位置。

## 完成标准（Definition of Done）

**本轮 spec 全部关闭**的充要条件：

1. 所有 `requirements.md` 里的 R-00x 都有对应测试覆盖且通过
2. `tasks.md` 里所有 checkbox 勾掉
3. `verification.md` 里所有命令绿色
4. `findings.md` 中 F-001/F-002/F-003 的 status 全部为 `resolved`
5. 完整 `pytest -q` 绿色
6. `python -m bench.latency --quick` p99 < 2.5ms（允许 +0.8ms 回归余量）
7. 新增一条 `docs/claude-review/YYYY-MM-spec-completion.md` 记录本轮收尾
