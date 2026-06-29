#!/usr/bin/env bash
# 参考脚本：在 Linux/macOS 上用 PyInstaller 构建 sidecar 二进制
# 主目标平台是 Windows（用户最终在 Windows 上跑 build_sidecar.ps1）。
# 这个 .sh 脚本仅用于开发者在非 Windows 平台快速验证 PyInstaller spec 是否可用。

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "[1/3] 安装 PyInstaller + 依赖"
pip install --upgrade pyinstaller
pip install -r backend-python/requirements.txt

echo "[2/3] 运行 PyInstaller"
cd backend-python
pyinstaller --clean --noconfirm sidecar.spec

# 目标三元组：Tauri externalBin 在 Windows x64 是 x86_64-pc-windows-msvc
# Linux x64 是 x86_64-unknown-linux-gnu；macOS arm64 是 aarch64-apple-darwin。
HOST_TRIPLE="$(rustc -vV 2>/dev/null | grep host: | awk '{print $2}' || echo unknown)"

SRC="dist/paperassistant-backend"
if [ ! -f "$SRC" ]; then
  echo "ERROR: PyInstaller 未生成 dist/paperassistant-backend" >&2
  exit 1
fi

DEST="$ROOT/frontend/src-tauri/binaries/paperassistant-backend-${HOST_TRIPLE}"
mkdir -p "$ROOT/frontend/src-tauri/binaries"
cp "$SRC" "$DEST"
chmod +x "$DEST"

echo "[3/3] sidecar 拷贝完成 → $DEST"
