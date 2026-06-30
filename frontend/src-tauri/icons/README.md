# Tauri 图标资源

包含所有目标平台所需的图标文件：

- `icon.png` (1024×1024) — Linux 主图标，也是源图
- `icon.ico` — Windows 多档（16/24/32/48/64/128/256）
- `icon.icns` — macOS 多档（含 16/32/128/256/512 及 @2x）
- `32x32.png` / `128x128.png` / `128x128@2x.png` — Tauri 默认 PNG 集
- `Square*Logo.png` / `StoreLogo.png` — Windows Store (MSIX) 用

设计：极简单色羽毛笔 + "Accept!" 草书字样，寓意"论文被接收"，白底深墨黑线。

如需重新生成（替换源图 source.png 后）：

```bash
npx @tauri-apps/cli icon path/to/source.png
```
