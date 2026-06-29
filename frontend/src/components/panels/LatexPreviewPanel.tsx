/**
 * LaTeX 预览（SPEC §六 / §7.5）。
 *
 * 当前阶段：把 Markdown 源转为非常简化的 LaTeX 文本展示（标题/段落/列表）。
 * 真正的 Markdown → LaTeX 模板渲染 + 实时 KaTeX 留待 B 计划。
 */
export function LatexPreviewPanel({ mdSource }: { mdSource: string }) {
  const latex = mdToLatexMini(mdSource);
  return (
    <div className="latex-preview">
      <div className="muted-block">
        <strong>LaTeX 预览（占位）</strong>
        <p className="muted">
          真实模板渲染（CSL 引用替换、自定义 LaTeX 模板套用、KaTeX 实时数学公式）将在 B 计划接入。
          这里只是把 Markdown 粗略转成 LaTeX 文本展示，让你提前看到联动效果。
        </p>
      </div>
      <pre className="latex-source"><code>{latex}</code></pre>
    </div>
  );
}

function mdToLatexMini(src: string): string {
  const lines = src.split(/\r?\n/);
  const out: string[] = [
    "\\documentclass{article}",
    "\\usepackage[UTF8]{ctex}",
    "\\begin{document}",
    "",
  ];
  let inList = false;
  const escTex = (s: string) =>
    s.replace(/([\\{}_$&#%])/g, "\\$1");

  for (const raw of lines) {
    const line = raw;
    const h = /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      if (inList) { out.push("\\end{itemize}"); inList = false; }
      const map = ["section", "subsection", "subsubsection", "paragraph", "subparagraph"];
      const cmd = map[Math.min(h[1].length - 1, map.length - 1)];
      out.push(`\\${cmd}{${escTex(h[2])}}`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { out.push("\\begin{itemize}"); inList = true; }
      out.push(`  \\item ${escTex(line.replace(/^\s*[-*]\s+/, ""))}`);
      continue;
    }
    if (inList) { out.push("\\end{itemize}"); inList = false; }
    if (line.trim() === "") { out.push(""); continue; }
    out.push(escTex(line));
  }
  if (inList) out.push("\\end{itemize}");
  out.push("");
  out.push("\\end{document}");
  return out.join("\n");
}
