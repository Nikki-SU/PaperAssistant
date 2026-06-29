# PaperAssistant / frontend

Tauri v2 + React + TypeScript + Vite。

## 开发
```bash
npm install
npm run tauri dev
```

## 构建
```bash
npm run tauri build
```

## 与 Python sidecar 的通信
- 前端通过 `http://localhost:8181` 调用 Python FastAPI
- Tauri 启动时拉起 `binaries/paperassistant-backend`（PyInstaller 打包的 EXE）
- 退出时 Tauri 负责 kill sidecar

对应 SPEC：项目二 §三. 技术栈
