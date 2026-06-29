/**
 * 设置对话框（SPEC §四.5 / §五.1）。
 *
 * - 数据根目录（切换需重启提示）
 * - 监控目录
 * - 4 个 AI 接口位（mineru/assistant/auditor/secretary）—— Key 不回显，只显 set/unset
 *   - endpoint 预填官方地址，用户可改
 *   - model 留空，不预填，给 placeholder 指引
 *   - 每个角色附「获取 Key」官方链接 + 简短教程提示
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

interface RoleMeta {
  label: string;
  desc: string;
  keyUrl: string;
  keyUrlLabel: string;
  hint: string;
  modelPlaceholder: string;
  endpointPlaceholder: string;
}

const ROLE_META: Record<string, RoleMeta> = {
  mineru: {
    label: "MinerU（PDF 解析）",
    desc: "把上传的 PDF 转成可结构化的 Markdown，是文献入库的第一步。",
    keyUrl: "https://mineru.net/apiManage/token",
    keyUrlLabel: "去 mineru.net 申请 API Token",
    hint: "登录 mineru.net → 控制台 → API 管理 → 创建 Token，复制粘贴到下方。每日有免费额度。",
    modelPlaceholder: "MinerU 不需要填 model，留空即可",
    endpointPlaceholder: "https://mineru.net/api/v4",
  },
  assistant: {
    label: "助手 AI（主对话）",
    desc: "默认对话角色，写综述、起草章节、做思路探索都走它。",
    keyUrl: "https://platform.deepseek.com/api_keys",
    keyUrlLabel: "去 platform.deepseek.com 申请 API Key",
    hint: "推荐 DeepSeek：注册账号 → API Keys → Create new key。也可填其他 OpenAI 兼容服务的 Key。",
    modelPlaceholder: "如 deepseek-chat / deepseek-reasoner",
    endpointPlaceholder: "https://api.deepseek.com/v1",
  },
  auditor: {
    label: "审阅 AI（事实核查）",
    desc: "对助手生成内容做事实核查（SPEC §4.3）；建议用更强或更严谨的模型。",
    keyUrl: "https://platform.deepseek.com/api_keys",
    keyUrlLabel: "去 platform.deepseek.com 申请 API Key",
    hint: "可以和助手共用 Key、用不同 model；也可以接独立账号防止额度互相抢。",
    modelPlaceholder: "如 deepseek-reasoner（更严谨）",
    endpointPlaceholder: "https://api.deepseek.com/v1",
  },
  secretary: {
    label: "秘书 AI（错别字/语法）",
    desc: "做修订和润色等轻量任务；未配置时系统会自动回退到助手。",
    keyUrl: "https://platform.deepseek.com/api_keys",
    keyUrlLabel: "去 platform.deepseek.com 申请 API Key",
    hint: "可选。不填则修订环节复用助手 Key/Model。",
    modelPlaceholder: "如 deepseek-chat（轻量任务）",
    endpointPlaceholder: "https://api.deepseek.com/v1",
  },
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
          <p className="muted-small">
            所有 Key 由你本人在此填写，软件不会内置任何 Key。Key 保存在
            <code> data_root/config/api_keys.secret</code>（仅本机权限 600），永不上传、永不回显明文。
          </p>
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
  const meta = ROLE_META[role.role] ?? {
    label: role.role,
    desc: "",
    keyUrl: "",
    keyUrlLabel: "",
    hint: "",
    modelPlaceholder: "如 gpt-4o / doubao-pro",
    endpointPlaceholder: "如 https://api.openai.com/v1",
  };
  const [endpoint, setEndpoint] = useState(role.endpoint);
  const [model, setModel] = useState(role.model);
  const [timeout_, setTimeout_] = useState(role.timeout || "120");
  const [keyDraft, setKeyDraft] = useState("");

  return (
    <div className="api-role-card">
      <div className="api-role-head">
        <strong>{meta.label}</strong>
        <span className={role.api_key_set ? "badge-ok" : "badge-warn"}>
          {role.api_key_set ? "● Key 已配置" : "● 未配置"}
        </span>
      </div>
      {meta.desc && <p className="muted-small role-desc">{meta.desc}</p>}
      {meta.keyUrl && (
        <p className="muted-small role-key-link">
          🔑 <a href={meta.keyUrl} target="_blank" rel="noreferrer">{meta.keyUrlLabel}</a>
          {meta.hint && <span className="role-hint"> · {meta.hint}</span>}
        </p>
      )}
      <div className="grid-2">
        <label>
          Endpoint
          <input
            className="text-input"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder={meta.endpointPlaceholder}
          />
        </label>
        <label>
          Model
          <input
            className="text-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={meta.modelPlaceholder}
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
