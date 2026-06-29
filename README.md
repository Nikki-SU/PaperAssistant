# PaperAssistant

> 本地优先（local-first）的学术写作辅助桌面应用。所有数据落到本地磁盘，
> 仅 PDF 解析与 AI 调用通过用户自配的接口位走外网。
>
> 状态：**v0.1 开发中**。本仓库当前是「最小可跑骨架 + 五阶段框架」，
> 助手 / 审阅 / 秘书三个 AI 接口位、MinerU PDF 解析、Tectonic 排版均留有接口位 + 降级实现。

## 设计原则

1. **本地优先**：默认数据根目录 `~/Documents/PaperAssistant`，可在 GUI 中修改。
2. **Markdown + CSV 二元持久化**：结构化数据落 CSV，富文本落 Markdown。**绝不**用 JSON 持久化用户数据。
3. **AI 边界与事实核查**：声称「来自某文献」的内容必须经审阅 AI 比对；推断类标注「建议」；缺信息时引导用户补充，不得编造。
4. **失败必须降级**：MinerU / 助手 / 审阅 / 秘书任一接口位失败，业务侧不应崩溃。
5. **与 debug-assistant 协作**：开发 / 测试期 PaperAssistant 后端启动时尝试接入 [debug-assistant](https://github.com/Nikki-SU/debug-assistant) 的 Python SDK；前端引入精简版 TypeScript SDK，自动捕获未处理异常上报。**SDK 失败必须静默降级**。

## 仓库结构

```text
PaperAssistant/
├── README.md
├── dev-pa.ps1                 ← Windows 一键启动
├── docs/
│   ├── SPEC.md                ← 完整产品规格（来自规划阶段）
│   └── ARCHITECTURE.md
├── backend-python/            ← FastAPI 后端
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── app/
│       ├── main.py            ← FastAPI 入口
│       ├── config.py          ← 路径配置 + 环境变量
│       ├── models/            ← Pydantic 模型
│       ├── storage/           ← CSV / Markdown IO
│       ├── services/          ← MinerU + AI 编排器
│       ├── audit/             ← 事实核查
│       ├── stages/            ← 五阶段业务骨架
│       └── api/               ← /api/{health,project,literature,citation,typesetting}
└── frontend/                  ← Tauri v2 + React 18 + Vite + TS
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── api/client.ts      ← 调用 backend 127.0.0.1:8181
    │   ├── lib/debugAssistant.ts ← 内联 debug-assistant 上报
    │   ├── stages/            ← 5 个阶段 React 组件
    │   ├── components/
    │   └── styles/
    └── src-tauri/             ← Rust + tauri.conf.json
```

## Quick Start (Windows)

> 前置：Python 3.11+（`py` 命令可用）、Node v20+、可选 Rust toolchain（Tauri 编译）。

```powershell
# 1. clone
git clone https://github.com/Nikki-SU/PaperAssistant.git
cd PaperAssistant

# 2. 一键启动（默认：起后端 + 起前端 Vite）
.\dev-pa.ps1

# 3a. 浏览器访问： http://127.0.0.1:1421
# 3b. 或使用 Tauri 桌面壳：
.\dev-pa.ps1 -Tauri

# 4. 同时启动 debug-assistant server（需要 G:\debug-assistant 已 clone）
.\dev-pa.ps1 -WithDebugAssistant
```

### 端口约定

| 服务 | 地址 |
|------|------|
| PaperAssistant backend | `http://127.0.0.1:8181` |
| PaperAssistant frontend (vite) | `http://127.0.0.1:1421` |
| debug-assistant server | `http://127.0.0.1:8765` |

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PAPERASSISTANT_DATA_ROOT` | `~/Documents/PaperAssistant` | 本地数据根目录 |
| `PAPERASSISTANT_HOST` | `127.0.0.1` | backend host |
| `PAPERASSISTANT_PORT` | `8181` | backend port |
| `PAPERASSISTANT_LOG_LEVEL` | `INFO` | 日志等级 |
| `DEBUG_ASSISTANT_ENABLED` | `true` | 是否接入 debug-assistant |
| `DEBUG_ASSISTANT_HOST` / `_PORT` | `127.0.0.1` / `8765` | 远端 server |
| `DA_SDK_PATH` | — | 若未 pip 装 SDK，可指向源码目录 |
| `MINERU_API_KEY` / `MINERU_ENDPOINT` | — | MinerU 接入；未配置时回落到占位 Markdown |
| `PA_ASSISTANT_API_KEY` / `_ENDPOINT` / `_MODEL` | — | 助手 AI |
| `PA_AUDITOR_API_KEY` / `_ENDPOINT` / `_MODEL` | — | 审阅 AI |
| `PA_SECRETARY_API_KEY` / `_ENDPOINT` / `_MODEL` | — | 秘书 AI |

## 当前实现状态

| 模块 | 状态 |
|------|------|
| 后端骨架（FastAPI） | ✅ 完成 |
| `/api/project` CRUD | ✅ 完成 |
| `/api/literature` 上传 / 列表 / 详情 | ✅ 完成（MinerU 为 stub） |
| `/api/citation` add / list | ✅ 完成 |
| `/api/typesetting/export` 合并 manuscript.md | ✅ 完成 |
| MinerU 真实 API | ⏳ TODO |
| AI Orchestrator 真实模型接入 | ⏳ TODO（接口位 + 降级已就绪） |
| 事实核查 5 次循环 | ⏳ 框架就绪，需接 AI |
| 五阶段 stage 业务逻辑 | ⏳ 仅 topic / review / citation / typesetting 有 UI |
| Tectonic PDF 编译 | ⏳ TODO |
| 前端项目侧栏 + 五阶段导航 | ✅ 完成 |
| 文献拖拽上传 | ✅ 完成 |
| 引用管理 UI | ✅ 完成 |
| 排版导出 UI | ✅ 完成 |
| 与 debug-assistant 集成 | ✅ 前后端均已接入，连不上时静默降级 |

## 与 debug-assistant 的关系

- debug-assistant 是独立项目（独立仓库）：通用错误记录 / 闭环解决工具。
- PaperAssistant **仅在开发期** 引用 debug-assistant SDK：
  - 后端：`backend-python/app/main.py::_init_debug_assistant()`，连不上即降级。
  - 前端：`frontend/src/lib/debugAssistant.ts`，内联精简 SDK；安装全局错误捕获，HTTP 失败 / Promise reject 自动上报。
- 不强依赖：debug-assistant 没起也能完整跑 PaperAssistant。

## License

AGPL-3.0
