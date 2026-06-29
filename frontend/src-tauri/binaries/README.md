# binaries/

PaperAssistant Tauri 通过 `externalBin` 把 Python 后端作为 sidecar 打包。

构建产物文件名（target triple 由 Tauri 自动追加）：

- Windows x64： `paperassistant-backend-x86_64-pc-windows-msvc.exe`
- Linux x64：   `paperassistant-backend-x86_64-unknown-linux-gnu`
- macOS arm64： `paperassistant-backend-aarch64-apple-darwin`

> Tauri externalBin 约束：声明 `binaries/paperassistant-backend`
> → 运行时实际寻找 `binaries/paperassistant-backend-<host-triple>(.exe)`
> 名字不匹配会报 "sidecar not found"。

### 怎么生成

Windows：

```powershell
pwsh scripts/build_sidecar.ps1
```

其它平台参考：

```bash
bash scripts/build_sidecar.sh
```

构建脚本会自动 PyInstaller `backend-python/sidecar.spec` 并拷贝到本目录。
