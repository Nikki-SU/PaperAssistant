/**
 * AI 对话面板（SPEC §4.3 / §六 / §7.x）。
 *
 * - 角色切换：assistant / auditor / secretary
 * - **任务类型选择器**：12 种任务（6 必须 + 4 建议 + 2 自由），后端自动按 policy 走核查
 * - **sources 编辑区**：必须类任务时至少填 1 条来源片段，否则后端 422
 * - 调真 API：POST /api/ai/chat
 * - 错误友好提示：not_configured → 引导去设置
 * - 审计 badge 来自后端 audit_status（6 种）
 * - 🔍 手动核查按钮：仅在 free_chat/other 兜底显示
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type {
  AIChatMessage,
  AIChatTaskType,
  AIRole,
  AuditStatus,
  ChatSource,
  Project,
  TaskTypeInfo,
} from "../../api/client";

interface Msg {
  id: string;
  role: "user" | "assistant";
  text: string;
  audit: AuditStatus;
  taskType?: AIChatTaskType;
  taskLabel?: string;
  auditRounds?: number;
  auditFeedback?: string;
  auditLogPath?: string;
  auditDropped?: boolean;
  citations?: { doi: string; checked: boolean }[];
  errorCode?: string;
  // 手动核查兜底（仅 free_chat / other）
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

// 默认 task_type：自由对话
const DEFAULT_TASK: AIChatTaskType = "free_chat";

export function AIChatPanel({ project, apiKeysReady, onOpenSettings, notify }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState<AIRole>("assistant");

  // 任务类型
  const [taskTypes, setTaskTypes] = useState<TaskTypeInfo[]>([]);
  const [taskType, setTaskType] = useState<AIChatTaskType>(DEFAULT_TASK);

  // sources 编辑：(title, snippet) 列表
  const [sources, setSources] = useState<ChatSource[]>([]);
  const [showSourcesEditor, setShowSourcesEditor] = useState(false);

  // 角色状态
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

  // 拉任务类型枚举
  useEffect(() => {
    let cancelled = false;
    void api.aiTaskTypes()
      .then((r) => {
        if (cancelled) return;
        setTaskTypes(r.items);
      })
      .catch(() => { /* 静默 */ });
    return () => { cancelled = true; };
  }, []);

  const currentTaskInfo = useMemo<TaskTypeInfo | null>(
    () => taskTypes.find((t) => t.key === taskType) ?? null,
    [taskType, taskTypes]
  );

  // 切换任务类型时自动展开/收起 sources 区
  useEffect(() => {
    if (currentTaskInfo?.requires_sources) {
      setShowSourcesEditor(true);
    } else {
      setShowSourcesEditor(false);
    }
  }, [currentTaskInfo?.requires_sources]);

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

  function addSource() {
    setSources((arr) => [...arr, { title: "", snippet: "" }]);
  }
  function updateSource(idx: number, patch: Partial<ChatSource>) {
    setSources((arr) => arr.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }
  function removeSource(idx: number) {
    setSources((arr) => arr.filter((_, i) => i !== idx));
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    // 前端校验：必须类必须至少 1 条 sources
    if (currentTaskInfo?.requires_sources) {
      const valid = sources.filter((s) => s.snippet.trim().length > 0);
      if (valid.length === 0) {
        notify(`「${currentTaskInfo.label}」必须提供至少 1 条来源片段（snippet）`, "error");
        return;
      }
    }

    const userMsg: Msg = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
      audit: "user",
      taskType,
      taskLabel: currentTaskInfo?.label,
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

    // 拼 sources 给后端
    const submittedSources: ChatSource[] = currentTaskInfo?.requires_sources
      ? sources.filter((s) => s.snippet.trim().length > 0)
      : sources.filter((s) => s.snippet.trim().length > 0);  // 即便不强制，用户填了也带上

    try {
      const resp = await api.aiChat({
        role,
        messages: history,
        project: project?.name,
        stage: project?.stage,
        task_type: taskType,
        sources: submittedSources,
      });
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: resp.success
          ? (resp.audit_dropped
              ? "（事实核查 5 轮未通过，内容已自动丢弃，不入库。请补充更可信的来源后重试。）"
              : (resp.output || "（AI 返回了空内容）"))
          : `⚠ ${resp.error || "AI 调用失败"}`,
        audit: resp.success ? resp.audit_status : "error",
        auditRounds: resp.audit_rounds,
        auditFeedback: resp.audit_feedback,
        auditLogPath: resp.audit_log_path,
        auditDropped: resp.audit_dropped,
        taskType: (resp.task_type as AIChatTaskType) || taskType,
        taskLabel: resp.task_label || currentTaskInfo?.label,
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
        notify(`已自动通过事实核查（${resp.audit_rounds} 轮）`, "ok");
      } else if (resp.audit_status === "failed" && resp.audit_dropped) {
        notify(`事实核查 5 轮未通过，内容已硬丢弃（不入库）`, "error");
      } else if (resp.audit_status === "not_configured") {
        notify(`审阅 AI 未配置，无法自动核查；请先到设置面板填写`, "warn");
      } else if (resp.audit_status === "suggestion") {
        notify(`已生成「建议」内容（非事实性结论）`, "ok");
      }
    } catch (e) {
      // 422 = 必须类缺 sources
      const msg = String(e);
      const isMissingSources = /HTTP 422/.test(msg);
      setMessages((ms) => [...ms, {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: isMissingSources
          ? `⚠ 当前任务「${currentTaskInfo?.label}」必须事实核查，请先在 sources 编辑区填入来源片段。`
          : `⚠ 请求失败：${msg}（请检查后端是否已启动 8181）`,
        audit: "error",
        errorCode: isMissingSources ? "missing_sources" : "network",
      }]);
      notify(isMissingSources ? `缺少来源片段，已拒绝` : `请求 /api/ai/chat 失败：${msg}`, "error");
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

  // 手动核查（仅 free_chat / other 兜底）
  async function verifyMsg(msgId: string) {
    const m = messages.find((x) => x.id === msgId);
    if (!m || m.role !== "assistant" || !m.text.trim()) return;
    setMessages((arr) => arr.map((x) =>
      x.id === msgId ? { ...x, verifyState: "running" } : x
    ));
    try {
      const resp = await api.aiVerify({
        content: m.text,
        sources: sources.filter((s) => s.snippet.trim().length > 0),
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

  // 任务分组渲染
  const groupedTasks = useMemo(() => {
    const must = taskTypes.filter((t) => t.policy === "must_audit");
    const sugg = taskTypes.filter((t) => t.policy === "suggestion");
    const free = taskTypes.filter((t) => t.policy === "free");
    return { must, sugg, free };
  }, [taskTypes]);

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

      {/* 任务类型选择器（SPEC §4.3） */}
      <div className="ai-task-selector">
        <label className="ai-task-label">任务类型：</label>
        <select
          className="ai-task-select"
          value={taskType}
          onChange={(e) => setTaskType(e.target.value as AIChatTaskType)}
          disabled={busy}
        >
          {groupedTasks.must.length > 0 && (
            <optgroup label="🔒 必须事实核查（自动）">
              {groupedTasks.must.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </optgroup>
          )}
          {groupedTasks.sugg.length > 0 && (
            <optgroup label="💡 建议（非事实结论）">
              {groupedTasks.sugg.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </optgroup>
          )}
          {groupedTasks.free.length > 0 && (
            <optgroup label="💬 自由对话">
              {groupedTasks.free.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </optgroup>
          )}
        </select>
        {currentTaskInfo && (
          <span className={`task-policy-tag policy-${currentTaskInfo.policy}`}>
            {currentTaskInfo.policy === "must_audit" && "🔒 自动核查"}
            {currentTaskInfo.policy === "suggestion" && "💡 仅建议"}
            {currentTaskInfo.policy === "free" && "💬 自由"}
          </span>
        )}
      </div>

      {/* sources 编辑区（必须类强制，其它可选） */}
      {showSourcesEditor && (
        <div className="ai-sources-editor">
          <div className="ai-sources-head">
            <span className="ai-sources-title">
              来源片段 {currentTaskInfo?.requires_sources && <span className="required-star">*</span>}
            </span>
            <button className="link-btn" onClick={addSource} disabled={busy}>+ 添加</button>
            {!currentTaskInfo?.requires_sources && (
              <button className="link-btn" onClick={() => setShowSourcesEditor(false)} disabled={busy}>收起</button>
            )}
          </div>
          {sources.length === 0 && (
            <div className="muted-small">
              {currentTaskInfo?.requires_sources
                ? `「${currentTaskInfo.label}」必须至少 1 条来源片段（snippet），否则后端拒绝（422）`
                : "可选：贴入原文片段以便审阅核查"}
            </div>
          )}
          {sources.map((s, i) => (
            <div key={i} className="source-row">
              <input
                type="text"
                placeholder="标题/DOI（可选）"
                value={s.title ?? ""}
                onChange={(e) => updateSource(i, { title: e.target.value })}
                disabled={busy}
                className="source-title-input"
              />
              <textarea
                rows={2}
                placeholder="原文片段（snippet，必填）"
                value={s.snippet}
                onChange={(e) => updateSource(i, { snippet: e.target.value })}
                disabled={busy}
                className="source-snippet-input"
              />
              <button className="link-btn link-btn-danger" onClick={() => removeSource(i)} disabled={busy}>
                删除
              </button>
            </div>
          ))}
        </div>
      )}
      {!showSourcesEditor && !currentTaskInfo?.requires_sources && (
        <div className="ai-sources-collapsed">
          <button className="link-btn" onClick={() => setShowSourcesEditor(true)} disabled={busy}>
            ＋ 添加来源（可选）
          </button>
        </div>
      )}

      <div className="ai-chat-history">
        {messages.length === 0 && (
          <div className="empty-hint">
            还没有对话。先选择任务类型，必要时填入来源片段，然后输入消息。Ctrl+Enter 发送。
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={"ai-msg ai-msg-" + m.role}>
            <div className="ai-msg-head">
              <span className="msg-role">{m.role === "user" ? "你" : ROLE_LABEL[role]}</span>
              {m.taskLabel && <span className="msg-task-label">[{m.taskLabel}]</span>}
              <AuditBadge audit={m.audit} rounds={m.auditRounds} dropped={m.auditDropped} />
            </div>
            <div className="ai-msg-body">{m.text}</div>
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
            {/* 手动核查按钮：仅 free_chat / other 兜底 */}
            {m.role === "assistant"
              && !m.errorCode
              && (m.taskType === "free_chat" || m.taskType === "other")
              && (
              <div className="ai-msg-verify">
                {(!m.verifyState || m.verifyState === "idle") && (
                  <button
                    className="link-btn"
                    onClick={() => void verifyMsg(m.id)}
                    title="让审阅 AI 检查本条内容是否与原文一致（最多 5 轮）"
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
            <div className="ai-msg-body muted-small">
              （正在调用远端模型
              {currentTaskInfo?.policy === "must_audit" && "，必须类任务会自动事实核查最多 5 轮"}
              ）
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
