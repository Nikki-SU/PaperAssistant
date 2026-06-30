/**
 * Markdown 编辑器（SPEC §三 / §六 / §7.3：Vditor 所见即所得）。
 *
 * 与上一版的区别（commit δ 重写）：
 *  · 砍掉 textarea + 自渲染 preview 双栏，违反 USER.md「WPS智能文档风格 / 禁止编辑/预览切换」
 *  · 接入 Vditor wysiwyg 模式：单视图所见即所得（与 SPEC §三 "Markdown 编辑器 Vditor" 完全一致）
 *  · Vditor 自带工具栏（H1-3 / 加粗 / 斜体 / 列表 / 引用 / 表格 / 链接 / 图片 / 代码 / 公式 / 撤销 ...）
 *  · 保留：切项目加载 draft / 防抖 1.5s 自动保存 / 字数统计 / 状态 badge / 手动保存按钮
 *  · 工程兼容：Vditor 内部维护值，通过 input 回调推到外层 onChange；切项目时 setValue
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Vditor from "vditor";
import "vditor/dist/index.css";
import { api } from "../../api/client";
import type { Project } from "../../api/client";

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

export function MarkdownEditorPanel(props: {
  project: Project | null;
  content: string;
  onChange: (s: string) => void;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const { project, content, onChange, notify } = props;

  const hostRef = useRef<HTMLDivElement | null>(null);
  const vditorRef = useRef<Vditor | null>(null);
  const readyRef = useRef(false);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [savedAt, setSavedAt] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const debounceTimerRef = useRef<number | null>(null);
  const lastSavedRef = useRef<string>("");
  const contentRef = useRef<string>(content);
  contentRef.current = content;

  // ---- 初始化 Vditor（仅一次） ----
  useEffect(() => {
    if (!hostRef.current) return;
    if (vditorRef.current) return;
    const v = new Vditor(hostRef.current, {
      height: "100%",
      mode: "wysiwyg",
      cache: { enable: false },
      placeholder: "请先在左栏选择项目或开始写正文...",
      toolbar: [
        "headings", "bold", "italic", "strike", "|",
        "list", "ordered-list", "check", "outdent", "indent", "|",
        "quote", "line", "code", "inline-code", "code-theme", "|",
        "link", "table", "|",
        "upload",
        "|",
        "undo", "redo", "|",
        "fullscreen", "edit-mode",
      ],
      preview: {
        math: { engine: "KaTeX" },
        hljs: { enable: true },
      },
      input: (value: string) => {
        // 把 Vditor 当前值推到外层 React state
        if (!readyRef.current) return;
        onChange(value);
      },
      after: () => {
        readyRef.current = true;
        // 用挂载时上层传进来的 content 作为初值（项目切换钩在下面）
        try {
          v.setValue(contentRef.current || "");
        } catch {
          /* ignore */
        }
      },
    });
    vditorRef.current = v;
    return () => {
      readyRef.current = false;
      try {
        v.destroy();
      } catch {
        /* ignore */
      }
      vditorRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- 切换项目 → 加载该项目的 draft.md → 灌入 Vditor ----
  useEffect(() => {
    if (!project) {
      setLoaded(false);
      return;
    }
    setLoaded(false);
    setStatus("idle");
    void (async () => {
      try {
        const text = await api.getDraft(project.name);
        const seed = text || "# 我的论文草稿\n\n在这里写正文。\n";
        onChange(seed);
        lastSavedRef.current = text;
        // 等 Vditor ready 后塞值
        const tryFill = () => {
          if (readyRef.current && vditorRef.current) {
            try {
              vditorRef.current.setValue(seed);
            } catch {
              /* ignore */
            }
          } else {
            window.setTimeout(tryFill, 50);
          }
        };
        tryFill();
        setLoaded(true);
        setStatus("saved");
        setSavedAt(new Date().toLocaleTimeString());
      } catch (e) {
        setLoaded(true);
        notify(`加载草稿失败: ${String(e)}`, "error");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.name]);

  const doSave = useCallback(
    async (manual: boolean) => {
      if (!project) {
        if (manual) notify("未选项目，无法保存", "warn");
        return;
      }
      setStatus("saving");
      try {
        const r = await api.saveDraft(project.name, contentRef.current);
        lastSavedRef.current = contentRef.current;
        setStatus("saved");
        setSavedAt(new Date(r.saved_at).toLocaleTimeString());
        if (manual) notify(`已保存 (${r.bytes} 字节)`, "ok");
      } catch (e) {
        setStatus("error");
        notify(`保存失败: ${String(e)}`, "error");
      }
    },
    [project, notify]
  );

  // ---- 内容变化 → 标 dirty + 防抖自动保存 ----
  useEffect(() => {
    if (!loaded || !project) return;
    if (content === lastSavedRef.current) {
      setStatus("saved");
      return;
    }
    setStatus("dirty");
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = window.setTimeout(() => {
      void doSave(false);
    }, 1500);
    return () => {
      if (debounceTimerRef.current) {
        window.clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, loaded]);

  // 字数 / 行数 / 字节
  const stats = useMemo(() => {
    const lines = content.split("\n").length;
    const chars = content.length;
    const bytes = new Blob([content]).size;
    const cjk = (content.match(/[\u4e00-\u9fff]/g) ?? []).length;
    const words = (content.match(/[A-Za-z]+/g) ?? []).length;
    return { lines, chars, bytes, cjk, words };
  }, [content]);

  const statusBadge = (() => {
    switch (status) {
      case "saved":
        return <span className="md-status md-status-saved">● 已保存 {savedAt}</span>;
      case "dirty":
        return <span className="md-status md-status-dirty">○ 未保存</span>;
      case "saving":
        return <span className="md-status md-status-saving">↻ 保存中…</span>;
      case "error":
        return <span className="md-status md-status-error">⚠ 保存失败</span>;
      default:
        return <span className="md-status">—</span>;
    }
  })();

  return (
    <div className="md-editor md-editor-wysiwyg">
      <div className="md-topbar">
        <button
          className="primary-btn md-save-btn"
          onClick={() => void doSave(true)}
          disabled={!project || status === "saving"}
        >
          保存
        </button>
        {statusBadge}
        <span className="muted-small md-topbar-hint">
          所见即所得编辑器（Vditor wysiwyg）· 1.5s 自动保存
        </span>
      </div>

      <div ref={hostRef} className="md-vditor-host" />

      <div className="md-statusbar">
        <span className="muted-small">
          {project ? (
            <code>projects/{project.name}/paper/draft.md</code>
          ) : (
            <span>（未选项目，编辑不会持久化）</span>
          )}
        </span>
        <span className="muted-small">
          行 {stats.lines} · 字符 {stats.chars} · 字节 {stats.bytes}
          {stats.cjk > 0 && <> · 中文 {stats.cjk}</>}
          {stats.words > 0 && <> · 英文 {stats.words}</>}
        </span>
      </div>
    </div>
  );
}
