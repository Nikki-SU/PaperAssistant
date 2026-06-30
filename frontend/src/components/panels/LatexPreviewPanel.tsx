/**
 * LaTeX 预览（SPEC §六 / §7.5 / ζ 阶段）。
 *
 * 接通真实编译链 + 多引擎支持：
 *  · 顶部引擎下拉（auto / xelatex / pdflatex / lualatex / tectonic），不可用引擎自动置灰
 *  · 挂载时调 GET /api/typesetting/engines/detect 探测本机 LaTeX，全无时显示安装引导卡
 *  · 「一键编译 PDF」：自动 export → render_tex → compile_pdf(engine)，串行任一失败即停
 *  · 编译失败时把 .log 解析出的结构化错误（含行号）列出来，不只是 stderr 尾部
 *  · 客户端「复制/下载 .tex」保留作本地兜底
 *  · 引擎选择持久化到 localStorage（KEY: pa_latex_engine）
 */
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  Project,
  LatexEngineInfo,
  LatexErrorBlock,
} from "../../api/client";

const ENGINE_STORAGE_KEY = "pa_latex_engine";

const ENGINE_LABEL: Record<string, string> = {
  auto: "自动（推荐）",
  xelatex: "xelatex",
  pdflatex: "pdflatex",
  lualatex: "lualatex",
  tectonic: "tectonic",
};

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
  engine_used?: string;
  engine_bin?: string;
  used_latexmk?: boolean;
  run_count?: number;
  reason?: "no_engine" | "engine_not_found" | "compile_failed" | "timeout";
  engine_requested?: string;
  hint?: string;
  returncode?: number;
  errors?: LatexErrorBlock[];
  warnings?: LatexErrorBlock[];
  log_path?: string;
  stderr_tail?: string;
  stdout_tail?: string;
  at: string;
};

type EngineDetect = {
  engines: LatexEngineInfo[];
  has_any: boolean;
  auto_pick: string | null;
  latexmk_bin: string | null;
  install_hint: string | null;
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

  // 引擎下拉 + 探测
  const [engineSel, setEngineSel] = useState<string>(() => {
    try {
      return localStorage.getItem(ENGINE_STORAGE_KEY) || "auto";
    } catch {
      return "auto";
    }
  });
  const [detect, setDetect] = useState<EngineDetect | null>(null);
  const [detecting, setDetecting] = useState(false);

  const latex = mdToLatexMini(mdSource);

  function nowTime() {
    return new Date().toLocaleTimeString();
  }

  async function refreshDetect() {
    setDetecting(true);
    try {
      const r = await api.detectLatexEngines();
      setDetect(r);
    } catch (e) {
      notify(`检测 LaTeX 引擎失败: ${String(e)}`, "error");
    } finally {
      setDetecting(false);
    }
  }

  useEffect(() => {
    void refreshDetect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onPickEngine(v: string) {
    setEngineSel(v);
    try {
      localStorage.setItem(ENGINE_STORAGE_KEY, v);
    } catch {
      /* ignore */
    }
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
      const r = await api.compilePdf(project.name, engineSel);
      setLastPdf({ ...r, at: nowTime() });
      if (r.compiled) {
        notify(
          `PDF 已编译（${r.engine_used}${r.used_latexmk ? "+latexmk" : ""}）→ ${r.pdf_path}`,
          "ok",
        );
        return true;
      }
      // 降级提示
      if (r.reason === "no_engine") {
        notify("本机未装任何 LaTeX 引擎，详见下方安装引导", "warn");
      } else if (r.reason === "engine_not_found") {
        notify(`引擎 ${r.engine_requested ?? engineSel} 未找到`, "warn");
      } else if (r.reason === "timeout") {
        notify("LaTeX 编译超时（240s）", "warn");
      } else if (r.reason === "compile_failed") {
        notify(
          `编译失败（returncode=${r.returncode}）· 错误段：${(r.errors ?? []).length} 条`,
          "error",
        );
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
  const noEngine = detect !== null && !detect.has_any;

  return (
    <div className="latex-preview">
      <div className="latex-toolbar">
        <button
          className="primary-btn"
          onClick={() => void doCompileAll()}
          disabled={!project || busy || noEngine}
          title="自动串行：导出 manuscript.md → 渲染 manuscript.tex → 调引擎编译 PDF"
        >
          {busy ? "处理中…" : "一键编译 PDF"}
        </button>

        {/* 引擎下拉 */}
        <label className="latex-engine-pick">
          <span className="muted-small">引擎</span>
          <select
            className="latex-engine-select"
            value={engineSel}
            onChange={(e) => onPickEngine(e.target.value)}
            disabled={busy}
            title="选择 LaTeX 编译引擎；auto 按 xelatex→pdflatex→lualatex→tectonic 顺序自动挑"
          >
            {(["auto", "xelatex", "pdflatex", "lualatex", "tectonic"] as const).map((id) => {
              const info = id === "auto" ? null : detect?.engines.find((x) => x.id === id);
              const avail = id === "auto" ? !!detect?.has_any : !!info?.available;
              const label = ENGINE_LABEL[id] ?? id;
              const suffix = id === "auto"
                ? (detect?.auto_pick ? ` → ${detect.auto_pick}` : (detect ? " · 无可用" : ""))
                : (avail ? " ✓" : " ·未装");
              return (
                <option key={id} value={id} disabled={!avail}>
                  {label}{suffix}
                </option>
              );
            })}
          </select>
        </label>

        <button
          className="secondary-btn"
          onClick={() => void refreshDetect()}
          disabled={detecting}
          title="重新检测本机 LaTeX 引擎"
        >
          {detecting ? "检测中…" : "↻ 检测引擎"}
        </button>

        <span className="latex-toolbar-divider" />

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
          {renderingTex ? "渲染中…" : "渲染 .tex"}
        </button>
        <button
          className="secondary-btn"
          onClick={() => void doCompilePdf()}
          disabled={!project || busy || noEngine}
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

      {/* 无引擎时的安装引导卡 */}
      {noEngine && detect?.install_hint && (
        <div className="latex-install-card">
          <strong>⚠️ 本机未检测到任何 LaTeX 引擎</strong>
          <div className="muted-small" style={{ marginTop: 6, lineHeight: 1.7 }}>
            {detect.install_hint}
          </div>
          <div className="muted-small" style={{ marginTop: 8 }}>
            装完后点上方 <strong>「↻ 检测引擎」</strong> 即可。
          </div>
        </div>
      )}

      {/* 检测结果摘要（有可用引擎时） */}
      {detect && detect.has_any && (
        <div className="muted-block latex-engine-info">
          <strong>已检测到引擎：</strong>
          {detect.engines.filter((e) => e.available).map((e) => (
            <code key={e.id} style={{ marginLeft: 6 }}>
              {e.id}
              {e.version ? ` (${e.version.slice(0, 40)})` : ""}
            </code>
          ))}
          {detect.latexmk_bin && (
            <span className="muted-small" style={{ marginLeft: 8 }}>
              · latexmk ✓（自动多遍编译）
            </span>
          )}
        </div>
      )}

      <div className="muted-block">
        <strong>提示：</strong>
        <span className="muted">
          {" "}下方 <code>&lt;pre&gt;</code> 是「客户端极简版」LaTeX，仅供结构预览。真正提交编译走「一键编译 PDF」：
          服务器读 <code>paper/template.tex</code> + <code>manuscript.md</code> 渲染后调选定引擎出 PDF。
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
              : lastPdf.reason === "no_engine" || lastPdf.reason === "engine_not_found" || lastPdf.reason === "timeout"
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
                {lastPdf.engine_used && (
                  <>
                    {" · 引擎: "}
                    <code>{lastPdf.engine_used}</code>
                  </>
                )}
                {lastPdf.used_latexmk && (
                  <span style={{ marginLeft: 6 }}>+ latexmk</span>
                )}
                {typeof lastPdf.run_count === "number" && lastPdf.run_count > 1 && (
                  <span style={{ marginLeft: 6 }}>· 跑了 {lastPdf.run_count} 遍</span>
                )}
                {lastPdf.engine_bin && (
                  <div>
                    <code className="muted-small">{lastPdf.engine_bin}</code>
                  </div>
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

              {/* 结构化错误列表（最有用的部分） */}
              {lastPdf.errors && lastPdf.errors.length > 0 && (
                <div className="latex-errors">
                  <div className="muted-small" style={{ marginBottom: 4 }}>
                    <strong>.log 错误段（{lastPdf.errors.length} 条）</strong>
                  </div>
                  {lastPdf.errors.map((err, idx) => (
                    <div key={idx} className="latex-error-item">
                      <div className="latex-error-head">
                        <span className="latex-error-msg">{err.message}</span>
                        {err.line !== null && (
                          <code className="latex-error-line">l.{err.line}</code>
                        )}
                      </div>
                      {err.context && (
                        <pre className="latex-error-ctx">
                          <code>{err.context}</code>
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
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

    const h = /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      closeList();
      const map = ["section", "subsection", "subsubsection", "paragraph", "subparagraph", "subparagraph"];
      const cmd = map[Math.min(h[1].length - 1, map.length - 1)];
      out.push(`\\${cmd}{${escTex(h[2])}}`);
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      if (inList !== "itemize") {
        closeList();
        out.push("\\begin{itemize}");
        inList = "itemize";
      }
      out.push(`  \\item ${escTex(line.replace(/^\s*[-*+]\s+/, ""))}`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (inList !== "enumerate") {
        closeList();
        out.push("\\begin{enumerate}");
        inList = "enumerate";
      }
      out.push(`  \\item ${escTex(line.replace(/^\s*\d+\.\s+/, ""))}`);
      continue;
    }

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

    let p = line;
    p = p.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, (_m, _alt, url) => `\\includegraphics[width=0.8\\linewidth]{${url}}`);
    p = p.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_m, text, url) => `\\href{${url}}{${text}}`);
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
