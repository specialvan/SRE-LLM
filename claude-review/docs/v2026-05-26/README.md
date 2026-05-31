# Opus v2.0 深度评审报告（2026-05-26） · Historical Opus v2.0 Review Packet

> Historical packet from the 2026-05-26 Opus deep review; it is not the current handoff.
> Opus review should start from `docs/opus-review/HANDOFF.md`, then verify
> live status in `wiki/review-backlog.md`,
> `docs/codex-review/OPEN_RISKS.md`, and
> `docs/codex-review/QUALITY_GATES.md`.

> 本目录是对 codex 工程包的第二轮深度评审产出。入口契约为
> `docs/opus-review/OPUS_REVIEW_PACKET.md`；本轮基于该 packet 重跑 quality
> gates、核验 14 项 P2/P3 已声明 resolved 的 findings、Spot-check 5 项 P0/P1
> 已声明 resolved 的 findings，并独立寻找 11 项新隐患（编号从 F50 起，以
> 区别于 v1.0 的 F01–F42）。

## 文档清单

| 文件 | 用途 |
|---|---|
| `00-executive-brief.md` | 评审结论摘要、合并门禁判定 |
| `01-scope-and-baseline.md` | 评审范围、入口文档、版本基线 |
| `02-resolved-findings-spot-check.md` | 对 v1.0 已声明 resolved 项的逐项 line-level 复核 |
| `03-new-findings.md` | 本轮独立审计发现的 11 项新隐患（F50–F60） |
| `04-evidence-manifest-audit.md` | 证据制品 / manifest / 报告 CLI / 测试一致性核验 |
| `05-merge-gate-checklist.md` | 当前快照能否合入主线的门禁判断 |
| `evidence/verification-rerun-2026-05-26.md` | 重跑命令实测输出与时间戳记录 |

## 关键结论

1. **Quality gates 全绿**：276 passed / 12 studies / `artifact_check ok studies=3 files=8`。
2. **v1.0 已声明 resolved 项基本属实**：14/14 P2/P3 项验证通过；F02 存在 1 处
   边界缝隙（`_matrix()` 调用位于 try 外）；F39 描述与实现机制有出入但行为正确；
   其余 P0/P1 项 F01/F03/F04/F25/F05 全部 HOLDS。
3. **新发现 11 项隐患**：其中 4 项 P1（autoscaler 单位错配、稳定性监控反向差分
   滞后、`stability_violation` 仅为装饰、Guardrail 静默放过 NaN），3 项 P2、4
   项 P3。详见 `03-new-findings.md`。
4. **证据流程陷阱（来自 manifest 审计）**：`s11_catch_sre_wrapper.png` 等
   matplotlib 制品在不同机器上 byte-identity 易漂移；reviewer 必须按 packet
   提示先跑 `analysis.evidence_manifest` 再跑 `analysis.evidence_report`，否则
   会复现一次假阴性。建议加入自愈合 / PNG 确定化措施。
5. **合并建议**：当前快照可作为研究阶段 PR 合入，但应在合入前至少修复
   F50/F51/F53/F54 四项 P1 findings 或显式记录到 OPEN_RISKS。

## 与全局规则的关系

- 已遵守 `~/.claude/CLAUDE.md` 关于"评审报告沉淀到 `claude-review/` 并按版本
  区分"的要求。
- 已在 `wiki/` 与 `docs/opus-review/` 之外新增本目录，不覆盖历史 v1.0 评审产出。
- 评审报告以中文撰写，便于跨会话复盘；引用 file:line 时保持英文路径与原始 ID。
