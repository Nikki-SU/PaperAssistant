/**
 * 知识库卡片列表（SPEC §六 / §8.2）。
 *
 * F2 阶段真实化：
 *  · 顶部学科 selector（listSubjects）+ 按学科筛选卡片
 *  · 卡片网格：title / source_book / source_section / summary / audited 徽章
 *  · 点击卡片 → 右侧抽屉显示完整 Markdown（getKnowledgeCardMarkdown）
 *  · 刷新按钮 + 卡片数量统计
 *  · 卡片创建/删除入口：后续 G 阶段 chat 自动写入；这里只读 + 删除
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { KnowledgeCard, SubjectInfo } from "../../api/client";

export function KBCardListPanel({
  notify,
}: {
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [subjects, setSubjects] = useState<SubjectInfo[]>([]);
  const [activeSubject, setActiveSubject] = useState<string>("");
  const [cards, setCards] = useState<KnowledgeCard[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [openCard, setOpenCard] = useState<KnowledgeCard | null>(null);
  const [openMd, setOpenMd] = useState<string>("");

  const loadSubjects = useCallback(async () => {
    try {
      const r = await api.listSubjects();
      setSubjects(r.subjects);
    } catch (e) {
      notify(`加载学科失败: ${String(e)}`, "error");
    }
  }, [notify]);

  const loadCards = useCallback(async () => {
    setBusy(true);
    try {
      const r = await api.listKnowledgeCards(activeSubject || undefined);
      setCards(r.cards);
      setTotal(r.total);
    } catch (e) {
      notify(`加载卡片失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }, [activeSubject, notify]);

  useEffect(() => {
    void loadSubjects();
    void loadCards();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadCards();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSubject]);

  async function openDetail(c: KnowledgeCard) {
    setOpenCard(c);
    setOpenMd("加载中…");
    try {
      const md = await api.getKnowledgeCardMarkdown(c.card_id);
      setOpenMd(md);
    } catch (e) {
      setOpenMd(`加载失败: ${String(e)}`);
    }
  }

  async function deleteCard(c: KnowledgeCard) {
    if (!confirm(`删除卡片「${c.title}」？此操作不可逆。`)) return;
    try {
      await api.deleteKnowledgeCard(c.card_id);
      notify(`已删除：${c.title}`, "ok");
      if (openCard?.card_id === c.card_id) {
        setOpenCard(null);
        setOpenMd("");
      }
      await loadCards();
      await loadSubjects();
    } catch (e) {
      notify(`删除失败: ${String(e)}`, "error");
    }
  }

  return (
    <div className="kb-list">
      <div className="kb-list-toolbar">
        <label className="muted-small">学科：</label>
        <select
          className="search-input"
          value={activeSubject}
          onChange={(e) => setActiveSubject(e.target.value)}
          style={{ width: 180 }}
        >
          <option value="">（全部学科）</option>
          {subjects.map((s) => (
            <option key={s.subject} value={s.subject}>
              {s.subject} · {s.card_count} 卡 / {s.textbook_count} 课本
            </option>
          ))}
        </select>
        <button className="primary-btn" onClick={() => void loadCards()} disabled={busy}>
          刷新
        </button>
        <span className="muted-small">
          共 {total} 张卡片
          {activeSubject && <>（学科：{activeSubject}）</>}
        </span>
      </div>

      <div className="kb-grid">
        {cards.length === 0 && !busy && (
          <div className="empty-hint">
            没有知识库卡片。
            <br />
            在 AI 对话中选用 <code>generate_knowledge_card</code> 任务类型，附上来源即可自动入库。
          </div>
        )}
        {cards.map((c) => (
          <article key={c.card_id} className="kb-card" onClick={() => void openDetail(c)}>
            <header className="kb-card-head">
              <span className="kb-subject-tag">{c.subject}</span>
              {c.audited === "true" && <span className="kb-audited-badge">✓ 已审计</span>}
              {c.audited !== "true" && <span className="kb-unaudited-badge">未审计</span>}
            </header>
            <h4 className="kb-card-title">{c.title}</h4>
            <p className="muted-small">
              {c.source_book && <>📖 {c.source_book}</>}
              {c.source_section && <> · §{c.source_section}</>}
            </p>
            {c.summary && <p className="kb-card-summary">{c.summary}</p>}
            <footer className="kb-card-foot muted-small">
              <code>{c.card_id.slice(0, 12)}…</code>
              <button
                className="kb-card-del"
                title="删除"
                onClick={(e) => {
                  e.stopPropagation();
                  void deleteCard(c);
                }}
              >
                🗑
              </button>
            </footer>
          </article>
        ))}
      </div>

      {openCard && (
        <div className="kb-detail-overlay" onClick={() => setOpenCard(null)}>
          <div className="kb-detail-panel" onClick={(e) => e.stopPropagation()}>
            <header className="kb-detail-head">
              <h3>{openCard.title}</h3>
              <button className="close-btn" onClick={() => setOpenCard(null)}>
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
            <pre className="kb-detail-md">{openMd}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
