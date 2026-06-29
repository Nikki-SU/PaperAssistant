/**
 * 设置对话框（SPEC §四.5 / §五.1）。
 *
 * - 数据根目录（切换需重启提示）
 * - 监控目录
 * - 4 个 AI 接口位（mineru/assistant/auditor/secretary）—— Key 不回显，只显 set/unset
 *
 * 首次启动时由 FirstRunDialog 自动打开（如果 is_default_root && key 全空）。
 */
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ApiRoleConfig, SettingsSnapshot } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: (s: SettingsSnapshot) => void;
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
}

const ROLE_LABELS: Record<string, string> = {
  mineru:    "MinerU（PDF 解析）",
  assistant: "助手 AI（主对话）",
  auditor:   "审阅 AI（事实核查）",
  secretary: "秘书 AI（修订记录）",
};

export function SettingsDialog({ open, onClose, onSaved, notify }: Props) {
  const [snap, setSnap] = useState<SettingsSnapshot | null>(null);
  const [dataRoot, setDataRoot] = useState("");
  const [monitorDir, setMonitorDir] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    void api.getSettings()
      .then((s) => {
        setSnap(s);
        setDataRoot(s.data_root);
        setMonitorDir(s.monitor_dir);
      })
      .catch((e) => notify(`加载设置失败: ${String(e)}`, "error"));
  }, [open, notify]);

  async function saveDataRoot() {
    if (!dataRoot.trim()) return;
    setBusy(true);
    try {
      const r = await api.setDataRoot(dataRoot.trim());
      notify(`数据目录已设为 ${r.data_root}（可能需重启后端生效）`);
      const fresh = await api.getSettings();
      setSnap(fresh);
      onSaved(fresh);
    } catch (e) {
      notify(`保存失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveMonitorDir() {
    if (!monitorDir.trim()) return;
    setBusy(true);
    try {
      await api.setMonitorDir(monitorDir.trim());
      const fresh = await api.getSettings();
      setSnap(fresh);
      onSaved(fresh);
      notify("监控目录已更新", "ok");
    } catch (e) {
      notify(`保存失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveRole(role: ApiRoleConfig, newKey: string | null, draft: Partial<ApiRoleConfig>) {
    setBusy(true);
    try {
      await api.saveApiConfig({
        role: role.role,
        endpoint: draft.endpoint ?? role.endpoint,
        model: draft.model ?? role.model,
        timeout: parseInt(String(draft.timeout ?? role.timeout) || "120", 10),
        api_key: newKey,  // null 表示不传 = 保持原值；空字符串 = 清除
      });
      const fresh = await api.getSettings();
      setSnap(fresh);
      onSaved(fresh);
      notify(`${role.role} 已保存`, "ok");
    } catch (e) {
      notify(`保存失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-settings" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h3>⚙ 设置</h3>
          <button className="ghost-btn" onClick={onClose}>×</button>
        </header>

        <section className="settings-section">
          <h4>数据根目录</h4>
          <div className="setting-row">
            <input
              className="text-input wide"
              value={dataRoot}
              onChange={(e) => setDataRoot(e.target.value)}
              placeholder="如 C:\Users\Rosa\Documents\PaperAssistant"
            />
            <button className="primary-btn" onClick={saveDataRoot} disabled={busy}>保存</button>
          </div>
          {snap?.is_default_root && (
            <p className="muted-small">⚠ 当前是默认目录，建议指定到你自己的位置。</p>
          )}
          <p className="muted-small">
            指针文件：<code>{snap?.pointer_file ?? ""}</code>
          </p>
        </section>

        <section className="settings-section">
          <h4>监控目录</h4>
          <div className="setting-row">
            <input
              className="text-input wide"
              value={monitorDir}
              onChange={(e) => setMonitorDir(e.target.value)}
              placeholder="可选：下载文献时自动导入这里的 PDF"
            />
            <button className="primary-btn" onClick={saveMonitorDir} disabled={busy}>保存</button>
          </div>
        </section>

        <section className="settings-section">
          <h4>AI 接口位（4 个角色）</h4>
          {(snap?.api_roles ?? []).map((r) => (
            <ApiRoleEditor
              key={r.role}
              role={r}
              busy={busy}
              onSave={(newKey, draft) => onSaveRole(r, newKey, draft)}
            />
          ))}
        </section>
      </div>
    </div>
  );
}

function ApiRoleEditor(props: {
  role: ApiRoleConfig;
  busy: boolean;
  onSave: (newKey: string | null, draft: Partial<ApiRoleConfig>) => void;
}) {
  const { role, busy, onSave } = props;
  const [endpoint, setEndpoint] = useState(role.endpoint);
  const [model, setModel] = useState(role.model);
  const [timeout_, setTimeout_] = useState(role.timeout || "120");
  const [keyDraft, setKeyDraft] = useState("");

  return (
    <div className="api-role-card">
      <div className="api-role-head">
        <strong>{ROLE_LABELS[role.role] ?? role.role}</strong>
        <span className={role.api_key_set ? "badge-ok" : "badge-warn"}>
          {role.api_key_set ? "● Key 已配置" : "● 未配置"}
        </span>
      </div>
      <div className="grid-2">
        <label>
          Endpoint
          <input
            className="text-input"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="如 https://api.openai.com/v1"
          />
        </label>
        <label>
          Model
          <input
            className="text-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="如 gpt-4o / doubao-pro"
          />
        </label>
        <label>
          Timeout (秒)
          <input
            className="text-input"
            value={timeout_}
            onChange={(e) => setTimeout_(e.target.value)}
          />
        </label>
        <label>
          API Key {role.api_key_set && <span className="muted-small">（已存在，不回显）</span>}
          <input
            className="text-input"
            type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            placeholder={role.api_key_set ? "留空 = 保持不变" : "填入新 Key"}
          />
        </label>
      </div>
      <div className="api-role-foot">
        <button
          className="primary-btn"
          disabled={busy}
          onClick={() => onSave(
            keyDraft ? keyDraft : null,
            { endpoint, model, timeout: timeout_ },
          )}
        >
          保存
        </button>
        {role.api_key_set && (
          <button
            className="ghost-btn danger"
            disabled={busy}
            onClick={() => {
              if (!confirm(`确定清除 ${role.role} 的 API Key？`)) return;
              onSave("", { endpoint, model, timeout: timeout_ });
            }}
          >
            清除 Key
          </button>
        )}
      </div>
    </div>
  );
}
