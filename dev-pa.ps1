# PaperAssistant 一键启动（Windows / PowerShell）
# - 启动 backend (FastAPI @ 127.0.0.1:8181)
# - 启动 frontend (Vite @ 127.0.0.1:1421)
# - 可选：同时启动 debug-assistant server（需要 G:\debug-assistant 已 clone）
#
# 用法：
#   PowerShell> .\dev-pa.ps1
#   PowerShell> .\dev-pa.ps1 -NoFrontend          # 只起后端
#   PowerShell> .\dev-pa.ps1 -WithDebugAssistant  # 同时起 debug-assistant server
#   PowerShell> .\dev-pa.ps1 -Tauri               # 用 tauri dev 替代纯 vite

param(
    [switch]$NoFrontend,
    [switch]$WithDebugAssistant,
    [switch]$Tauri
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot

Write-Host "==> PaperAssistant repo: $repo"

# --- 0. debug-assistant server（可选） ---
$daJob = $null
if ($WithDebugAssistant) {
    $daRepo = "G:\debug-assistant"
    if (-not (Test-Path $daRepo)) {
        Write-Warning "未找到 $daRepo —— 跳过 debug-assistant 启动。"
    } else {
        Write-Host "==> starting debug-assistant server (127.0.0.1:8765)"
        $daJob = Start-Job -Name "da-server" -ScriptBlock {
            param($root)
            Set-Location $root
            if (-not (Test-Path ".venv")) {
                py -m venv .venv
            }
            & ".venv\Scripts\python.exe" -m pip install -q -e "$root\server"
            & ".venv\Scripts\python.exe" -m debug_assistant.main
        } -ArgumentList $daRepo
    }
}

# --- 1. backend venv + install ---
$backendDir = Join-Path $repo "backend-python"
$venv = Join-Path $backendDir ".venv"
Push-Location $backendDir
try {
    if (-not (Test-Path $venv)) {
        Write-Host "==> creating venv at $venv"
        py -m venv $venv
    }
    $py = Join-Path $venv "Scripts\python.exe"
    Write-Host "==> pip install backend deps"
    & $py -m pip install -q --upgrade pip
    & $py -m pip install -q -r requirements.txt
} finally {
    Pop-Location
}

# --- 2. backend job ---
$beJob = Start-Job -Name "pa-backend" -ScriptBlock {
    param($backendDir, $py)
    Set-Location $backendDir
    & $py -m app.main
} -ArgumentList $backendDir, (Join-Path $venv "Scripts\python.exe")

Write-Host "==> backend job id: $($beJob.Id)"

# --- 3. frontend ---
if (-not $NoFrontend) {
    $frontendDir = Join-Path $repo "frontend"
    Push-Location $frontendDir
    try {
        if (-not (Test-Path "node_modules")) {
            Write-Host "==> npm install"
            npm install
        }
        if ($Tauri) {
            Write-Host "==> npm run tauri dev"
            npm run tauri -- dev
        } else {
            Write-Host "==> npm run dev (Vite @ 1421)"
            npm run dev
        }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "PaperAssistant 后端任务在后台运行；停止：Stop-Job -Name pa-backend"
