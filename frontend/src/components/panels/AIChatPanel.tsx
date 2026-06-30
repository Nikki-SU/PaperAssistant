/**
 * AI 对话面板（SPEC §4.3 / §六 — commit δ 重写）。
 *
 * 与上一版的根本区别：
 *  · ❌ 删除「task_type 选择器」——SPEC §4.3 真正本意是 AI 自判触发，不该人手挑
 *  · ❌ 删除「sources 编辑区」——日常聊天用户没法填，且 AI 自判含 claimed_sources
 *  · ✅ 仍保留角色 tabs（assistant/auditor/secretary）
 *  · ✅ 后端统一发 task_type="free_chat"，由 backend ai.py 注入的 SELF_JUDGE_GUARD 让助手自判
 *    输出 {content, category, claimed_sources}，后端按 category 分流：
 *      - factual_summary + 非空 claimed_sources → 自动 verify_with_auditor 5 轮
 *      - suggestion → 直接展示，标 💡 建议
 *      - free → 直接展示，标 💬 自由
 *      - 撒谎防御：声称 factual_summary 但 claimed_sources 空 → 强制降级 suggestion
 *  · ✅ 保留 AuditBadge（审阅状态）+ 手动 🔍 事实核查兜底按钮
 *  · ✅ 错误友好提示：not_configured → 引导去设置
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type {
  AIChatMessage,
  AIRole,
  AuditStatus,
  Project,
} from "../../api/client";

interface Msg {
  id: string;
  role: "user" | "assistant";
  text: string;
  audit: AuditStatus;
  category?: string;          // AI 自判：factual_summary | suggestion | free
  claimedSources?: string[];  // AI 自判：声称的来源（DOI / 教材名等）
  auditRounds?: number;
  auditFeedback?: string;
  auditLogPath?: string;
  auditDropped?: boolean;
  errorCode?: string;
  // 手动核查兜底
  verifyState?: "idle" | "running" | "verified" | "failed" | "not_configured" | "error";
  verifyFeedback?: string;
  verifyRounds?: number;
  verifyDropped?: boolean;
}

interface Props {
  project: Project | null;
  apiKeysReady: boolean;
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
  const [roleStatus, setRoleStatus] = useState<Record<string, boolean>>({});

  // 拉 AI 角色就绪状态
  useEffect(() => {
    let cancelled = false;
    void api.aiStatus()
      .then((r) => {
        if (cancelled) return;
        const m: Record<string, boolean> = {};
        for (const it of r.items) m[it.role] = it.configured;
        setRoleStatus(m);
      })
      .catch(() => { /* 静默 */ });
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
        audit: "not_configured",
        errorCode: "not_configured",
      }]);
      return;
    }

    setBusy(true);
    const history: AIChatMessage[] = messages
      .filter((m) => m.audit !== "error" && m.audit !== "not_configured")
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
        // commit δ：固定 free_chat，由后端 SELF_JUDGE_GUARD 让 AI 自判 category
        task_type: "free_chat",
        sources: [],
      });

      // 从后端响应中读取 AI 自判结果（向后兼容旧字段）
      const extraAny = resp as unknown as {
        self_judge_category?: string;
        claimed_sources?: string[];
      };
      const category = extraAny.self_judge_category;
      const claimedSources = extraAny.claimed_sources;

      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: resp.success
          ? (resp.audit_dropped
              ? "（AI 自判为事实总结，但审阅 5 轮未通过，内容已自动丢弃，不入库。请补充更可信的来源或换种问法。）"
              : (resp.output || "（AI 返回了空内容）"))
          : `⚠ ${resp.error || "AI 调用失败"}`,
        audit: resp.success ? resp.audit_status : "error",
        auditRounds: resp.audit_rounds,
        auditFeedback: resp.audit_feedback,
        auditLogPath: resp.audit_log_path,
        auditDropped: resp.audit_dropped,
        category,
        claimedSources,
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
      } else if (resp.audit_status === "verified") {
        notify(`AI 自判为事实总结，已通过事实核查（${resp.audit_rounds} 轮）`, "ok");
      } else if (resp.audit_status === "failed" && resp.audit_dropped) {
        notify(`事实核查 5 轮未通过，内容已硬丢弃（不入库）`, "error");
      } else if (resp.audit_status === "not_configured") {
        notify(`审阅 AI 未配置；本条 AI 输出未经核查，请到设置面板填写`, "warn");
      } else if (resp.audit_status === "suggestion") {
        notify(`AI 自判为「建议」（非事实结论）`, "ok");
      }
    } catch (e) {
      const msg = String(e);
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: `⚠ 请求失败：${msg}（请检查后端是否已启动 8181）`,
        audit: "error",
        errorCode: "network",
      }]);
      notify(`请求 /api/ai/chat 失败：${msg}`, "error");
    } finally {
      setBusy(false);
    }
  }

  // 手动核查（兜底：当用户怀疑 AI 自判错误时，强制再核一遍）
  async function verifyMsg(msgId: string) {
    const m = messages.find((x) => x.id === msgId);
    if (!m || m.role !== "assistant" || !m.text.trim()) return;
    setMessages((arr) => arr.map((x) =>
      x.id === msgId ? { ...x, verifyState: "running" } : x
    ));
    try {
      const resp = await api.aiVerify({
        content: m.text,
        sources: [],  // 用户不再编辑 sources；审阅 AI 直接比对 AI 自己声称的来源
        project: project?.name,
        max_rounds: 5,
      });
      setMessages((arr) => arr.map((x) => {
        if (x.id !== msgId) return x;
        const next: Msg = { ...x };
        next.verifyState = resp.status;
        next.verifyFeedback = resp.last_feedback;
        next.verifyRounds = resp.rounds;
        next.verifyDropped = resp.status === "failed";
        if (resp.status === "verified") {
          next.audit = "verified";
          if (resp.final_content && resp.final_content !== x.text) {
            next.text = resp.final_content;
          }
        } else if (resp.status === "failed") {
          next.audit = "failed";
          next.auditDropped = true;
          next.text = "（手动事实核查 5 轮未通过，内容已自动丢弃。）";
        }
        return next;
      }));
      if (resp.status === "failed") {
        notify(`事实核查 5 轮未通过，内容已丢弃（不会入库）`, "error");
      } else if (resp.status === "verified") {
        notify(`事实核查通过（${resp.rounds} 轮）`, "ok");
      } else if (resp.status === "not_configured") {
        notify(`审阅 AI 未配置，请到设置面板填写`, "warn");
      } else {
        notify(`事实核查出错：${resp.last_feedback}`, "error");
      }
    } catch (e) {
      setMessages((arr) => arr.map((x) =>
        x.id === msgId ? { ...x, verifyState: "error", verifyFeedback: String(e) } : x
      ));
      notify(`事实核查请求失败：${e}`, "error");
    }
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

      <div className="ai-self-judge-hint muted-small">
        💬 自然对话即可。助手 AI 会自己判断你的请求属于「事实总结」「建议」或「自由聊天」——
        声称来自具体文献时会自动触发审阅 AI 5 轮事实核查；建议性内容标「💡 建议」。
      </div>

      <div className="ai-chat-history">
        {messages.length === 0 && (
          <div className="empty-hint">
            还没有对话。直接输入问题，AI 会自判分流。Ctrl+Enter 发送。
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={"ai-msg ai-msg-" + m.role}>
            <div className="ai-msg-head">
              <span className="msg-role">{m.role === "user" ? "你" : ROLE_LABEL[role]}</span>
              {m.category && (
                <span className={`msg-category msg-cat-${m.category}`}>
                  {m.category === "factual_summary" && "🔒 事实总结"}
                  {m.category === "suggestion" && "💡 建议"}
                  {m.category === "free" && "💬 自由"}
                </span>
              )}
              <AuditBadge audit={m.audit} rounds={m.auditRounds} dropped={m.auditDropped} />
            </div>
            <div className="ai-msg-body">{m.text}</div>
            {m.claimedSources && m.claimedSources.length > 0 && (
              <details className="ai-msg-sources">
                <summary>AI 声称的来源（{m.claimedSources.length} 条）</summary>
                <ul>
                  {m.claimedSources.map((s, i) => (
                    <li key={i}><code>{s}</code></li>
                  ))}
                </ul>
              </details>
            )}
            {m.auditFeedback && (m.audit === "failed" || m.audit === "verified") && (
              <details className="ai-msg-feedback">
                <summary>审阅反馈（{m.auditRounds} 轮）</summary>
                <pre>{m.auditFeedback}</pre>
                {m.auditLogPath && <div className="muted-small">日志：{m.auditLogPath}</div>}
              </details>
            )}
            {m.errorCode === "not_configured" && (
              <div className="ai-msg-cta">
                <button className="link-btn" onClick={onOpenSettings}>去设置 →</button>
              </div>
            )}
            {/* 手动核查兜底（任何 assistant 消息都可触发） */}
            {m.role === "assistant" && !m.errorCode && (
              <div className="ai-msg-verify">
                {(!m.verifyState || m.verifyState === "idle") && (
                  <button
                    className="link-btn"
                    onClick={() => void verifyMsg(m.id)}
                    title="让审阅 AI 重新检查本条内容（覆盖 AI 自判）"
                  >🔍 手动事实核查</button>
                )}
                {m.verifyState === "running" && (
                  <span className="muted-small">审阅中…（最多 5 轮）</span>
                )}
                {m.verifyState === "verified" && (
                  <span className="verify-badge verify-pass">
                    ✓ 已通过事实核查（{m.verifyRounds} 轮）
                  </span>
                )}
                {m.verifyState === "failed" && (
                  <div className="verify-failed-box">
                    <div className="verify-failed-title">
                      ✗ 事实核查 5 轮未通过 · 内容已自动丢弃（不会入库）
                    </div>
                    {m.verifyFeedback && (
                      <pre className="verify-failed-feedback">{m.verifyFeedback}</pre>
                    )}
                  </div>
                )}
                {m.verifyState === "not_configured" && (
                  <span className="verify-badge verify-warn">
                    审阅 AI 未配置 · <button className="link-btn" onClick={onOpenSettings}>去设置</button>
                  </span>
                )}
                {m.verifyState === "error" && (
                  <span className="verify-badge verify-warn">
                    审阅出错：{m.verifyFeedback?.slice(0, 80)}
                  </span>
                )}
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
            <div className="ai-msg-body muted-small">
              （AI 正在自判分类。声称来自具体文献时会自动事实核查最多 5 轮）
            </div>
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

function AuditBadge({
  audit,
  rounds,
  dropped,
}: {
  audit: AuditStatus;
  rounds?: number;
  dropped?: boolean;
}) {
  if (audit === "verified") {
    return (
      <span className="audit-badge audit-verified">
        ✓ 已核查{rounds ? `（${rounds}轮）` : ""}
      </span>
    );
  }
  if (audit === "failed") {
    return (
      <span className="audit-badge audit-failed">
        ✗ 核查失败{dropped ? " · 已丢弃" : ""}
      </span>
    );
  }
  if (audit === "not_configured") {
    return <span className="audit-badge audit-not-configured">⚙ 审阅未配置</span>;
  }
  if (audit === "suggestion") {
    return <span className="audit-badge audit-suggestion">💡 建议</span>;
  }
  if (audit === "error") {
    return <span className="audit-badge audit-error">⚠ 错误</span>;
  }
  return <span className="audit-badge audit-user">用户</span>;
}
