# PaperAssistant 打包指南（H 阶段产物）

> 目标：把 PaperAssistant 打包成一个可在 Windows x64 上一键安装、离线运行的桌面 App。
> 架构：Tauri 2（前端 + Rust 启动器） + PyInstaller 把 Python FastAPI 后端打成 sidecar 二进制 + 内嵌 Tectonic 单文件 LaTeX 引擎。

---

## 1. 前置依赖（Windows 10/11 x64）

| 工具 | 版本 | 安装方式 |
| --- | --- | --- |
| Node.js | ≥ 20 LTS | https://nodejs.org/ |
| pnpm 或 npm | 任意 | 跟随 Node 安装 |
| Rust 工具链 | stable | https://rustup.rs/，运行 `rustup default stable` |
| Tauri CLI | v2 | `cargo install tauri-cli --version "^2.0.0"` 或 `npm i -g @tauri-apps/cli@^2` |
| Python | 3.11 / 3.12 | https://www.python.org/ |
| PyInstaller | 最新 | `pip install pyinstaller` |
| WebView2 Runtime | Evergreen | Windows 11 默认有；Win10 见 https://developer.microsoft.com/microsoft-edge/webview2/ |
| WiX Toolset v3 | v3.x | 仅当输出 .msi 安装包时需要：https://github.com/wixtoolset/wix3/releases |

> 没装 Rust 就跑 `cargo --version`，会有命令行提示安装；首次安装下载 ~200MB。

---

## 2. 一次性准备：拉取 Tectonic 二进制

PaperAssistant 把 Tectonic（一个零依赖的 LaTeX 引擎，单 exe 即可工作）作为资源内嵌进安装包。第一次构建前需要把它下载到指定位置：

```powershell
# 在仓库根目录执行
pwsh scripts/fetch_tectonic.ps1
```

该脚本会自动：
1. 调用 GitHub Releases API 找到 `tectonic-*-x86_64-pc-windows-msvc.zip` 最新版
2. 下载到本地临时目录
3. 解压并把 `tectonic.exe` 拷到 `frontend/src-tauri/resources/tectonic/tectonic.exe`

大小约 30–50 MB；下载完成后 `dir frontend/src-tauri/resources/tectonic/` 应能看到 `tectonic.exe`。

如果你已有 Tectonic 可执行文件，直接放进该目录即可，不必跑脚本。

---

## 3. 构建步骤

### 方式一：一键打包

```powershell
pwsh scripts/build_all.ps1
```

该脚本依次做三件事：
1. 跑 PyInstaller 构建 sidecar（等价于 build_sidecar.ps1）
2. 校验 `frontend/src-tauri/resources/tectonic/tectonic.exe` 存在
3. 进入 `frontend/`，执行 `npm install`、`npm run build`、`cargo tauri build`

构建产物：
- 安装包：`frontend/src-tauri/target/release/bundle/msi/*.msi`、`bundle/nsis/*.exe`
- 解包后可执行文件：`frontend/src-tauri/target/release/PaperAssistant.exe`

### 方式二：分步构建（用于调试）

```powershell
# Step 1：构建 Python sidecar 单文件 exe
pwsh scripts/build_sidecar.ps1
# 产物：frontend/src-tauri/binaries/paperassistant-backend-x86_64-pc-windows-msvc.exe

# Step 2：确认 Tectonic 已就位（若未做过）
pwsh scripts/fetch_tectonic.ps1

# Step 3：Tauri 打包
cd frontend
npm install
npm run build           # 生成 dist/（前端静态资源）
cargo tauri build       # 调用 Rust + Tauri 把 dist + sidecar + resources 打成 msi/nsis
```

---

## 4. 产物结构

```
frontend/src-tauri/
├── binaries/
│   └── paperassistant-backend-x86_64-pc-windows-msvc.exe   # PyInstaller 出的 sidecar
├── resources/
│   └── tectonic/
│       └── tectonic.exe                                    # 内嵌 LaTeX 引擎
├── target/release/
│   ├── PaperAssistant.exe                                  # Tauri 主程序
│   └── bundle/
│       ├── msi/PaperAssistant_0.1.0_x64_en-US.msi
│       └── nsis/PaperAssistant_0.1.0_x64-setup.exe
```

---

## 5. 运行时行为

1. 用户双击 `PaperAssistant.exe` → Tauri Rust 启动器拉起 sidecar：
   ```
   binaries/paperassistant-backend-x86_64-pc-windows-msvc.exe
   ```
2. 启动器把 `resources/tectonic/tectonic.exe` 的绝对路径写入环境变量 `PAPERASSISTANT_TECTONIC_BIN`，后端在 `/api/typesetting/{project}/compile_pdf` 中按此优先级解析：
   ```
   PAPERASSISTANT_TECTONIC_BIN  →  TECTONIC_BIN  →  PATH 中的 tectonic
   ```
3. 主窗口加载 `dist/index.html`，前端调 `http://127.0.0.1:<port>/api/...` 与 sidecar 通信。
4. 用户关窗 → `RunEvent::ExitRequested` 触发 Rust 端 `kill(sidecar)`，释放端口。

---

## 6. 控制台日志（调试用）

Tauri Rust 端把 sidecar 的 stdout / stderr 转发到控制台，前缀分别为：
- `[backend-out]` — 来自 Python 端的 print / logger.info
- `[backend-err]` — 来自 Python 端的 stderr / traceback

调试时建议从命令行启动：

```powershell
cd frontend/src-tauri/target/release
./PaperAssistant.exe
```

可直接看到所有 sidecar 日志，便于排查启动失败。

---

## 7. 常见错误

### 7.1 "sidecar not found"

Rust 启动器抛 `failed to spawn sidecar paperassistant-backend`：
- 确认 `binaries/paperassistant-backend-x86_64-pc-windows-msvc.exe` 存在（文件名包含 target triple，Tauri v2 强约束）
- 重跑 `pwsh scripts/build_sidecar.ps1`

### 7.2 "compiled: false, reason: tectonic_not_found"

调 `/api/typesetting/{project}/compile_pdf` 返回此 JSON 而不是 PDF：
- 检查 `resources/tectonic/tectonic.exe` 是否存在
- 调试运行时（步骤 6）应能看到 `PAPERASSISTANT_TECTONIC_BIN=...` 注入
- 也可手动在系统环境变量里设 `TECTONIC_BIN`

### 7.3 "tauri command not found"

`cargo tauri build` 失败：
- `cargo install tauri-cli --version "^2.0.0"`
- 或局部 `npm i -D @tauri-apps/cli@^2`，然后 `npx tauri build`

### 7.4 PyInstaller 在 Win10 报 "import error: pydantic_core"

`pip install --upgrade pyinstaller pydantic pydantic-core`，spec 已开 `collect_all`，正常不应出现。

### 7.5 安装后启动闪退

99% 是 sidecar 启动异常，端口未占用、未连接：
- 用步骤 6 的命令行模式启动，看 `[backend-err]` 完整 traceback
- 临时用 `PAPERASSISTANT_DATA_ROOT=C:\Users\You\.paperassistant` 跑一次，避免权限问题

---

## 8. 版本/签名/分发（可选）

| 项 | 当前状态 | 备注 |
| --- | --- | --- |
| 应用名 | PaperAssistant | `tauri.conf.json` `productName` |
| Identifier | `com.papassistant.app` | **占位**，发布前建议改成 `com.<你的命名空间>.paperassistant` |
| 版本号 | `0.1.0` | `tauri.conf.json` `version` |
| 图标 | 无（仅有 `icons/README.md`） | 发布前需放 `icon.png` `icon.ico` `icon.icns` |
| 代码签名 | 未配置 | Win 用 `signtool`，需 EV/OV 证书 |
| 自动更新 | 未配置 | 后续可接 Tauri Updater plugin |

---

## 9. 跨平台说明

当前仓库 H 阶段只完整支持 **Windows x64** 打包流程。Linux/macOS：
- `scripts/build_sidecar.sh` 是参考脚本，能跑 PyInstaller，但 `cargo tauri build` 在该平台只能产对应平台 bundle（不能从 Linux 出 Windows .msi）
- 后续若要支持 macOS，需追加 `frontend/src-tauri/resources/tectonic-mac` 等分平台资源并在 `main.rs` 按 `cfg(target_os)` 解析
