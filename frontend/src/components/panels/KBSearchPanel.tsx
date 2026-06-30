/**
 * 知识库检索（SPEC §六）。
 *
 * F2 阶段真实化：
 *  · 关键词输入 + 学科 selector（可选）
 *  · 调 listKnowledgeCards({subject?, q?, limit})
 *  · 结果列表显示 title / source_book / summary / audited 徽章
 *  · 点击结果 → 展示完整 Markdown
 *
 * commit β 新增：
 *  · 详情抽屉里如果 source_book 存在 → 「查看教材原文」按钮
 *    GET /api/knowledge/textbooks/{subject}/{name}
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { KnowledgeCard, SubjectInfo, Project } from "../../api/client";

type DetailView = "card" | "textbook";

export function KBSearchPanel({
  project,
  notify,
}: {
  project: Project | null;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [subjects, setSubjects] = useState<SubjectInfo[]>([]);
  const [q, setQ] = useState("");
  const [subject, setSubject] = useState("");
  const [results, setResults] = useState<KnowledgeCard[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [openCard, setOpenCard] = useState<KnowledgeCard | null>(null);
  const [openMd, setOpenMd] = useState<string>("");
  const [view, setView] = useState<DetailView>("card");
  const [tbBody, setTbBody] = useState<string>("");
  const [tbLoading, setTbLoading] = useState(false);

  const loadSubjects = useCallback(async () => {
    try {
      const r = await api.listSubjects();
      setSubjects(r.subjects);
    } catch (e) {
      notify(`加载学科失败: ${String(e)}`, "error");
    }
  }, [notify]);

  useEffect(() => {
    void loadSubjects();
  }, [loadSubjects]);

  const doSearch = useCallback(async () => {
    setBusy(true);
    try {
      const r = await api.listKnowledgeCards(subject || undefined, q.trim() || undefined);
      setResults(r.cards);
      setTotal(r.total);
      if (q.trim() && r.cards.length === 0) {
        notify(`没有匹配「${q}」的卡片`, "warn");
      }
    } catch (e) {
      notify(`检索失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }, [q, subject, notify]);

  async function openDetail(c: KnowledgeCard) {
    setOpenCard(c);
    setView("card");
    setTbBody("");
    setOpenMd("加载中…");
    try {
      const md = await api.getKnowledgeCardMarkdown(c.card_id);
      setOpenMd(md);
    } catch (e) {
      setOpenMd(`加载失败: ${String(e)}`);
    }
  }

  function closeDetail() {
    setOpenCard(null);
    setView("card");
    setTbBody("");
    setOpenMd("");
  }

  async function openTextbook() {
    if (!openCard?.subject || !openCard?.source_book) {
      notify("当前卡片没有标注教材来源", "warn");
      return;
    }
    setView("textbook");
    setTbLoading(true);
    setTbBody("加载中…");
    try {
      const txt = await api.getTextbookContent(openCard.subject, openCard.source_book);
      setTbBody(txt);
    } catch (e) {
      setTbBody(`加载失败: ${String(e)}`);
      notify(`加载教材原文失败: ${String(e)}`, "error");
    } finally {
      setTbLoading(false);
    }
  }

  return (
    <div className="kb-search">
      <div className="kb-search-form">
        <input
          className="search-input"
          placeholder="输入关键词（标题 / 摘要 / 提问），回车检索"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void doSearch()}
          style={{ flex: 1 }}
        />
        <select
          className="search-input"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={{ width: 160 }}
        >
          <option value="">（全部学科）</option>
          {subjects.map((s) => (
            <option key={s.subject} value={s.subject}>
              {s.subject} ({s.card_count})
            </option>
          ))}
        </select>
        <button className="primary-btn" onClick={() => void doSearch()} disabled={busy}>
          {busy ? "检索中…" : "检索"}
        </button>
      </div>

      <div className="muted-small kb-search-hint">
        当前项目：<code>{project?.name ?? "未选"}</code>
        {" · "}
        知识库位置：<code>data_root/knowledge/</code>
        {" · "}
        总命中：{total} 张
      </div>

      <div className="kb-search-results">
        {results.length === 0 && !busy && q && (
          <div className="empty-hint">没有匹配的卡片。换个关键词试试？</div>
        )}
        {results.length === 0 && !busy && !q && (
          <div className="empty-hint">输入关键词后回车开始检索；空关键词可列出全部卡片。</div>
        )}
        {results.map((c) => (
          <article key={c.card_id} className="kb-search-row" onClick={() => void openDetail(c)}>
            <header className="kb-search-row-head">
              <span className="kb-subject-tag">{c.subject}</span>
              <strong className="kb-search-row-title">{c.title}</strong>
              {c.audited === "true" ? (
                <span className="kb-audited-badge">✓ 已审计</span>
              ) : (
                <span className="kb-unaudited-badge">未审计</span>
              )}
            </header>
            <p className="muted-small">
              {c.source_book && <>📖 {c.source_book}</>}
              {c.source_section && <> · §{c.source_section}</>}
            </p>
            {c.summary && <p className="kb-search-row-sum">{c.summary}</p>}
          </article>
        ))}
      </div>

      {openCard && (
        <div className="kb-detail-overlay" onClick={closeDetail}>
          <div className="kb-detail-panel" onClick={(e) => e.stopPropagation()}>
            <header className="kb-detail-head">
              <h3>{openCard.title}</h3>
              <button className="close-btn" onClick={closeDetail}>
                ✕
              </button>
            </header>
            <div className="muted-small kb-detail-meta">
              学科：{openCard.subject}
              {openCard.source_book && <> · 课本：{openCard.source_book}</>}
              {openCard.source_section && <> · 章节：{openCard.source_section}</>}
              {" · "}
              {openCard.audited === "true" ? (
                <span className="kb-audited-badge">✓ 已审计</span>
              ) : (
                <span className="kb-unaudited-badge">未审计</span>
              )}
            </div>

            <div className="lit-detail-actions" style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0" }}>
              <button
                className={view === "card" ? "primary-btn" : "secondary-btn"}
                onClick={() => setView("card")}
              >
                卡片 Markdown
              </button>
              <button
                className={view === "textbook" ? "primary-btn" : "secondary-btn"}
                onClick={() => void openTextbook()}
                disabled={!openCard.source_book || tbLoading}
                title={
                  openCard.source_book
                    ? "GET /api/knowledge/textbooks/{subject}/{name}"
                    : "该卡片未标注教材来源"
                }
              >
                {tbLoading ? "加载中…" : openCard.source_book ? `📖 教材原文：${openCard.source_book}` : "📖 教材原文（无来源）"}
              </button>
            </div>

            {view === "card" ? (
              <pre className="kb-detail-md">{openMd}</pre>
            ) : (
              <pre className="kb-detail-md" style={{ whiteSpace: "pre-wrap" }}>
                {tbBody || "(空)"}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
