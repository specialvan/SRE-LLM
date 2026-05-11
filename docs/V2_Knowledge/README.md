# V2 Knowledge Hub

本目录是 **2026-05** 时点的项目知识库快照，面向下一位接手的 agent / 开发
/ reviewer。

## 为什么叫 V2

V1 是 `docs/knowledge_base.html`，只覆盖九个数学机制的公式与 before/after
数据收益。当项目从"机制复现"推进到"SRE 自迭代决策系统 + artifact / lease
/ replay / 可执行 spec"之后，V1 的一页已经装不下。V2 重新组织，加入：

- 从顶层 context 到 stage 决策流的**架构全景**
- 当前分支（`gan-session`）的**交付状态**与未合入 blocker
- 九个机制 → SRE 控制原语的**对照卡片**
- 最新评审的 **findings** + **可执行 spec** 入口
- 一键定位：从 "我想干什么" 到 "读哪个文件"

## 怎么用

```
直接打开 knowledge-base.html
```

离线可读（MathJax / mermaid 走 CDN，首次需网络；之后可用 browser cache）。

## 文件

| 文件 | 用途 |
|---|---|
| [`knowledge-base.html`](knowledge-base.html) | 单页知识库，所有章节集中 |
| `README.md` | 你正在看的这份 |

## 与其他文档的关系

```
V2_Knowledge/knowledge-base.html  ←  一页读懂项目当前形态
          │
          ├──（链入）docs/architecture/     深度架构文档
          ├──（链入）docs/adr/              决策记录
          ├──（链入）docs/runbooks/         运维 SOP
          ├──（链入）docs/claude-review/    最新评审 + 可执行 spec
          └──（链入）docs/knowledge_base.html  V1 数学机制原版（保留）
```

V2 不替代任何深度文档，它是"索引 + 概览"。

## 更新策略

- 每次有"评审一轮 → 形成 spec → codex 完成 → 评审下一轮"完整闭环时，
  新建 `docs/V3_Knowledge/`、`V4_Knowledge/` 等，**V2 永远冻结在 2026-05**。
- 同一轮里的增量改动只更新本目录下的 `knowledge-base.html`。
