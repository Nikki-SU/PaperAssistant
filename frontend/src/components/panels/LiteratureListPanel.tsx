/**
 * 文献卡片列表（SPEC §六 / §8.1）。
 *
 * 列出 library/cards.csv 的所有卡片，支持搜索 + 上传 PDF。
 */
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { LiteratureCard, Project } from "../../api/client";

export function LiteratureListPanel({ project, notify }: {
  project: Project | null;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [cards, setCards] = useState<LiteratureCard[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    try {
      const r = await api.listLiterature(q || undefined);
      setCards(r.cards);
    } catch (e) {
      notify(`加载文献失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  async function onUpload(file: File) {
    setBusy(true);
    try {
      const r = await api.uploadPDF(file);
      notify(`已上传：${r.card.doi}（${r.mineru.success ? "MinerU OK" : "MinerU 待接入"}）`);
      await load();
    } catch (e) {
      notify(`上传失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lit-list">
      <div className="lit-toolbar">
        <input
          className="search-input"
          placeholder="搜索 DOI/标题/作者/关键词"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <button className="primary-btn" onClick={load} disabled={busy}>检索</button>
        <label className="upload-btn">
          <input
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onUpload(f);
              e.target.value = "";
            }}
          />
          上传 PDF
        </label>
        <span className="muted-small">项目：{project?.name ?? "未选"}</span>
      </div>
      <div className="lit-grid">
        {cards.length === 0 && <div className="empty-hint">还没有文献卡片</div>}
        {cards.map((c) => (
          <article key={c.doi} className="lit-card">
            <header>
              <code className="doi">{c.doi}</code>
              <span className={"status status-" + (c.status || "draft")}>{c.status || "draft"}</span>
            </header>
            <h4 className="lit-title">{c.title || "（无标题）"}</h4>
            <p className="muted-small">
              {c.journal || "—"} · {c.first_author || "—"}
            </p>
            {c.keywords && <p className="kw">关键词：{c.keywords}</p>}
            {c.abstract && <p className="abs">{c.abstract.slice(0, 240)}{c.abstract.length > 240 ? "…" : ""}</p>}
          </article>
        ))}
      </div>
    </div>
  );
}
