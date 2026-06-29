/**
 * 文献卡片列表（SPEC §六 / §8.1）。
 *
 * F3 阶段增强：
 *  · 已有：列表 + 关键词检索 + 上传 PDF
 *  · 新增：点击卡片显示详情抽屉（完整字段 + abstract 完整版）
 *  · 上传后显示 MinerU 进度（success / placeholder）
 *  · 文件大小提示（超 100MB 警告）+ 进度态
 */
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { LiteratureCard, Project } from "../../api/client";

export function LiteratureListPanel({
  project,
  notify,
}: {
  project: Project | null;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [cards, setCards] = useState<LiteratureCard[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [openCard, setOpenCard] = useState<LiteratureCard | null>(null);

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

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onUpload(file: File) {
    // SPEC §九：单文件 ≤200 页 / 100MB；超出前端先警告
    const sizeMB = file.size / (1024 * 1024);
    if (sizeMB > 100) {
      if (!confirm(`文件 ${file.name} 大小 ${sizeMB.toFixed(1)} MB，超出 SPEC §九 单文件 100MB 限制。仍要上传？\n（如果是 PDF，后端会按 200 页切分后调 MinerU）`)) {
        return;
      }
    }
    setUploading(true);
    try {
      const r = await api.uploadPDF(file);
      const mineruMsg = r.mineru.success
        ? `MinerU 成功${r.mineru.page_count ? `（${r.mineru.page_count} 页${r.mineru.truncated ? " · 已切分" : ""}）` : "（占位模式）"}`
        : `MinerU 失败：${r.mineru.message}`;
      notify(`已上传：${r.card.doi || file.name} · ${mineruMsg}`, r.mineru.success ? "ok" : "warn");
      await load();
    } catch (e) {
      notify(`上传失败: ${String(e)}`, "error");
    } finally {
      setUploading(false);
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
        <button className="primary-btn" onClick={load} disabled={busy}>
          {busy ? "检索中…" : "检索"}
        </button>
        <label className={"upload-btn " + (uploading ? "disabled" : "")}>
          <input
            type="file"
            accept="application/pdf"
            hidden
            disabled={uploading}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onUpload(f);
              e.target.value = "";
            }}
          />
          {uploading ? "上传中…" : "上传 PDF"}
        </label>
        <span className="muted-small">项目：{project?.name ?? "未选"} · 共 {cards.length} 篇</span>
      </div>
      <div className="lit-grid">
        {cards.length === 0 && !busy && <div className="empty-hint">还没有文献卡片，点「上传 PDF」开始建库</div>}
        {cards.map((c) => (
          <article
            key={c.doi}
            className="lit-card"
            onClick={() => setOpenCard(c)}
            title="点击查看详情"
          >
            <header>
              <code className="doi">{c.doi}</code>
              <span className={"status status-" + (c.status || "draft")}>{c.status || "draft"}</span>
            </header>
            <h4 className="lit-title">{c.title || "（无标题）"}</h4>
            <p className="muted-small">
              {c.journal || "—"} · {c.first_author || "—"}
            </p>
            {c.keywords && <p className="kw">关键词：{c.keywords}</p>}
            {c.abstract && (
              <p className="abs">
                {c.abstract.slice(0, 240)}
                {c.abstract.length > 240 ? "…" : ""}
              </p>
            )}
          </article>
        ))}
      </div>

      {openCard && (
        <div className="kb-detail-overlay" onClick={() => setOpenCard(null)}>
          <div className="kb-detail-panel" onClick={(e) => e.stopPropagation()}>
            <header className="kb-detail-head">
              <h3>{openCard.title || "（无标题）"}</h3>
              <button className="close-btn" onClick={() => setOpenCard(null)}>
                ✕
              </button>
            </header>
            <div className="muted-small kb-detail-meta">
              <div>
                <strong>DOI：</strong>
                <code>{openCard.doi}</code>
              </div>
              <div>
                <strong>期刊：</strong>
                {openCard.journal || "—"}
              </div>
              <div>
                <strong>一作：</strong>
                {openCard.first_author || "—"}
              </div>
              {openCard.corresponding_author && (
                <div>
                  <strong>通讯：</strong>
                  {openCard.corresponding_author}
                </div>
              )}
              {openCard.category && (
                <div>
                  <strong>分类：</strong>
                  {openCard.category}
                  {openCard.subcategory && <> / {openCard.subcategory}</>}
                </div>
              )}
              {openCard.keywords && (
                <div>
                  <strong>关键词：</strong>
                  {openCard.keywords}
                </div>
              )}
              <div>
                <strong>状态：</strong>
                <span className={"status status-" + (openCard.status || "draft")}>
                  {openCard.status || "draft"}
                </span>
              </div>
              <div>
                <strong>更新：</strong>
                {openCard.last_modified || "—"}
              </div>
            </div>
            {openCard.abstract && (
              <>
                <h4 style={{ marginTop: 12 }}>摘要</h4>
                <pre className="kb-detail-md" style={{ whiteSpace: "pre-wrap" }}>
                  {openCard.abstract}
                </pre>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
