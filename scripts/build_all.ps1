#requires -Version 5.1
<#
.SYNOPSIS
  一键构建 PaperAssistant Windows 安装包：sidecar → tectonic 校验 → tauri build。

.NOTES
  前置：
  - Windows 10/11 x64
  - 已装 Node.js 20+、Rust stable、Python 3.11/3.12、PyInstaller
  - 已装 Tauri CLI v2：`cargo install tauri-cli --version "^2.0.0"`
  - 若想出 .msi，需要 WiX Toolset v3.x

  本脚本依次：
  1. 跑 build_sidecar.ps1 → 产出 paperassistant-backend-*.exe
  2. 校验 frontend/src-tauri/resources/tectonic/tectonic.exe 已就位
     （没有就提示运行 fetch_tectonic.ps1）
  3. 进入 frontend/ 跑 npm install + npm run build + cargo tauri build
#>

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "==[ Step 1/3 ]== 构建 Python sidecar" -ForegroundColor Cyan
& (Join-Path $ScriptRoot "build_sidecar.ps1")

Write-Host ""
Write-Host "==[ Step 2/3 ]== 校验 Tectonic 资源" -ForegroundColor Cyan
$tectonicExe = Join-Path $RepoRoot "frontend\src-tauri\resources\tectonic\tectonic.exe"
if (-not (Test-Path $tectonicExe)) {
    Write-Warning "未找到 $tectonicExe"
    Write-Host "请先运行：pwsh $(Join-Path $ScriptRoot 'fetch_tectonic.ps1')" -ForegroundColor Yellow
    Write-Host "或手动放置 tectonic.exe 到 resources/tectonic/" -ForegroundColor Yellow
    throw "Tectonic 资源缺失，已中止打包。"
}
Write-Host "  ✓ Tectonic 已就位：$tectonicExe" -ForegroundColor Green

Write-Host ""
Write-Host "==[ Step 3/3 ]== 前端依赖 + Tauri 打包" -ForegroundColor Cyan
Push-Location (Join-Path $RepoRoot "frontend")
try {
    npm install | Out-Host
    npm run build | Out-Host
    cargo tauri build | Out-Host
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "✓ 全部完成。产物在：" -ForegroundColor Green
Write-Host "  - $($RepoRoot)\frontend\src-tauri\target\release\bundle\" -ForegroundColor Green
