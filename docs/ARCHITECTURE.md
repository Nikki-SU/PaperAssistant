# PaperAssistant 架构（v0.1 实装版）

> 与 `docs/SPEC.md` 对齐。本文件描述**当前真实代码**而非完整目标。
> 任何与代码不一致之处都应**先改 SPEC、再改本文**。

## 1. 进程拓扑

```
┌─────────────────────────────────────────────────────────────┐
│ Tauri 主进程（Rust）                                          │
│   - 仅托管窗口、加载前端 dist；不直接处理业务                  │
└─────────────────────────────────────────────────────────────┘
              │ webview
              ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend（React 18 + Vite，1421 端口）                        │
│  - 侧栏：项目列表                                              │
│  - 主区：根据 project.stage 路由到 5 个 Stage 组件             │
│  - api/client.ts → fetch(127.0.0.1:8181)                     │
│  - lib/debugAssistant.ts → POST(127.0.0.1:8765/api/report)   │
└─────────────────────────────────────────────────────────────┘
              │ HTTP/JSON
              ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend（FastAPI，8181 端口）                                 │
│  app/main.py          ← FastAPI app + startup hook           │
│  app/api/*            ← 5 个路由（health/project/lit/ci/ty）  │
│  app/storage/*        ← CSV + Markdown IO（线程锁）           │
│  app/services/*       ← MinerU client + AI Orchestrator      │
│  app/audit/*          ← FactChecker（最多 5 轮）              │
│  app/stages/*         ← 五阶段业务（当前为骨架）              │
│  app/models/*         ← Pydantic 模型                         │
│  app/config.py        ← 数据根目录 + 环境变量                  │
└─────────────────────────────────────────────────────────────┘
       │ 文件系统               │ HTTP（可选，全部允许失败）
       ▼                         ▼
  data_root/*               ┌──────────────────────┐
  (Markdown + CSV)          │ debug-assistant       │
                            │ server (8765)         │
                            └──────────────────────┘
                            ┌──────────────────────┐
                            │ MinerU / 三个 AI API  │
                            └──────────────────────┘
```

## 2. 数据目录（SPEC §五.1）

```
~/Documents/PaperAssistant/
├── config/
├── knowledge/
├── library/
│   ├── fulltext/          ← {doi}.md  全文（MinerU 输出）
│   └── cards/
│       ├── cards.csv      ← 主索引（SPEC §八.1，21 列）
│       └── {doi}.md       ← 卡片正文（frontmatter + 八节模板）
├── projects/
│   ├── _index.csv         ← 项目索引（name/stage/perspective/topic/...）
│   └── {project}/
│       ├── meta.csv
│       ├── memories/      ← 长期 / 临时记忆 Markdown
│       ├── paper/         ← 章节 Markdown（导出时合并为 manuscript.md）
│       └── citations/
│           └── citations.csv
└── temp/
    └── monitor/           ← 上传 PDF 暂存
```

## 3. 数据流

### 3.1 文献上传

```
[Frontend]                 [Backend]                        [Storage]
upload PDF  ─POST/literature/upload─►  api/literature.upload_pdf
                                            ├─ save to temp/monitor/
                                            ├─ MineruClient.parse()
                                            │      ├─ enabled? → real API (TODO)
                                            │      └─ disabled → placeholder.md
                                            ├─ write fulltext/{doi}.md
                                            ├─ upsert cards.csv (key=doi)
                                            └─ write cards/{doi}.md (frontmatter)
                                            └────► return JSON to FE
```

### 3.2 项目阶段切换

```
StageNav → PATCH /api/project/{name} {stage: "review"}
  └─ upsert _index.csv & {project}/meta.csv，同步两份元信息
```

### 3.3 事实核查（设计，未接 AI 时降级）

```
助手 AI 生成草稿 ──► FactChecker.review_once(draft, evidence)
                       ├─ 未配 auditor_chat ──► 返回全 missing-info
                       └─ 已配         ──► 解析 findings
                            ├─ 有阻塞？ ─yes→ assistant_chat 重写 ─► 再审
                            └─ 无阻塞 / 达到 5 轮 ─► 输出最终 report
```

## 4. 关键模块边界

- **storage**：纯函数 + 线程锁，无业务知识；只关心「CSV / Markdown」格式。
- **models**：Pydantic 模型仅用于 HTTP 入出参；落盘时由 storage 自己负责字段。
- **services**：
  - `MineruClient`：仅 PDF→Markdown 的接口位，**不**操作 cards.csv。
  - `AIOrchestrator`：四接口位的统一封装，所有调用失败必须返回 `AIResult(success=False)`，由上层决定如何降级。
- **audit**：纯逻辑，不直接调网络；接受可注入的 `auditor_chat` / `assistant_chat` 函数。
- **api**：胶水层。**所有 HTTP 异常都在这里抛 HTTPException**，业务函数尽量纯。
- **stages**：未来填业务逻辑的位置；当前仅 `describe()` 占位，便于 `main.py` 静态导入并触发 stages 子模块初始化。

## 5. 与 debug-assistant 的接入

- 后端：`app/main.py::_init_debug_assistant()`
  - 尝试 `from debug_assistant import Debugger, set_default`
  - 失败：`logger.warning` + 直接 return（启动继续）
- 前端：`src/lib/debugAssistant.ts`
  - 内联 `DebugAssistantClient` + `installGlobalHandlers`
  - `daReport()` 在 `api/client.ts` 的 fetch 失败 / 非 2xx 时调用
  - 任何调用都包在 try/catch 内，绝不向 UI 冒泡

## 6. 不变约束

| # | 约束 | 检查点 |
|---|------|--------|
| C1 | 落盘只能 Markdown / CSV | `storage/` 内未出现 `json.dumps` 写文件 |
| C2 | SDK 失败必须降级 | `_init_debug_assistant` 整段被 `try`；`daReport` 内 `catch { return null }` |
| C3 | AI 调用失败必须降级 | `AIOrchestrator.chat` 返回 `AIResult(success=False)` 而非抛错 |
| C4 | DOI 唯一 | cards.csv 用 `upsert_row(..., primary_key="doi")` |
| C5 | 删除项目不物理删除目录 | `api/project.delete_project` 仅删索引 |
