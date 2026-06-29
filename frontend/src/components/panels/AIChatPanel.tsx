/**
 * AI 对话面板（SPEC §六 / §7.x）。
 *
 * 当前阶段：占位 + 真实接口接入引导。
 * - 若 4 个 AI 接口位未配置：显示"请先去设置配置 API Key"
 * - 配置好后：当前用 echo 占位（B 计划接入真实 SDK 时替换 client.ts.chat 即可）
 * - 含审计状态标识（来自审阅 AI）和交互式勾选组件占位
 *
 * 输入框始终可用，方便用户先记笔记；真实对话调用待 B 计划。
 */
import { useState } from "react";
import type { Project } from "../../api/client";

type Audit = "verified" | "suggestion" | "user";
interface Msg {
  id: string;
  role: "user" | "assistant";
  text: string;
  audit: Audit;
  citations?: { doi: string; checked: boolean }[];
}

interface Props {
  project: Project | null;
  apiKeysReady: boolean;
  onOpenSettings: () => void;
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
}

export function AIChatPanel({ project, apiKeysReady, onOpenSettings, notify }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");

  function send() {
    if (!input.trim()) return;
    const userMsg: Msg = {
      id: `u-${Date.now()}`,
      role: "user",
      text: input,
      audit: "user",
    };
    setMessages((ms) => [...ms, userMsg]);
    setInput("");

    if (!apiKeysReady) {
      const warn: Msg = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: "（AI 接口未配置）请先去「设置」配置助手 API Key。否则我没法真的回答。",
        audit: "user",
      };
      setMessages((ms) => [...ms, warn]);
      return;
    }

    // 占位回复（B 计划替换）
    const fake: Msg = {
      id: `a-${Date.now()}`,
      role: "assistant",
      text: `（占位回复 · 待接入真实 AI）我收到了你的输入：「${userMsg.text}」`,
      audit: "suggestion",
    };
    setMessages((ms) => [...ms, fake]);
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
        {apiKeysReady ? (
          <span className="badge-ok">● AI 接口已就绪</span>
        ) : (
          <span className="badge-warn">
            ● AI 接口未配置 ·{" "}
            <button className="link-btn" onClick={onOpenSettings}>去设置</button>
          </span>
        )}
        <span className="muted-small">
          当前项目：{project?.name ?? "未选"} · 阶段：{project?.stage ?? "—"}
        </span>
      </div>

      <div className="ai-chat-history">
        {messages.length === 0 && (
          <div className="empty-hint">
            还没有对话。在下面输入你的问题或要求，AI 会根据当前阶段给出回应。
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={"ai-msg ai-msg-" + m.role}>
            <div className="ai-msg-head">
              <span className="msg-role">{m.role === "user" ? "你" : "助手"}</span>
              <AuditBadge audit={m.audit} />
            </div>
            <div className="ai-msg-body">{m.text}</div>
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
      </div>

      <div className="ai-chat-input">
        <textarea
          rows={3}
          placeholder="输入消息，Ctrl+Enter 发送"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="primary-btn" onClick={send}>发送</button>
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
  return <span className="audit-badge audit-user">用户</span>;
}
