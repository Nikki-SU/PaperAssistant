# PaperAssistant 架构总览

## 模块划分

```
PaperAssistant/
├── backend-python/          # FastAPI sidecar，监听 8181
│   └── app/
│       ├── api/             # HTTP 路由层
│       ├── services/        # MinerU / AI 调度
│       ├── stages/          # 五阶段业务逻辑
│       ├── storage/         # CSV + Markdown 读写（铁律：无 JSON）
│       ├── audit/           # 事实核查（审阅 AI 闭环）
│       └── models/          # Pydantic 模型（仅 HTTP 在途）
├── frontend/                # Tauri v2 + React 前端
│   ├── src/                 # React (stages / components / store)
│   └── src-tauri/           # Rust 壳（启动 Python sidecar）
└── docs/                    # SPEC + 架构说明
```

## 数据流

```
用户 ─→ Tauri Window ─→ React (前端)
                          │ HTTP fetch
                          ▼
                  FastAPI sidecar (localhost:8181)
                          │
              ┌───────────┼────────────────┐
              ▼           ▼                ▼
        api/literature  api/citation   api/typesetting
              │           │                │
              ▼           ▼                ▼
         services/      stages/        services/
        mineru/AI    五阶段业务      AI/Tectonic
              │           │                │
              └───┬───────┴────────────────┘
                  ▼
              storage/
        ┌───────┴───────┐
        ▼               ▼
   csv_io.py     markdown_io.py
        │               │
        ▼               ▼
   {data_root}/...   {data_root}/...
   (CSV 索引)         (Markdown 全文/卡片/记忆)
```

## 调试集成
开发期所有 Python 后端错误通过 `debug-assistant` SDK 自动上报到 `http://localhost:8765`：
```python
from debug_assistant import Debugger
debugger = Debugger(project="PaperAssistant", module="backend")
try:
    risky()
except Exception as e:
    debugger.report(error=e, context={"stage": "literature_review"})
```

## 铁律
- **数据格式**：CSV + Markdown 落盘，**绝不 JSON**（仅 HTTP 在途传输用 JSON）
- **AI 边界**：声称"来自某文献"的输出必须经审阅 AI 核查
- **兜底原则**：AI 缺少信息时，告知用户如何补充，不得编造
- **本地优先**：CSL/Tectonic/MinerU 全部本地运行（除 MinerU API 调用）
