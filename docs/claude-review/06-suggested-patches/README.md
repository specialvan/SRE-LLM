# Suggested Patches

下列补丁是 review 附带的**可直接 cherry-pick 的骨架**。不包含完整实现，目的是给 Codex 一个"照这个风格写"的起点。

| 文件 | Action Item | 目的 |
| --- | --- | --- |
| [01-barrier-aware-policy.md](./01-barrier-aware-policy.md) | AI-02 | 把 GradientPolicy 升级为能预测 barrier 的 predict-then-brake 策略 |
| [02-benchmark-ci.md](./02-benchmark-ci.md) | AI-14 | 把 benchmark 产物固化为 CI artifact |
| [03-benchmark-assertions.md](./03-benchmark-assertions.md) | AI-01 | 给 benchmark metrics 加 SLO 红线断言 |
| [04-status-enums.md](./04-status-enums.md) | AI-03b | 锁 status 枚举并加 assert |
| [05-ci-invariants.md](./05-ci-invariants.md) | AI-11 | grep-based invariant 扫描脚本 |

## 使用方式

每个 patch 文件都是<strong>可阅读的 markdown + 可复制的 code block</strong>。Codex 应该：

1. 先读整个 patch 文件（理解动机）；
2. 按 `## 实现步骤` 里的顺序落代码；
3. 每一步都先跑 pytest 再进下一步；
4. 完成后回 [05-action-items.md](../05-action-items.md) 更新进度。
