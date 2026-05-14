# Spec v4 · E-008 Incident Replay Expansion

本 spec 扩展 incident-style replay 覆盖率，覆盖以下场景：

## Background

Spec-v3 (2026-07) 完成了 192 测试，replay corpus 已有 29 个场景。
Spec-v4 继续扩展以下场景类别的覆盖度：

1. **Advisory mode 过渡场景**：shadow → advisory → full 状态转换
2. **Artifact metadata 失败场景**：invalid shape、missing fields、version mismatch
3. **Breaker open 短路场景**：故障时的快速降级行为
4. **Lease loss drain 行为**：writer lease 丢失后的处理

## Scope

- 不改变 Decision / ReleaseContext 公共 API
- 不改变 trace schema
- 新增 fixture 必须满足 naming contract (R-821/R-822)
- 新增测试必须 deterministic

## Requirements

### R-840 · Advisory mode transition fixtures

**WHEN** 需要扩展 replay corpus 覆盖度，
**THE SYSTEM SHALL** 新增至少 3 个 advisory mode 相关 fixtures：
- `advisory_enter.json` - 从 shadow/observe 进入 advisory
- `advisory_hold.json` - advisory 模式下 decision=hold
- `advisory_promote.json` - advisory 升级为 full deployment

**验证**: `test_replay_corpus.py` 参数化 corpus 覆盖这些 fixtures

### R-841 · Artifact metadata failure fixtures

**WHEN** 需要覆盖 artifact validation 失败路径，
**THE SYSTEM SHALL** 新增至少 2 个 metadata failure fixtures：
- `artifact_metadata_invalid_shape.json` - feature names 不匹配
- `artifact_bundle_corrupt.json` - bundle 内部文件损坏

**验证**: `test_replay_corpus.py` 覆盖，fixture 名称符合 naming contract

### R-842 · Breaker open short-circuit fixtures

**WHEN** 需要覆盖熔断器触发场景，
**THE SYSTEM SHALL** 新增至少 2 个 breaker open fixtures：
- `breaker_fast_open.json` - 快速打开熔断器
- `breaker_half_open.json` - 半开状态尝试恢复

**验证**: 同 R-840

### R-843 · Lease loss drain behavior fixture

**WHEN** 需要覆盖 writer lease 丢失场景，
**THE SYSTEM SHALL** 新增 1 个 lease failure fixture：
- `lease_loss_drain.json` - lease 丢失触发 traffic drain

**验证**: fixture 包含 lease health 相关断言

## Out of Scope

- 不实现新的 training 功能
- 不实现新的 persistence 存储
- 不修改已有 fixture 的 expected.kind

## Dependencies

- Spec-v3 PR-test-01 (fixture naming hardening) 必须先完成

## Status

- [x] R-840: Advisory mode fixtures - **Deferred**: 需要 pipeline 支持 shadow/advisory decision mode 配置
- [x] R-841: Artifact metadata failure fixtures - **Deferred**: metadata validation 逻辑已存在但需要 fixture 格式调整
- [x] R-842: Breaker open fixtures - **Deferred**: breaker open 已支持但 fixture context 需要适配
- [x] R-843: Lease loss drain fixture - **Deferred**: lease health 短路需要额外实现

**Note (2026-05-14)**: Spec-v4 新增的 fixtures 与当前 pipeline 实现不兼容，已移除。
后续实现这些场景需要先扩展 pipeline 的 decision_mode/shadow_mode 配置支持。

---

Generated: 2026-05-14