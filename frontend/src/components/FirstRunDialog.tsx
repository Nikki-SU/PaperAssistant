/**
 * 首次启动引导（A5）。
 *
 * 触发条件：is_default_root === true 时强引导用户选目录。
 * - Tauri 环境：理想做法是用 plugin-dialog 的 open dialog；当前不依赖（避免锁版本）
 * - 退化：让用户手动粘贴绝对路径
 */
import { useState } from "react";
import { api } from "../api/client";
import type { SettingsSnapshot } from "../api/client";

interface Props {
  current: SettingsSnapshot;
  onDone: (s: SettingsSnapshot) => void;
  onSkip: () => void;
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
}

export function FirstRunDialog({ current, onDone, onSkip, notify }: Props) {
  const [path, setPath] = useState(current.data_root);
  const [busy, setBusy] = useState(false);

  async function commit() {
    if (!path.trim()) return;
    setBusy(true);
    try {
      await api.setDataRoot(path.trim());
      const fresh = await api.getSettings();
      notify(`已切换数据目录到 ${fresh.data_root}`, "ok");
      onDone(fresh);
    } catch (e) {
      notify(`保存失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal modal-first-run">
        <header className="modal-head">
          <h3>👋 欢迎使用 PaperAssistant</h3>
        </header>
        <p>
          这是一个<strong>本地优先</strong>的学术写作辅助工具。所有数据（论文草稿、文献库、记忆）都存在你自己的电脑上。
        </p>
        <p>请先选定一个用来存放论文项目和文献库的目录：</p>

        <div className="setting-row">
          <input
            className="text-input wide"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="如 C:\Users\Rosa\Documents\PaperAssistant"
          />
        </div>

        <p className="muted-small">
          目前是默认目录 <code>{current.data_root}</code>。你可以保留它，或改到任意位置。
          这个目录下会自动创建 <code>config/ knowledge/ library/ projects/ temp/</code> 子目录。
        </p>

        <footer className="modal-foot">
          <button className="ghost-btn" onClick={onSkip} disabled={busy}>
            先用默认目录
          </button>
          <button className="primary-btn" onClick={commit} disabled={busy}>
            使用这个目录
          </button>
        </footer>
      </div>
    </div>
  );
}
