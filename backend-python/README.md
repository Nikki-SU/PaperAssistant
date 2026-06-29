# PaperAssistant / backend-python

FastAPI sidecar，由 Tauri 启动并维护其生命周期。

## 启动（开发期独立调试）
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8181
```

## 模块
- `api/`：HTTP 路由层
- `services/`：MinerU、AI 调度（助手/审阅/秘书）
- `stages/`：五阶段业务逻辑（选题/综述/撰写/引用/排版）
- `storage/`：CSV + Markdown 读写（**绝不 JSON**）
- `audit/`：事实核查（审阅 AI 闭环）
- `models/`：Pydantic 数据模型

对应 SPEC：项目二 §三. 技术栈 / §四. 全局核心规则
