/**
 * Markdown 编辑器（SPEC §三 / §六 / §7.3：Vditor 所见即所得）。
 *
 * commit η.1 在 δ 基础上的改动：
 *  · 图片插入：替换 Vditor 内置 "upload"（后端无接口，原本是死按钮）为
 *    自定义 "insert-image"：本地选图 → FileReader 转 base64 → 直接 insertValue
 *    一条 `![alt](data:image/...;base64,...)` 内嵌进 draft.md。
 *    单文件、无外部依赖、符合"本地隐私优先"的设计。
 *    同时拦截粘贴/拖拽图片 → 同样走 base64 内嵌路径。
 *  · 表格插入：替换 Vditor 内置 "table"（默认硬塞 3×3 无对话）为
 *    自定义 "insert-table"：点击后弹出 WPS / Office 风格网格选择器
 *    （hover 高亮预览、点击确认插入 N×M 表格）。
 *  · 浮层定位在编辑区顶部，不是 modal dialog，遵守 USER.md「禁止弹窗」。
 *  · 其余（防抖保存、状态 badge、字数统计、切项目灌值）保持不变。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Vditor from "vditor";
import "vditor/dist/index.css";
import { api } from "../../api/client";
import type { Project } from "../../api/client";

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

const ICON_TABLE =
  '<svg viewBox="0 0 16 16" width="16" height="16">' +
  '<path fill="currentColor" d="M1.5 2.5h13a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zm.5 1V6h3.5V3.5H2zm4.5 0V6h2.5V3.5H6.5zm3.5 0V6h3.5V3.5H10zM2 7v2.5h3.5V7H2zm4.5 0v2.5h2.5V7H6.5zm3.5 0v2.5h3.5V7H10zM2 10.5v2h3.5v-2H2zm4.5 0v2h2.5v-2H6.5zm3.5 0v2h3.5v-2H10z"/>' +
  "</svg>";

const ICON_IMAGE =
  '<svg viewBox="0 0 16 16" width="16" height="16">' +
  '<path fill="currentColor" d="M2 2.5h12a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zm0 1v6.793L4.5 7.793l3 3 2.5-2.5 3 3V3.5H2zM11 5a1.25 1.25 0 1 1 0 2.5A1.25 1.25 0 0 1 11 5z"/>' +
  "</svg>";

const TABLE_PICKER_MAX_ROWS = 8;
const TABLE_PICKER_MAX_COLS = 10;
// 图片体积告警阈值（5MB 以上提醒会膨胀 draft.md）
const IMG_WARN_BYTES = 5 * 1024 * 1024;

function buildTableMarkdown(rows: number, cols: number): string {
  if (rows < 1 || cols < 1) return "";
  const cell = "   ";
  const sep = "---";
  const headerLine = "| " + Array(cols).fill(cell).join(" | ") + " |";
  const sepLine = "| " + Array(cols).fill(sep).join(" | ") + " |";
  const bodyLine = "| " + Array(cols).fill(cell).join(" | ") + " |";
  const lines: string[] = [headerLine, sepLine];
  for (let i = 0; i < rows - 1; i++) lines.push(bodyLine);
  return "\n" + lines.join("\n") + "\n";
}

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

  // 图片选择 input（隐藏）
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // 表格网格选择器状态
  const [tablePicker, setTablePicker] = useState<{
    visible: boolean;
    rows: number;
    cols: number;
  }>({ visible: false, rows: 0, cols: 0 });

  // 用 ref 持有最新闭包，便于 Vditor toolbar click 回调里调用
  const insertImageFromFileRef = useRef<(file: File) => void>(() => {});
  const openTablePickerRef = useRef<() => void>(() => {});
  const openFilePickerRef = useRef<() => void>(() => {});

  // ---- 图片：File → base64 → Markdown 内嵌 ----
  insertImageFromFileRef.current = (file: File) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      notify("仅支持图片文件（png / jpg / gif / webp）", "error");
      return;
    }
    if (file.size > IMG_WARN_BYTES) {
      notify(
        `图片偏大（${(file.size / 1024 / 1024).toFixed(1)}MB），内嵌会显著增加 draft.md 体积`,
        "warn"
      );
    }
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = reader.result;
      if (typeof b64 !== "string") {
        notify("读取图片失败", "error");
        return;
      }
      const altRaw = file.name.replace(/\.[^.]+$/, "").trim() || "image";
      const alt = altRaw.replace(/[\[\]\\]/g, "_");
      const md = `\n![${alt}](${b64})\n`;
      try {
        vditorRef.current?.insertValue(md);
      } catch {
        // 兜底：直接拼到内容尾部
        const next = (contentRef.current || "") + md;
        onChange(next);
      }
    };
    reader.onerror = () => notify("读取图片失败", "error");
    reader.readAsDataURL(file);
  };

  openFilePickerRef.current = () => {
    fileInputRef.current?.click();
  };

  openTablePickerRef.current = () => {
    setTablePicker({ visible: true, rows: 0, cols: 0 });
  };

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
        "link",
        {
          name: "insert-table",
          tip: "插入表格（选行列）",
          tipPosition: "n",
          icon: ICON_TABLE,
          click: () => openTablePickerRef.current(),
        },
        {
          name: "insert-image",
          tip: "插入图片（base64 内嵌，本地直存）",
          tipPosition: "n",
          icon: ICON_IMAGE,
          click: () => openFilePickerRef.current(),
        },
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
        // 接管粘贴/拖拽图片 → 走 base64 内嵌
        try {
          const editorEl = hostRef.current?.querySelector(
            ".vditor-wysiwyg .vditor-reset"
          ) as HTMLElement | null;
          if (editorEl) {
            editorEl.addEventListener("paste", (e: ClipboardEvent) => {
              const items = e.clipboardData?.items;
              if (!items) return;
              for (let i = 0; i < items.length; i++) {
                const it = items[i];
                if (it.kind === "file" && it.type.startsWith("image/")) {
                  const f = it.getAsFile();
                  if (f) {
                    e.preventDefault();
                    insertImageFromFileRef.current(f);
                  }
                }
              }
            });
            editorEl.addEventListener("drop", (e: DragEvent) => {
              const files = e.dataTransfer?.files;
              if (!files || files.length === 0) return;
              const imgs = Array.from(files).filter((f) =>
                f.type.startsWith("image/")
              );
              if (imgs.length === 0) return;
              e.preventDefault();
              imgs.forEach((f) => insertImageFromFileRef.current(f));
            });
          }
        } catch {
          /* ignore drop/paste binding errors */
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

  // ---- 表格选择器：ESC 关闭 ----
  useEffect(() => {
    if (!tablePicker.visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setTablePicker({ visible: false, rows: 0, cols: 0 });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tablePicker.visible]);

  const confirmTable = useCallback((rows: number, cols: number) => {
    if (rows < 1 || cols < 1) return;
    const md = buildTableMarkdown(rows, cols);
    try {
      vditorRef.current?.insertValue(md);
    } catch {
      const next = (contentRef.current || "") + md;
      onChange(next);
    }
    setTablePicker({ visible: false, rows: 0, cols: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onChange]);

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

      <div ref={hostRef} className="md-vditor-host">
        {tablePicker.visible && (
          <TablePickerOverlay
            rows={tablePicker.rows}
            cols={tablePicker.cols}
            maxRows={TABLE_PICKER_MAX_ROWS}
            maxCols={TABLE_PICKER_MAX_COLS}
            onHover={(r, c) =>
              setTablePicker((s) => ({ ...s, rows: r, cols: c }))
            }
            onPick={confirmTable}
            onClose={() =>
              setTablePicker({ visible: false, rows: 0, cols: 0 })
            }
          />
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) insertImageFromFileRef.current(f);
          // 允许重复选同一张图
          e.target.value = "";
        }}
      />

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

// ---------------- 表格网格选择器（inline overlay，非 modal） ----------------
function TablePickerOverlay(props: {
  rows: number;
  cols: number;
  maxRows: number;
  maxCols: number;
  onHover: (r: number, c: number) => void;
  onPick: (r: number, c: number) => void;
  onClose: () => void;
}) {
  const { rows, cols, maxRows, maxCols, onHover, onPick, onClose } = props;
  const grid: { r: number; c: number }[] = [];
  for (let r = 1; r <= maxRows; r++) {
    for (let c = 1; c <= maxCols; c++) {
      grid.push({ r, c });
    }
  }
  const label =
    rows > 0 && cols > 0 ? `${rows} 行 × ${cols} 列` : "拖动选择行列数";

  return (
    <div className="tbl-picker-backdrop" onClick={onClose}>
      <div
        className="tbl-picker-card"
        onClick={(e) => e.stopPropagation()}
        onMouseLeave={() => onHover(0, 0)}
      >
        <div className="tbl-picker-head">
          <span className="tbl-picker-title">插入表格</span>
          <span className="tbl-picker-label">{label}</span>
          <button
            className="tbl-picker-close"
            onClick={onClose}
            title="关闭 (Esc)"
          >
            ✕
          </button>
        </div>
        <div
          className="tbl-picker-grid"
          style={{
            gridTemplateColumns: `repeat(${maxCols}, 18px)`,
            gridTemplateRows: `repeat(${maxRows}, 18px)`,
          }}
        >
          {grid.map(({ r, c }) => {
            const on = r <= rows && c <= cols;
            return (
              <div
                key={`${r}-${c}`}
                className={`tbl-picker-cell${on ? " tbl-picker-cell-on" : ""}`}
                onMouseEnter={() => onHover(r, c)}
                onClick={() => onPick(r, c)}
              />
            );
          })}
        </div>
        <div className="tbl-picker-hint">
          鼠标悬停预览，点击确认插入；表格内可继续 Tab 加行
        </div>
      </div>
    </div>
  );
}
