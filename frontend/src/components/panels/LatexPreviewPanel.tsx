/**
 * LaTeX 预览（SPEC §六 / §7.5）。
 *
 * F4 阶段真实化：
 *  · 左编辑 Markdown（父级 mdContent） → 实时转 LaTeX 显示在 <pre> 中
 *  · "导出 manuscript" 按钮：调 typesetting/export 把 paper/*.md 合并为 manuscript.md
 *  · 显示当前合并产物路径 / 章节列表 / 提示 Tectonic 编译留待 H 阶段
 *  · 支持下载 LaTeX 源代码到本地（Blob）
 *  · 支持 复制 LaTeX 到剪贴板
 */
import { useState } from "react";
import { api } from "../../api/client";
import type { Project } from "../../api/client";

export function LatexPreviewPanel({
  mdSource,
  project,
  notify,
}: {
  mdSource: string;
  project: Project | null;
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [exporting, setExporting] = useState(false);
  const [lastExport, setLastExport] = useState<{
    project: string;
    manuscript_path: string;
    chapters: string[];
    at: string;
  } | null>(null);

  const latex = mdToLatexMini(mdSource);

  async function doExport() {
    if (!project) {
      notify("请先选择项目", "warn");
      return;
    }
    setExporting(true);
    try {
      const r = await api.exportManuscript(project.name);
      setLastExport({
        project: r.project,
        manuscript_path: r.manuscript_path,
        chapters: r.chapters,
        at: new Date().toLocaleTimeString(),
      });
      notify(`已合并 ${r.chapters.length} 个章节 → ${r.manuscript_path}`, "ok");
    } catch (e) {
      notify(`导出失败: ${String(e)}`, "error");
    } finally {
      setExporting(false);
    }
  }

  async function copyLatex() {
    try {
      await navigator.clipboard.writeText(latex);
      notify("LaTeX 源已复制到剪贴板", "ok");
    } catch (e) {
      notify(`复制失败: ${String(e)}`, "error");
    }
  }

  function downloadLatex() {
    const blob = new Blob([latex], { type: "text/x-tex;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (project?.name || "manuscript") + ".tex";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="latex-preview">
      <div className="latex-toolbar">
        <button
          className="primary-btn"
          onClick={() => void doExport()}
          disabled={!project || exporting}
          title="把 paper/*.md 合并成 manuscript.md（H 阶段会接入 Tectonic 编译 PDF）"
        >
          {exporting ? "合并中…" : "导出 manuscript.md"}
        </button>
        <button className="secondary-btn" onClick={() => void copyLatex()}>
          复制 LaTeX
        </button>
        <button className="secondary-btn" onClick={downloadLatex}>
          下载 .tex
        </button>
        <span className="muted-small">
          项目：<code>{project?.name ?? "未选"}</code>
        </span>
      </div>

      <div className="muted-block">
        <strong>提示：</strong>
        <span className="muted">
          {" "}
          这里实时把 Markdown 粗转为 LaTeX 文本，方便预览结构。最终编译为 PDF 走 H 阶段
          Tectonic（PyInstaller 打包时一并嵌入）。
        </span>
      </div>

      {lastExport && (
        <div className="muted-block latex-export-info">
          <strong>最近一次合并 ({lastExport.at}):</strong>
          <div>
            <code>{lastExport.manuscript_path}</code>
          </div>
          <div className="muted-small">
            章节（{lastExport.chapters.length}）：
            {lastExport.chapters.map((c) => (
              <code key={c} style={{ marginRight: 6 }}>
                {c}
              </code>
            ))}
          </div>
        </div>
      )}

      <pre className="latex-source">
        <code>{latex}</code>
      </pre>
    </div>
  );
}

function mdToLatexMini(src: string): string {
  const lines = src.split(/\r?\n/);
  const out: string[] = [
    "\\documentclass{article}",
    "\\usepackage[UTF8]{ctex}",
    "\\usepackage{amsmath}",
    "\\usepackage{amssymb}",
    "\\usepackage{graphicx}",
    "\\usepackage{hyperref}",
    "\\begin{document}",
    "",
  ];
  let inList: "itemize" | "enumerate" | null = null;
  let inCode = false;
  const codeBuf: string[] = [];

  // 简单文本 escape（避免破坏 $/数学符号）
  const escTex = (s: string) =>
    s
      .replace(/\\/g, "\\textbackslash{}")
      .replace(/([{}_%&#])/g, "\\$1")
      .replace(/\^/g, "\\^{}");

  function closeList() {
    if (inList) {
      out.push(`\\end{${inList}}`);
      inList = null;
    }
  }

  for (const raw of lines) {
    const line = raw;

    // 代码块
    if (/^```/.test(line)) {
      if (inCode) {
        out.push("\\begin{verbatim}");
        out.push(...codeBuf);
        out.push("\\end{verbatim}");
        codeBuf.length = 0;
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(line);
      continue;
    }

    // 标题
    const h = /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      closeList();
      const map = ["section", "subsection", "subsubsection", "paragraph", "subparagraph", "subparagraph"];
      const cmd = map[Math.min(h[1].length - 1, map.length - 1)];
      out.push(`\\${cmd}{${escTex(h[2])}}`);
      continue;
    }

    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      if (inList !== "itemize") {
        closeList();
        out.push("\\begin{itemize}");
        inList = "itemize";
      }
      out.push(`  \\item ${escTex(line.replace(/^\s*[-*+]\s+/, ""))}`);
      continue;
    }
    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      if (inList !== "enumerate") {
        closeList();
        out.push("\\begin{enumerate}");
        inList = "enumerate";
      }
      out.push(`  \\item ${escTex(line.replace(/^\s*\d+\.\s+/, ""))}`);
      continue;
    }

    // 引用
    if (/^>\s?/.test(line)) {
      closeList();
      out.push(`\\begin{quote}${escTex(line.replace(/^>\s?/, ""))}\\end{quote}`);
      continue;
    }

    closeList();
    if (line.trim() === "") {
      out.push("");
      continue;
    }

    // 行内：图片 / 链接 / $..$ 保留，**bold** / *italic*
    let p = line;
    p = p.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, (_m, _alt, url) => `\\includegraphics[width=0.8\\linewidth]{${url}}`);
    p = p.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_m, text, url) => `\\href{${url}}{${text}}`);
    // $..$ 保留不转 escape
    const mathSlots: string[] = [];
    p = p.replace(/\$([^$\n]+)\$/g, (_m, body) => {
      mathSlots.push(body);
      return `\x00M${mathSlots.length - 1}\x00`;
    });
    p = escTex(p);
    p = p.replace(/\x00M(\d+)\x00/g, (_m, idx) => `$${mathSlots[Number(idx)]}$`);
    p = p.replace(/\*\*([^*\n]+)\*\*/g, "\\textbf{$1}");
    p = p.replace(/\*([^*\n]+)\*/g, "\\emph{$1}");
    out.push(p);
  }
  closeList();
  if (inCode) {
    out.push("\\begin{verbatim}");
    out.push(...codeBuf);
    out.push("\\end{verbatim}");
  }
  out.push("");
  out.push("\\end{document}");
  return out.join("\n");
}
