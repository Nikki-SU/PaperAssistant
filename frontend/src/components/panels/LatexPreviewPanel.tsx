/**
 * LaTeX 预览（SPEC §六 / §7.5）。
 *
 * F4 阶段真实化 + H 阶段接通：
 *  · 左编辑 Markdown（父级 mdContent） → 实时转 LaTeX 显示在 <pre> 中（本地极简版）
 *  · 「导出 manuscript.md」：合并 paper/*.md → manuscript.md（POST /api/typesetting/{p}/export）
 *  · 「渲染 .tex（服务器）」：基于 paper/template.tex 渲染变量 → manuscript.tex（POST /render_tex）
 *  · 「一键编译 PDF」：自动 export → render_tex → compile_pdf；Tectonic 缺失时显示降级 reason/hint
 *  · 客户端「复制 LaTeX / 下载 .tex」保留作为本地极简兜底（无需服务器）
 */
import { useState } from "react";
import { api } from "../../api/client";
import type { Project } from "../../api/client";

type ExportInfo = {
  project: string;
  manuscript_path: string;
  chapters: string[];
  at: string;
};

type TexInfo = {
  project: string;
  tex_path: string;
  bytes: number;
  had_title_var: boolean;
  had_body_var: boolean;
  at: string;
};

type PdfInfo = {
  project: string;
  compiled: boolean;
  pdf_path?: string;
  bytes?: number;
  tectonic_bin?: string;
  reason?: "tectonic_not_found" | "tectonic_failed" | "timeout";
  hint?: string;
  returncode?: number;
  stderr_tail?: string;
  stdout_tail?: string;
  at: string;
};

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
  const [renderingTex, setRenderingTex] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [lastExport, setLastExport] = useState<ExportInfo | null>(null);
  const [lastTex, setLastTex] = useState<TexInfo | null>(null);
  const [lastPdf, setLastPdf] = useState<PdfInfo | null>(null);

  const latex = mdToLatexMini(mdSource);

  function nowTime() {
    return new Date().toLocaleTimeString();
  }

  async function doExport(): Promise<boolean> {
    if (!project) {
      notify("请先选择项目", "warn");
      return false;
    }
    setExporting(true);
    try {
      const r = await api.exportManuscript(project.name);
      setLastExport({
        project: r.project,
        manuscript_path: r.manuscript_path,
        chapters: r.chapters,
        at: nowTime(),
      });
      notify(`已合并 ${r.chapters.length} 个章节 → ${r.manuscript_path}`, "ok");
      return true;
    } catch (e) {
      notify(`导出失败: ${String(e)}`, "error");
      return false;
    } finally {
      setExporting(false);
    }
  }

  async function doRenderTex(): Promise<boolean> {
    if (!project) {
      notify("请先选择项目", "warn");
      return false;
    }
    setRenderingTex(true);
    try {
      const r = await api.renderTex(project.name);
      setLastTex({ ...r, at: nowTime() });
      const tip = r.had_title_var && r.had_body_var
        ? "模板变量 {{title}}/{{body}} 已替换"
        : "模板缺少部分变量，已用兜底注入";
      notify(`已渲染 manuscript.tex（${r.bytes} bytes）· ${tip}`, "ok");
      return true;
    } catch (e) {
      notify(`渲染 .tex 失败: ${String(e)}`, "error");
      return false;
    } finally {
      setRenderingTex(false);
    }
  }

  async function doCompilePdf(): Promise<boolean> {
    if (!project) {
      notify("请先选择项目", "warn");
      return false;
    }
    setCompiling(true);
    try {
      const r = await api.compilePdf(project.name);
      setLastPdf({ ...r, at: nowTime() });
      if (r.compiled) {
        notify(`PDF 已编译 → ${r.pdf_path}（${r.bytes} bytes）`, "ok");
        return true;
      }
      // 降级提示
      if (r.reason === "tectonic_not_found") {
        notify("Tectonic 未找到，已降级（详见下方提示）", "warn");
      } else if (r.reason === "timeout") {
        notify("Tectonic 编译超时（180s），已中止", "warn");
      } else if (r.reason === "tectonic_failed") {
        notify(`Tectonic 编译失败（returncode=${r.returncode}）`, "error");
      } else {
        notify(`PDF 编译未完成：${r.reason ?? "unknown"}`, "warn");
      }
      return false;
    } catch (e) {
      notify(`编译 PDF 失败: ${String(e)}`, "error");
      return false;
    } finally {
      setCompiling(false);
    }
  }

  async function doCompileAll() {
    // 一键全流程：export → render_tex → compile_pdf；任一失败立即停
    const okExport = await doExport();
    if (!okExport) return;
    const okTex = await doRenderTex();
    if (!okTex) return;
    await doCompilePdf();
  }

  async function copyLatex() {
    try {
      await navigator.clipboard.writeText(latex);
      notify("LaTeX 源（本地极简版）已复制到剪贴板", "ok");
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

  const busy = exporting || renderingTex || compiling;

  return (
    <div className="latex-preview">
      <div className="latex-toolbar">
        <button
          className="primary-btn"
          onClick={() => void doCompileAll()}
          disabled={!project || busy}
          title="自动串行：导出 manuscript.md → 渲染 manuscript.tex → 调 Tectonic 编译 PDF"
        >
          {busy ? "处理中…" : "一键编译 PDF"}
        </button>
        <button
          className="secondary-btn"
          onClick={() => void doExport()}
          disabled={!project || busy}
          title="POST /api/typesetting/{project}/export：合并 paper/*.md 为 manuscript.md"
        >
          {exporting ? "合并中…" : "导出 manuscript.md"}
        </button>
        <button
          className="secondary-btn"
          onClick={() => void doRenderTex()}
          disabled={!project || busy}
          title="POST /api/typesetting/{project}/render_tex：基于 paper/template.tex 渲染变量"
        >
          {renderingTex ? "渲染中…" : "渲染 .tex（服务器）"}
        </button>
        <button
          className="secondary-btn"
          onClick={() => void doCompilePdf()}
          disabled={!project || busy}
          title="POST /api/typesetting/{project}/compile_pdf：仅编译已存在的 manuscript.tex"
        >
          {compiling ? "编译中…" : "仅编译 PDF"}
        </button>
        <span className="latex-toolbar-divider" />
        <button className="secondary-btn" onClick={() => void copyLatex()} disabled={busy}>
          复制 LaTeX（本地）
        </button>
        <button className="secondary-btn" onClick={downloadLatex} disabled={busy}>
          下载 .tex（本地）
        </button>
        <span className="muted-small">
          项目：<code>{project?.name ?? "未选"}</code>
        </span>
      </div>

      <div className="muted-block">
        <strong>提示：</strong>
        <span className="muted">
          {" "}
          下方 <code>&lt;pre&gt;</code> 是「客户端极简版」LaTeX，仅供结构预览。真正提交编译走「一键编译 PDF」：服务器读
          <code> paper/template.tex </code> + <code>manuscript.md</code> 渲染后调 Tectonic 出 PDF。
        </span>
      </div>

      {lastExport && (
        <div className="muted-block latex-export-info">
          <strong>① 最近一次合并 ({lastExport.at}):</strong>
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

      {lastTex && (
        <div className="muted-block latex-export-info">
          <strong>② 最近一次渲染 .tex ({lastTex.at}):</strong>
          <div>
            <code>{lastTex.tex_path}</code>
          </div>
          <div className="muted-small">
            字节：{lastTex.bytes} · 模板变量：
            <code style={{ marginLeft: 4 }}>{`{{title}}`}</code>={String(lastTex.had_title_var)} ·
            <code style={{ marginLeft: 4 }}>{`{{body}}`}</code>={String(lastTex.had_body_var)}
          </div>
        </div>
      )}

      {lastPdf && (
        <div
          className="muted-block latex-export-info"
          style={{
            borderLeft: lastPdf.compiled
              ? "3px solid #2e9e63"
              : lastPdf.reason === "tectonic_not_found" || lastPdf.reason === "timeout"
              ? "3px solid #d49a2f"
              : "3px solid #c34646",
          }}
        >
          <strong>
            ③ 最近一次编译 PDF ({lastPdf.at}):{" "}
            {lastPdf.compiled ? "✅ 成功" : `⚠️ ${lastPdf.reason ?? "失败"}`}
          </strong>
          {lastPdf.compiled ? (
            <>
              <div>
                <code>{lastPdf.pdf_path}</code>
              </div>
              <div className="muted-small">
                字节：{lastPdf.bytes}
                {lastPdf.tectonic_bin && (
                  <>
                    {" · Tectonic: "}
                    <code>{lastPdf.tectonic_bin}</code>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              {lastPdf.hint && (
                <div className="muted-small" style={{ marginTop: 4 }}>
                  {lastPdf.hint}
                </div>
              )}
              {typeof lastPdf.returncode === "number" && (
                <div className="muted-small">returncode: {lastPdf.returncode}</div>
              )}
              {lastPdf.stderr_tail && (
                <details style={{ marginTop: 4 }}>
                  <summary className="muted-small">stderr (末尾)</summary>
                  <pre className="latex-source" style={{ maxHeight: 160 }}>
                    <code>{lastPdf.stderr_tail}</code>
                  </pre>
                </details>
              )}
              {lastPdf.stdout_tail && (
                <details>
                  <summary className="muted-small">stdout (末尾)</summary>
                  <pre className="latex-source" style={{ maxHeight: 120 }}>
                    <code>{lastPdf.stdout_tail}</code>
                  </pre>
                </details>
              )}
            </>
          )}
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
