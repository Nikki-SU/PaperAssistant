# resources/tectonic/

PaperAssistant 内嵌 Tectonic（零依赖 LaTeX 引擎）作为打包资源。

### 期望文件

- Windows: `tectonic.exe`

### 怎么获取

```powershell
pwsh scripts/fetch_tectonic.ps1
```

脚本会从 GitHub Releases 拉最新 Windows x64 zip 并解压到本目录。

或手动下载：

- https://github.com/tectonic-typesetting/tectonic/releases/latest
- 匹配 asset：name 含 `x86_64-pc-windows-msvc` 且 `.zip$`
- 解压后把 `tectonic.exe` 放到本目录

### 运行时

Tauri 启动器在 `setup()` 阶段把这个 exe 的绝对路径写入
`PAPERASSISTANT_TECTONIC_BIN` 环境变量；后端 `/api/typesetting/{project}/compile_pdf`
按 `PAPERASSISTANT_TECTONIC_BIN → TECTONIC_BIN → PATH` 顺序解析。

文件缺失时，后端会返回 `{compiled: false, reason: "tectonic_not_found"}`，
不抛 500；前端可提示用户去设置面板补路径。
