/**
 * AI 对话面板（SPEC §六 / §7.x）。
 *
 * - 角色切换：assistant / auditor / secretary
 * - 调真 API：POST /api/ai/chat
 * - 错误友好提示：not_configured → 引导去设置；network → 给出诊断
 * - 审计 badge 来自后端返回（verified/suggestion/error/user）
 * - 输入框始终可用（即便未配置 Key 也可记笔记，回复时给出引导）
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { AIChatMessage, AIRole, Project } from "../../api/client";

type Audit = "verified" | "suggestion" | "user" | "error";

interface Msg {
  id: string;
  role: "user" | "assistant";
  text: string;
  audit: Audit;
  citations?: { doi: string; checked: boolean }[];
  errorCode?: string;
}

interface Props {
  project: Project | null;
  apiKeysReady: boolean;  // 来自 App 顶层（基于 settings snapshot）
  onOpenSettings: () => void;
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
}

const ROLE_LABEL: Record<AIRole, string> = {
  assistant: "助手",
  auditor: "审阅",
  secretary: "秘书",
};

export function AIChatPanel({ project, apiKeysReady, onOpenSettings, notify }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState<AIRole>("assistant");

  // 拉一次 AI 就绪状态，做角色级别的细化提示
  const [roleStatus, setRoleStatus] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    void api.aiStatus()
      .then((r) => {
        if (cancelled) return;
        const m: Record<string, boolean> = {};
        for (const it of r.items) m[it.role] = it.configured;
        setRoleStatus(m);
      })
      .catch(() => { /* 静默：可能后端未启动 */ });
    return () => { cancelled = true; };
  }, [apiKeysReady]);

  const currentRoleReady = roleStatus[role] ?? apiKeysReady;
  const headerStatusBadge = useMemo(() => {
    if (currentRoleReady) return <span className="badge-ok">● {ROLE_LABEL[role]} 就绪</span>;
    return (
      <span className="badge-warn">
        ● {ROLE_LABEL[role]} 未配置 ·{" "}
        <button className="link-btn" onClick={onOpenSettings}>去设置</button>
      </span>
    );
  }, [currentRoleReady, role, onOpenSettings]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const userMsg: Msg = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
      audit: "user",
    };
    setMessages((ms) => [...ms, userMsg]);
    setInput("");

    if (!currentRoleReady) {
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: `（${ROLE_LABEL[role]} 未配置）请到「设置 → AI 接口位 → ${role}」填入 Endpoint / Model / API Key。`,
        audit: "error",
        errorCode: "not_configured",
      }]);
      return;
    }

    setBusy(true);
    // 把当前会话作为上下文一并传给后端（仅传文本和角色）
    const history: AIChatMessage[] = messages
      .filter((m) => m.audit !== "error")
      .map((m) => ({
        role: m.role === "assistant" ? "assistant" : "user",
        content: m.text,
      }));
    history.push({ role: "user", content: text });

    try {
      const resp = await api.aiChat({
        role,
        messages: history,
        project: project?.name,
        stage: project?.stage,
      });
      const audit: Audit = resp.success
        ? (resp.audit_status === "user" ? "suggestion" : resp.audit_status)
        : "error";
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: resp.success ? (resp.output || "（AI 返回了空内容）") : `⚠ ${resp.error || "AI 调用失败"}`,
        audit,
        errorCode: resp.error_code || undefined,
      }]);
      if (!resp.success) {
        const tip = resp.error_code === "not_configured"
          ? "请到设置里补齐 endpoint/model/key。"
          : resp.error_code === "network"
            ? "网络连不上，检查 endpoint 与代理。"
            : resp.error_code === "http_error"
              ? "AI 服务返回错误，检查 Key 余额 / 模型名。"
              : "未知错误，已记录。";
        notify(`${ROLE_LABEL[role]} 调用失败：${tip}`, "warn");
      }
    } catch (e) {
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: `⚠ 请求失败：${String(e)}（请检查后端是否已启动 8181）`,
        audit: "error",
        errorCode: "network",
      }]);
      notify(`请求 /api/ai/chat 失败：${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  function toggleCitation(msgId: string, doi: string) {
    setMessages((ms) =>
      ms.map((m) => {
        if (m.id !== msgId || !m.citations) return m;
        return {
          ...m,
          citations: m.citations.map((c) =>
            c.doi === doi ? { ...c, checked: !c.checked } : c
          ),
        };
      })
    );
    notify(`已切换文献勾选 ${doi}`, "ok");
  }

  return (
    <div className="ai-chat">
      <div className="ai-chat-status">
        <div className="ai-role-tabs">
          {(["assistant", "auditor", "secretary"] as AIRole[]).map((r) => (
            <button
              key={r}
              className={`role-tab ${r === role ? "active" : ""}`}
              onClick={() => setRole(r)}
              title={r}
            >
              {ROLE_LABEL[r]}
              {!(roleStatus[r] ?? false) && <span className="role-tab-dot" />}
            </button>
          ))}
        </div>
        {headerStatusBadge}
        <span className="muted-small">
          当前项目：{project?.name ?? "未选"} · 阶段：{project?.stage ?? "—"}
        </span>
      </div>

      <div className="ai-chat-history">
        {messages.length === 0 && (
          <div className="empty-hint">
            还没有对话。在下面输入你的问题或要求，{ROLE_LABEL[role]} 会回应。Ctrl+Enter 发送。
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={"ai-msg ai-msg-" + m.role}>
            <div className="ai-msg-head">
              <span className="msg-role">{m.role === "user" ? "你" : ROLE_LABEL[role]}</span>
              <AuditBadge audit={m.audit} />
            </div>
            <div className="ai-msg-body">{m.text}</div>
            {m.errorCode === "not_configured" && (
              <div className="ai-msg-cta">
                <button className="link-btn" onClick={onOpenSettings}>去设置 →</button>
              </div>
            )}
            {m.citations && m.citations.length > 0 && (
              <div className="ai-citations">
                <div className="citations-title">交互式文献勾选：</div>
                {m.citations.map((c) => (
                  <label key={c.doi} className="citation-checkbox">
                    <input
                      type="checkbox"
                      checked={c.checked}
                      onChange={() => toggleCitation(m.id, c.doi)}
                    />
                    <code>{c.doi}</code>
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="ai-msg ai-msg-assistant">
            <div className="ai-msg-head">
              <span className="msg-role">{ROLE_LABEL[role]}</span>
              <span className="audit-badge audit-suggestion">思考中…</span>
            </div>
            <div className="ai-msg-body muted-small">（请稍候，正在调用远端模型）</div>
          </div>
        )}
      </div>

      <div className="ai-chat-input">
        <textarea
          rows={3}
          placeholder={busy ? "正在等待回复…" : "输入消息，Ctrl+Enter 发送"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button className="primary-btn" onClick={() => void send()} disabled={busy}>
          {busy ? "发送中…" : "发送"}
        </button>
      </div>
    </div>
  );
}

function AuditBadge({ audit }: { audit: Audit }) {
  if (audit === "verified") {
    return <span className="audit-badge audit-verified">✓ 已核查</span>;
  }
  if (audit === "suggestion") {
    return <span className="audit-badge audit-suggestion">建议</span>;
  }
  if (audit === "error") {
    return <span className="audit-badge audit-error">⚠ 错误</span>;
  }
  return <span className="audit-badge audit-user">用户</span>;
}
