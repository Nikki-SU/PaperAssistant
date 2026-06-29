#requires -Version 5.1
<#
.SYNOPSIS
  在 Windows 上用 PyInstaller 把 FastAPI 后端打成单文件 sidecar exe。

.DESCRIPTION
  1. 安装 / 升级 pyinstaller
  2. 安装 backend-python/requirements.txt
  3. 跑 sidecar.spec
  4. 把 dist/paperassistant-backend.exe 复制到
     frontend/src-tauri/binaries/paperassistant-backend-x86_64-pc-windows-msvc.exe
     （Tauri externalBin 强约束：必须含 target triple 后缀）

.NOTES
  目标平台固定 Windows x64。其它平台请用 build_sidecar.sh（参考实现）。
#>

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")

Write-Host "[1/4] 升级 pyinstaller 并安装依赖" -ForegroundColor Cyan
python -m pip install --upgrade pip pyinstaller | Out-Host
python -m pip install -r (Join-Path $RepoRoot "backend-python/requirements.txt") | Out-Host

Push-Location (Join-Path $RepoRoot "backend-python")
try {
    Write-Host "[2/4] 运行 PyInstaller (sidecar.spec)" -ForegroundColor Cyan
    pyinstaller --clean --noconfirm sidecar.spec | Out-Host

    $src = Join-Path (Get-Location) "dist\paperassistant-backend.exe"
    if (-not (Test-Path $src)) {
        throw "PyInstaller 没有产出 dist\paperassistant-backend.exe（请查 PyInstaller 日志）"
    }

    $binDir = Join-Path $RepoRoot "frontend\src-tauri\binaries"
    if (-not (Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir | Out-Null }

    $dest = Join-Path $binDir "paperassistant-backend-x86_64-pc-windows-msvc.exe"
    Write-Host "[3/4] 复制到 $dest" -ForegroundColor Cyan
    Copy-Item -Force $src $dest

    Write-Host "[4/4] 完成：sidecar 大小 = $((Get-Item $dest).Length / 1MB) MB" -ForegroundColor Green
}
finally {
    Pop-Location
}
