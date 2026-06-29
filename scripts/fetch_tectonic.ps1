#requires -Version 5.1
<#
.SYNOPSIS
  从 GitHub Releases 拉取 Tectonic Windows x64 单文件并放到 resources/tectonic/。

.DESCRIPTION
  1. 调用 GitHub API 找最新 release
  2. 匹配 asset：name 含 'x86_64-pc-windows-msvc' 且 '.zip$'
  3. 下载到临时目录 → 解压 → 找 tectonic.exe → 拷贝到
     frontend/src-tauri/resources/tectonic/tectonic.exe

.NOTES
  网络不通时可手动下载放置（路径同上）。
#>

$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$DestDir = Join-Path $RepoRoot "frontend\src-tauri\resources\tectonic"
$DestExe = Join-Path $DestDir "tectonic.exe"

if (-not (Test-Path $DestDir)) { New-Item -ItemType Directory -Path $DestDir -Force | Out-Null }

if (Test-Path $DestExe) {
    Write-Host "已存在：$DestExe" -ForegroundColor Yellow
    $ans = Read-Host "覆盖? (y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") {
        Write-Host "已跳过下载。"
        return
    }
}

Write-Host "[1/4] 查询 Tectonic 最新 Release..." -ForegroundColor Cyan
$api = "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"
$rel = Invoke-RestMethod -Uri $api -UseBasicParsing -Headers @{ "User-Agent" = "PaperAssistant-fetch-tectonic" }
$asset = $rel.assets | Where-Object {
    $_.name -match "x86_64-pc-windows-msvc" -and $_.name -match "\.zip$"
} | Select-Object -First 1

if (-not $asset) {
    throw "没找到匹配的 asset（x86_64-pc-windows-msvc *.zip）。请到 https://github.com/tectonic-typesetting/tectonic/releases 手动下载。"
}

Write-Host "  ✓ 选定 asset: $($asset.name) ($([math]::Round($asset.size / 1MB, 2)) MB)" -ForegroundColor Green
Write-Host "  ↓ $($asset.browser_download_url)" -ForegroundColor DarkGray

$tmpDir = Join-Path $env:TEMP "pa-tectonic-$(Get-Date -Format yyyyMMddHHmmss)"
New-Item -ItemType Directory -Path $tmpDir | Out-Null
$zipPath = Join-Path $tmpDir $asset.name

Write-Host "[2/4] 下载到 $zipPath ..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing

Write-Host "[3/4] 解压..." -ForegroundColor Cyan
$extractDir = Join-Path $tmpDir "extract"
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

$foundExe = Get-ChildItem -Path $extractDir -Recurse -Filter "tectonic.exe" | Select-Object -First 1
if (-not $foundExe) {
    throw "解压后没找到 tectonic.exe（请到 $extractDir 手动确认）。"
}

Write-Host "[4/4] 拷贝到 $DestExe" -ForegroundColor Cyan
Copy-Item -Force $foundExe.FullName $DestExe

Remove-Item -Recurse -Force $tmpDir

Write-Host ""
Write-Host "✓ Tectonic 已就位：$DestExe  ($([math]::Round((Get-Item $DestExe).Length / 1MB, 2)) MB)" -ForegroundColor Green
