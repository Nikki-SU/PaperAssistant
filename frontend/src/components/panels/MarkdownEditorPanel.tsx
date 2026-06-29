/**
 * Markdown 编辑器（SPEC §六 / §7.3：所见即所得）。
 *
 * F1 阶段真实化（不引入 Milkdown 依赖，避免阻塞中国大陆 npm 安装）：
 *  · 顶部工具栏：H1/H2/H3/B/I/code/list/quote/link/image/table/math
 *  · 增强 Markdown 渲染：标题/段落/列表/引用/链接/图片/表格/inline `$..$` & block `$$..$$` 公式占位
 *  · 联动后端：onMount → getDraft；防抖 1.5s 自动保存到 paper/draft.md；手动保存按钮
 *  · 字数 / 行数 / 字节统计；保存状态指示（saved / dirty / saving / error）
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [savedAt, setSavedAt] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const debounceTimerRef = useRef<number | null>(null);
  const lastSavedRef = useRef<string>("");

  // ---- 切换项目 → 加载该项目的 draft.md ----
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
        onChange(text || "# 我的论文草稿\n\n在这里写正文。\n");
        lastSavedRef.current = text;
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

  const doSave = useCallback(
    async (manual: boolean) => {
      if (!project) {
        if (manual) notify("未选项目，无法保存", "warn");
        return;
      }
      setStatus("saving");
      try {
        const r = await api.saveDraft(project.name, content);
        lastSavedRef.current = content;
        setStatus("saved");
        setSavedAt(new Date(r.saved_at).toLocaleTimeString());
        if (manual) notify(`已保存 (${r.bytes} 字节)`, "ok");
      } catch (e) {
        setStatus("error");
        notify(`保存失败: ${String(e)}`, "error");
      }
    },
    [project, content, notify]
  );

  // ---- 工具栏：在光标处插入文本 ----
  function insertAtCursor(before: string, after: string = "", placeholder: string = "") {
    const ta = taRef.current;
    if (!ta) return;
    const start = ta.selectionStart ?? content.length;
    const end = ta.selectionEnd ?? content.length;
    const selected = content.slice(start, end) || placeholder;
    const next = content.slice(0, start) + before + selected + after + content.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + before.length + selected.length;
      ta.setSelectionRange(pos, pos);
    });
  }

  function insertLine(prefix: string, placeholder: string) {
    const ta = taRef.current;
    if (!ta) return;
    const start = ta.selectionStart ?? content.length;
    // 移到行首
    let lineStart = start;
    while (lineStart > 0 && content[lineStart - 1] !== "\n") lineStart--;
    const linePrefix = content.slice(lineStart, start);
    if (linePrefix.length > 0) {
      // 在新行插
      const next = content.slice(0, start) + "\n" + prefix + placeholder + content.slice(start);
      onChange(next);
      requestAnimationFrame(() => {
        ta.focus();
        const pos = start + 1 + prefix.length + placeholder.length;
        ta.setSelectionRange(pos, pos);
      });
    } else {
      const next = content.slice(0, start) + prefix + placeholder + content.slice(start);
      onChange(next);
      requestAnimationFrame(() => {
        ta.focus();
        const pos = start + prefix.length + placeholder.length;
        ta.setSelectionRange(pos, pos);
      });
    }
  }

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
    <div className="md-editor">
      <div className="md-toolbar">
        <ToolbarBtn label="H1" title="一级标题 Ctrl+1" onClick={() => insertLine("# ", "标题")} />
        <ToolbarBtn label="H2" title="二级标题 Ctrl+2" onClick={() => insertLine("## ", "标题")} />
        <ToolbarBtn label="H3" title="三级标题 Ctrl+3" onClick={() => insertLine("### ", "标题")} />
        <ToolbarSep />
        <ToolbarBtn label="B" title="加粗" bold onClick={() => insertAtCursor("**", "**", "粗体")} />
        <ToolbarBtn label="I" title="斜体" italic onClick={() => insertAtCursor("*", "*", "斜体")} />
        <ToolbarBtn label="` `" title="行内代码" onClick={() => insertAtCursor("`", "`", "code")} />
        <ToolbarSep />
        <ToolbarBtn label="• 列表" title="无序列表" onClick={() => insertLine("- ", "条目")} />
        <ToolbarBtn label="1. 编号" title="有序列表" onClick={() => insertLine("1. ", "条目")} />
        <ToolbarBtn label="❝引用" title="引用块" onClick={() => insertLine("> ", "引用内容")} />
        <ToolbarSep />
        <ToolbarBtn
          label="链接"
          title="插入链接 [text](url)"
          onClick={() => insertAtCursor("[", "](https://)", "链接文本")}
        />
        <ToolbarBtn
          label="图片"
          title="插入图片 ![alt](url)"
          onClick={() => insertAtCursor("![", "](https://)", "alt")}
        />
        <ToolbarBtn
          label="表格"
          title="插入表格"
          onClick={() =>
            insertLine("", "| 列1 | 列2 |\n| --- | --- |\n| a | b |\n")
          }
        />
        <ToolbarSep />
        <ToolbarBtn label="$..$" title="行内公式 KaTeX" onClick={() => insertAtCursor("$", "$", "x^2")} />
        <ToolbarBtn
          label="$$..$$"
          title="独立公式块"
          onClick={() => insertAtCursor("\n$$\n", "\n$$\n", "E = mc^2")}
        />
        <ToolbarSep />
        <button
          className="primary-btn md-save-btn"
          onClick={() => void doSave(true)}
          disabled={!project || status === "saving"}
        >
          保存
        </button>
        {statusBadge}
      </div>

      <div className="md-editor-grid">
        <textarea
          ref={taRef}
          className="md-source"
          value={content}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            project
              ? "在这里写 Markdown...\n\n支持工具栏快捷插入、自动保存到 paper/draft.md。\n切换到右栏「LaTeX 预览」可实时查看转换效果。"
              : "请先在左栏选择一个项目"
          }
          spellCheck={false}
        />
        <div className="md-preview">
          <SimpleMdPreview source={content} />
        </div>
      </div>

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

function ToolbarBtn(props: {
  label: string;
  title: string;
  onClick: () => void;
  bold?: boolean;
  italic?: boolean;
}) {
  const style: React.CSSProperties = {};
  if (props.bold) style.fontWeight = 700;
  if (props.italic) style.fontStyle = "italic";
  return (
    <button className="md-tool-btn" title={props.title} onClick={props.onClick} style={style}>
      {props.label}
    </button>
  );
}

function ToolbarSep() {
  return <span className="md-tool-sep" />;
}

// ===================== 增强 Markdown 渲染 =====================
// 支持：标题 H1-6 / 段落 / 列表 / 引用 / 代码块 / 行内代码 / 加粗 / 斜体 /
//       表格 / 链接 / 图片 / 行内 $..$ 与块 $$..$$（占位渲染，不实际计算）
function SimpleMdPreview({ source }: { source: string }) {
  const html = renderMd(source);
  return <div className="md-preview-content" dangerouslySetInnerHTML={{ __html: html }} />;
}

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMd(src: string): string {
  // 先把块公式 $$...$$ 占位（多行）
  const blockMaths: string[] = [];
  src = src.replace(/\$\$([\s\S]+?)\$\$/g, (_m, body) => {
    blockMaths.push(body);
    return `\x00BMATH${blockMaths.length - 1}\x00`;
  });

  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  let inCode = false;
  let codeLang = "";
  let codeBuf: string[] = [];
  let listType: "ul" | "ol" | null = null;

  function closeList() {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  }

  // 表格检测：连续 3+ 行 | a | b | + | --- | --- |
  function tryConsumeTable(i: number): { html: string; consumed: number } | null {
    const head = lines[i];
    const sep = lines[i + 1];
    if (!head || !sep) return null;
    if (!/^\s*\|.+\|\s*$/.test(head)) return null;
    if (!/^\s*\|?\s*:?-{3,}.*\|/.test(sep)) return null;
    const parseRow = (l: string) =>
      l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    const headers = parseRow(head);
    const rows: string[][] = [];
    let j = i + 2;
    while (j < lines.length && /^\s*\|.+\|\s*$/.test(lines[j])) {
      rows.push(parseRow(lines[j]));
      j++;
    }
    const html = [
      '<table class="md-table">',
      "<thead><tr>" + headers.map((h) => `<th>${inlineMd(h)}</th>`).join("") + "</tr></thead>",
      "<tbody>",
      ...rows.map(
        (r) => "<tr>" + r.map((c) => `<td>${inlineMd(c)}</td>`).join("") + "</tr>"
      ),
      "</tbody></table>",
    ].join("");
    return { html, consumed: j - i };
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 代码块
    const fence = /^```(\w*)/.exec(line);
    if (fence) {
      if (inCode) {
        out.push(
          `<pre class="md-pre"><code class="lang-${codeLang}">${escHtml(codeBuf.join("\n"))}</code></pre>`
        );
        codeBuf = [];
        codeLang = "";
        inCode = false;
      } else {
        closeList();
        codeLang = fence[1] || "";
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(line);
      continue;
    }

    // 标题
    const h = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (h) {
      closeList();
      out.push(`<h${h[1].length}>${inlineMd(h[2])}</h${h[1].length}>`);
      continue;
    }

    // 表格
    if (/^\s*\|.+\|\s*$/.test(line)) {
      const tbl = tryConsumeTable(i);
      if (tbl) {
        closeList();
        out.push(tbl.html);
        i += tbl.consumed - 1;
        continue;
      }
    }

    // 引用
    if (/^>\s?/.test(line)) {
      closeList();
      out.push(`<blockquote>${inlineMd(line.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }

    // 无序列表
    const ul = /^\s*[-*+]\s+(.+)$/.exec(line);
    if (ul) {
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${inlineMd(ul[1])}</li>`);
      continue;
    }
    // 有序列表
    const ol = /^\s*\d+\.\s+(.+)$/.exec(line);
    if (ol) {
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${inlineMd(ol[1])}</li>`);
      continue;
    }

    closeList();

    // 水平线
    if (/^\s*([-*_])\s*\1\s*\1[\s\S]*$/.test(line) && line.replace(/\s/g, "").length >= 3) {
      out.push("<hr/>");
      continue;
    }

    // 块公式占位还原
    const blockMath = /^\x00BMATH(\d+)\x00$/.exec(line.trim());
    if (blockMath) {
      const body = blockMaths[Number(blockMath[1])];
      out.push(`<div class="md-block-math" title="块公式（实际数学渲染待 KaTeX 接入）">$$${escHtml(body)}$$</div>`);
      continue;
    }

    if (line.trim() === "") {
      out.push("");
      continue;
    }
    out.push(`<p>${inlineMd(line)}</p>`);
  }
  closeList();
  if (inCode) {
    out.push(
      `<pre class="md-pre"><code class="lang-${codeLang}">${escHtml(codeBuf.join("\n"))}</code></pre>`
    );
  }
  return out.join("\n");
}

// 行内 markdown：[text](url) 链接、![alt](url) 图片、`code`、**bold** / *italic* / $math$
function inlineMd(s: string): string {
  // 顺序：先 escape，再图片、链接、行内公式、code、bold、italic
  // 但 escape 会处理掉 url 里的字符，所以分段处理
  // 简单做法：用占位符把图片/链接/代码/公式提取出来 → escape → 还原
  const slots: string[] = [];
  function slot(html: string) {
    slots.push(html);
    return `\x00SLOT${slots.length - 1}\x00`;
  }
  // 图片 ![alt](url "title")
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (_m, alt, url, title) =>
    slot(`<img src="${escAttr(url)}" alt="${escAttr(alt)}" ${title ? `title="${escAttr(title)}"` : ""}/>`)
  );
  // 链接 [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (_m, text, url, title) =>
    slot(
      `<a href="${escAttr(url)}" target="_blank" rel="noopener" ${title ? `title="${escAttr(title)}"` : ""}>${escHtml(text)}</a>`
    )
  );
  // 行内代码 `code`
  s = s.replace(/`([^`]+)`/g, (_m, code) => slot(`<code>${escHtml(code)}</code>`));
  // 行内公式 $...$（不能是 $$ 之间，已被块公式提前提取）
  s = s.replace(/\$([^$\n]+)\$/g, (_m, body) =>
    slot(`<span class="md-inline-math" title="行内公式">$${escHtml(body)}$</span>`)
  );

  // 剩余文本 escape
  s = escHtml(s);
  // 加粗 + 斜体（在 escape 后做）
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<![*])\*([^*\n]+)\*(?![*])/g, "<em>$1</em>");
  s = s.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");

  // 还原占位
  s = s.replace(/\x00SLOT(\d+)\x00/g, (_m, idx) => slots[Number(idx)]);
  return s;
}

function escAttr(s: string): string {
  return s.replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
