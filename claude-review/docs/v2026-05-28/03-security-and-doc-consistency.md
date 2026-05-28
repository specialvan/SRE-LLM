# 03 — 安全与文档一致性审计

## 1. DOM XSS 风险：share hash 状态未白名单化

**相关位置**：

- `docs/control-center.html:119`：`applyShareState(raw)` 从 URL hash 恢复状态。
- `docs/control-center.html:104`：`renderChartStatus()` 拼接 `innerHTML`。
- `docs/control-center.html:126`：`renderFocusTrail()` 拼接 `innerHTML` 且未对 `lensLabel` escape。

### 具体问题

`applyShareState()` 接收 URL hash：

```javascript
filterMode=params.get("filter")||filterMode;
windowMode=params.get("window")||windowMode;
...
lensMode=mode||"none";
lensValue=rest.join(":")==="none"?"":rest.join(":");
currentChart=params.get("chart")||currentChart;
```

这些字段缺少枚举约束。随后：

```javascript
const lensLabel=lensMode==="none"?"无透镜":`${lensMode}: ${lensValue}`;
const items=[...,`<button ...>透镜：${lensLabel}</button>`,...];
document.getElementById("focus-trail-list").innerHTML=items.join("");
```

恶意 hash 可把 HTML 片段注入 dashboard。

### 建议

- 为 hash state 建立解析函数：非法值丢弃并回退默认值。
- 所有进入 `innerHTML` 的文本统一 `esc()`。
- 对按钮/chip 改用 `document.createElement()` 与 `textContent`。
- 增加恶意 hash smoke：加载后 DOM 不得出现攻击片段。

## 2. localhost 暴露策略：默认安全不等于强制安全

**相关位置**：

- `scripts/control_center_server.py:231-232`
- `scripts/control_center_browser_smoke.py:76`
- `scripts/control_center_browser_smoke.py:627-628`
- `docs/codex-review/OPEN_RISKS.md:27`

### 具体问题

当前服务默认绑定 `127.0.0.1`，但入口仍允许调用方传非 loopback host。Host header 白名单只能检查请求头，不能阻止网络层暴露。如果绑定 `0.0.0.0`，同网段客户端可以伪造 Host header。

### 建议

- 默认只允许 `127.0.0.1` / `localhost` / `::1`。
- 非 loopback 需要显式危险开关。
- `OPEN_RISKS.md` 将“localhost exposure policy resolved”改为“默认本地绑定已覆盖；非 loopback 绑定需硬拒绝或危险开关”。

## 3. manifest path 读取任意本地文件风险

**相关位置**：

- `scripts/control_center_browser_smoke.py:344-355`
- `scripts/control_center_browser_smoke.py:372-375`
- `scripts/control_center_browser_smoke.py:427-460`

### 具体问题

verifier 信任 manifest 中 path，并读取文件计算 hash / 解析 JSON / 读取 DOM。若 reviewer 运行不可信 manifest，可造成任意本地文件存在性、大小、hash 泄露。

### 建议

- path 必须 repo-relative。
- reject absolute path 与 `..`。
- resolve 后必须 `relative_to(repo_root)` 成功。
- 对 PNG/HTML/JSON artifact 增加大小上限。

## 4. 本地环境路径泄露

**相关位置**：

- `analysis/control_center_data.py:379-382`
- `docs/CONTROL_CENTER_HANDOFF.md:17-21`

### 具体问题

文档/API payload 包含本地盘符路径、OpenDesign 安装路径、本机端口。这不是 secret，但对外发布工程包会暴露 reviewer/workstation 细节。

### 建议

- API payload 保留语义 provenance，不写真实绝对路径。
- handoff 中标注为“本工作站调试信息，不进入公开包”。
- release lint 检查 `C:\Users\`、盘符路径、`G:/`、动态 localhost port。

## 5. 文档一致性问题

### 5.1 `QUALITY_GATES.md` 与实测不一致

`QUALITY_GATES.md` 当前写：

```text
python -m pytest tests -q
437 passed
```

本轮实测为 4 failed。因此该文档必须更新为失败状态，或先修复后再写回通过状态。

### 5.2 OPUS packet 与 live quality gates 不一致

`docs/opus-review/OPUS_REVIEW_PACKET.md` 的 Latest verified commands 未包含 browser smoke report 与 package smoke，但 `QUALITY_GATES.md` Required Commands 包含它们。若 OPUS packet 被 `quality_gate_counts` 当成 live drift doc，应同步；若只是 historical snapshot，则不要把它放进 live command docs。

### 5.3 saved replay 被写成 current proof

`QUALITY_GATES.md` 对 package smoke / integration audit 的描述容易让 reviewer 以为 error paths 也实时重跑。实际当前代码更接近：

- package smoke：saved evidence report + source manifest replay + wheel import smoke。
- integration audit：normal API snapshot 与当前 backend payload hash；error manifests 多为 saved replay。

建议文档明确区分。

## 6. 安全验收 checklist

合入前建议新增如下 checklist：

- [ ] 恶意 `#share=` 不会向 DOM 注入 HTML/JS。
- [ ] control-center server 拒绝非 loopback host，除非显式危险开关。
- [ ] browser smoke manifest path 全部 repo-relative。
- [ ] verifier 拒绝 absolute path 与 `..`。
- [ ] evidence JSON writer 均 `allow_nan=False`。
- [ ] package/integration audit 文档明确区分 realtime rerun 与 saved replay。
