/**
 * Markdown 编辑器（SPEC §六：所见即所得）。
 *
 * 当前阶段：textarea + 实时 Markdown → HTML 简易渲染（同栏分屏）。
 * 真正所见即所得（如 Milkdown）留待 B 计划（需 npm install）。
 * 联动：内容写入父级 mdContent，右栏 LaTeX 面板可同步消费。
 *
 * 本地存储：保存按钮触发 PATCH 项目 draft.md（接口待补，目前仅本地状态）。
 */
import type { Project } from "../../api/client";

export function MarkdownEditorPanel(props: {
  project: Project | null;
  content: string;
  onChange: (s: string) => void;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const { project, content, onChange, notify } = props;
  return (
    <div className="md-editor">
      <div className="editor-toolbar">
        <span className="muted-small">
          编辑 <code>{project ? `projects/${project.name}/paper/draft.md` : "(未选项目)"}</code>
        </span>
        <button
          className="primary-btn"
          onClick={() => notify("保存接口待 B 计划接入；当前内容存在内存中", "warn")}
        >
          保存
        </button>
      </div>
      <div className="md-editor-grid">
        <textarea
          className="md-source"
          value={content}
          onChange={(e) => onChange(e.target.value)}
          placeholder="# 在这里写 Markdown...

支持的所见即所得高级特性（图片、嵌入公式 KaTeX、表格编辑器）将在 B 计划接入。"
        />
        <div className="md-preview">
          <SimpleMdPreview source={content} />
        </div>
      </div>
    </div>
  );
}

/** 极简 markdown → HTML（避免引入大依赖；只处理标题/列表/段落/code）。 */
function SimpleMdPreview({ source }: { source: string }) {
  const html = renderMdMini(source);
  return <div className="md-preview-content" dangerouslySetInnerHTML={{ __html: html }} />;
}

function renderMdMini(src: string): string {
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = src.split(/\r?\n/);
  const out: string[] = [];
  let inCode = false;
  let codeBuf: string[] = [];
  let inList = false;

  function closeList() { if (inList) { out.push("</ul>"); inList = false; } }

  for (const raw of lines) {
    const line = raw;
    if (/^```/.test(line)) {
      if (inCode) {
        out.push(`<pre><code>${esc(codeBuf.join("\n"))}</code></pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }
    const h = /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      closeList();
      const lvl = h[1].length;
      out.push(`<h${lvl}>${esc(h[2])}</h${lvl}>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${esc(line.replace(/^\s*[-*]\s+/, ""))}</li>`);
      continue;
    }
    closeList();
    if (line.trim() === "") { out.push(""); continue; }
    let p = esc(line);
    p = p.replace(/`([^`]+)`/g, "<code>$1</code>");
    p = p.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    p = p.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    out.push(`<p>${p}</p>`);
  }
  closeList();
  if (inCode) out.push(`<pre><code>${esc(codeBuf.join("\n"))}</code></pre>`);
  return out.join("\n");
}
