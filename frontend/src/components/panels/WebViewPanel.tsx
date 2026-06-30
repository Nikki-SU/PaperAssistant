/**
 * 搜索网站面板（SPEC §六）。
 *
 * 设计要点（用户钦定）：
 *   - **只给一个关键词输入框**，按 Enter 触发；无独立"搜索"按钮、无 URL 输入框
 *   - **搜索源由用户自己配置**，预置 x-mol / cnki 两个待填模板
 *   - URL 模板用 `{query}` 占位符；前端用 encodeURIComponent 拼装
 *   - **iframe 不暴露 URL 栏前缀**，用户感觉是软件原生功能
 *   - 切 tab 时若已有关键词则自动用新源重搜，否则清空 iframe
 *   - 添加/编辑源走**内联浮层**，不弹窗（USER.md 禁止弹窗）
 *   - 数据落 data_root/config/search_sources.md（铁律 2：Markdown 落盘）
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import type { SearchSource } from "../../api/client";

interface Props {
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
}

interface EditorState {
  mode: "create" | "edit";
  id?: string;
  name: string;
  url_template: string;
}

function buildIframeUrl(template: string, query: string): string {
  const q = query.trim();
  if (!template.trim() || !q) return "";
  // 标准占位符 {query}；同时兼容 {q}（少数站点习惯）
  const encoded = encodeURIComponent(q);
  if (template.includes("{query}")) return template.replaceAll("{query}", encoded);
  if (template.includes("{q}")) return template.replaceAll("{q}", encoded);
  // 兜底：模板末尾直接拼
  return template + encoded;
}

export function WebViewPanel({ notify }: Props) {
  const [sources, setSources] = useState<SearchSource[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [keyword, setKeyword] = useState<string>("");
  const [iframeSrc, setIframeSrc] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [savingEditor, setSavingEditor] = useState<boolean>(false);
  const keywordRef = useRef<HTMLInputElement | null>(null);

  // ---- 拉源列表 ----
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.listSearchSources();
      setSources(r.items);
      // 默认选第一个；如果原选中项不在了，回退到第一个
      setActiveId((cur) => {
        if (cur && r.items.some((s) => s.id === cur)) return cur;
        return r.items[0]?.id ?? null;
      });
    } catch (e) {
      notify(`加载搜索源失败：${String(e)}`, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const active = useMemo(
    () => sources.find((s) => s.id === activeId) ?? null,
    [sources, activeId]
  );

  // 切 tab 时，若已有关键词则自动重搜；否则清空
  useEffect(() => {
    if (!active) {
      setIframeSrc("");
      return;
    }
    if (!keyword.trim()) {
      setIframeSrc("");
      return;
    }
    const url = buildIframeUrl(active.url_template, keyword);
    setIframeSrc(url);
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- 关键词回车 ----
  function onKeywordKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (!active) {
      notify("请先选择一个搜索源", "warn");
      return;
    }
    if (!active.url_template.trim()) {
      notify(`「${active.name}」尚未配置 URL 模板，请点击 ⚙ 编辑`, "warn");
      return;
    }
    if (!keyword.trim()) return;
    const url = buildIframeUrl(active.url_template, keyword);
    setIframeSrc(url);
  }

  // ---- 编辑器 ----
  function openCreate() {
    setEditor({ mode: "create", name: "", url_template: "" });
  }

  function openEdit(s: SearchSource) {
    setEditor({ mode: "edit", id: s.id, name: s.name, url_template: s.url_template });
  }

  function closeEditor() {
    setEditor(null);
  }

  async function saveEditor() {
    if (!editor) return;
    const name = editor.name.trim();
    if (!name) {
      notify("请填写搜索源名称", "warn");
      return;
    }
    setSavingEditor(true);
    try {
      if (editor.mode === "create") {
        const r = await api.createSearchSource({ name, url_template: editor.url_template.trim() });
        notify(`已添加搜索源「${r.item.name}」`);
        await reload();
        setActiveId(r.item.id);
      } else if (editor.id) {
        const r = await api.updateSearchSource(editor.id, {
          name,
          url_template: editor.url_template.trim(),
        });
        notify(`已更新「${r.item.name}」`);
        await reload();
        // 编辑当前活跃源 → 立刻用新模板重新搜（若有关键词）
        if (editor.id === activeId && keyword.trim()) {
          setIframeSrc(buildIframeUrl(r.item.url_template, keyword));
        }
      }
      setEditor(null);
    } catch (e) {
      notify(`保存搜索源失败：${String(e)}`, "error");
    } finally {
      setSavingEditor(false);
    }
  }

  async function deleteCurrent() {
    if (!active) return;
    if (sources.length <= 1) {
      notify("至少保留一个搜索源", "warn");
      return;
    }
    if (!window.confirm(`确定删除搜索源「${active.name}」？`)) return;
    try {
      await api.deleteSearchSource(active.id);
      notify(`已删除「${active.name}」`);
      await reload();
    } catch (e) {
      notify(`删除失败：${String(e)}`, "error");
    }
  }

  // ---- 占位提示 ----
  const placeholderHint = useMemo(() => {
    if (loading) return "加载中…";
    if (!active) return "暂无搜索源，请点击 + 添加";
    if (!active.url_template.trim())
      return `「${active.name}」尚未配置 URL 模板\n点击右上角 ⚙ 编辑，填写形如 "https://www.x-mol.com/paper?q={query}" 的模板`;
    if (!keyword.trim()) return `在上方输入关键词，按 Enter 在「${active.name}」内搜索`;
    return "";
  }, [loading, active, keyword]);

  return (
    <div className="ss-pane">
      {/* 顶部：tab 切换 + 编辑/添加/删除 */}
      <div className="ss-tabs-row">
        <div className="ss-tabs" role="tablist">
          {sources.map((s) => {
            const isActive = s.id === activeId;
            const hasTpl = !!s.url_template.trim();
            return (
              <button
                key={s.id}
                role="tab"
                aria-selected={isActive}
                className={`ss-tab${isActive ? " ss-tab-active" : ""}${hasTpl ? "" : " ss-tab-empty"}`}
                onClick={() => setActiveId(s.id)}
                title={hasTpl ? s.url_template : "尚未配置 URL 模板"}
              >
                {s.name}
                {!hasTpl && <span className="ss-tab-dot" aria-hidden>●</span>}
              </button>
            );
          })}
          <button
            className="ss-tab-add"
            onClick={openCreate}
            title="添加搜索源"
            aria-label="添加搜索源"
          >
            +
          </button>
        </div>
        <div className="ss-actions">
          {active && (
            <>
              <button
                className="ss-icon-btn"
                onClick={() => openEdit(active)}
                title="编辑当前搜索源"
                aria-label="编辑"
              >
                ⚙
              </button>
              <button
                className="ss-icon-btn ss-icon-danger"
                onClick={deleteCurrent}
                title="删除当前搜索源"
                aria-label="删除"
                disabled={sources.length <= 1}
              >
                ×
              </button>
            </>
          )}
        </div>
      </div>

      {/* 关键词输入：唯一的输入框 */}
      <div className="ss-keyword-row">
        <input
          ref={keywordRef}
          className="ss-keyword"
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={onKeywordKeyDown}
          placeholder={active ? `在「${active.name}」中搜索…按 Enter` : "请先选择搜索源"}
          autoFocus
        />
      </div>

      {/* 主体：iframe 或占位 */}
      <div className="ss-frame-wrap">
        {iframeSrc ? (
          <iframe
            className="ss-frame"
            src={iframeSrc}
            title={active?.name || "search"}
            referrerPolicy="no-referrer-when-downgrade"
          />
        ) : (
          <div className="ss-placeholder" role="status">
            <pre>{placeholderHint}</pre>
            {active && !active.url_template.trim() && (
              <button className="primary-btn" onClick={() => openEdit(active)}>
                立即填写模板
              </button>
            )}
          </div>
        )}
      </div>

      {/* 内联浮层（非弹窗）：添加 / 编辑搜索源 */}
      {editor && (
        <div className="ss-editor-overlay" onClick={closeEditor}>
          <div className="ss-editor-card" onClick={(e) => e.stopPropagation()}>
            <div className="ss-editor-title">
              {editor.mode === "create" ? "添加搜索源" : `编辑「${editor.name || "..."}」`}
            </div>
            <label className="ss-editor-label">
              名称
              <input
                type="text"
                value={editor.name}
                onChange={(e) => setEditor((cur) => (cur ? { ...cur, name: e.target.value } : cur))}
                placeholder="例如 x-mol / cnki / arXiv"
                maxLength={64}
              />
            </label>
            <label className="ss-editor-label">
              URL 模板
              <input
                type="text"
                value={editor.url_template}
                onChange={(e) =>
                  setEditor((cur) => (cur ? { ...cur, url_template: e.target.value } : cur))
                }
                placeholder="https://www.x-mol.com/paper?q={query}"
                spellCheck={false}
              />
            </label>
            <div className="ss-editor-hint">
              提示：在目标网站搜一次任意关键词，把浏览器地址栏的 URL 复制过来，把关键词替换为{" "}
              <code>{"{query}"}</code> 占位符。
            </div>
            <div className="ss-editor-actions">
              <button className="ghost-btn" onClick={closeEditor} disabled={savingEditor}>
                取消
              </button>
              <button className="primary-btn" onClick={saveEditor} disabled={savingEditor}>
                {savingEditor ? "保存中…" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
