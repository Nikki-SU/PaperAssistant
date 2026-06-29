import { useState } from "react";
import { api } from "../api/client";
import type { Project } from "../api/client";
import type { ToastMsg } from "../components/Toast";

export function TypesettingStage({
  project,
  onToast,
}: {
  project: Project;
  onToast: (m: ToastMsg) => void;
}) {
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<{ manuscript_path: string; chapters: string[] } | null>(null);

  async function doExport() {
    setExporting(true);
    try {
      const r = await api.exportManuscript(project.name);
      setResult(r);
      onToast({ text: `已合并 ${r.chapters.length} 章节为 manuscript.md`, kind: "ok" });
    } catch (e) {
      onToast({ text: `导出失败：${String(e)}`, kind: "error" });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="section">
      <h2>🖨 排版</h2>
      <p className="muted">
        本阶段会把 <code>paper/*.md</code> 合并为一份 <code>manuscript.md</code>，
        后续 Tectonic + CSL 编译 PDF 会在客户端本地完成（当前为 WIP）。
      </p>
      <button onClick={doExport} disabled={exporting}>
        {exporting ? "导出中..." : "导出 manuscript.md"}
      </button>
      {result && (
        <div style={{ marginTop: 12 }}>
          <div className="muted">manuscript：<code>{result.manuscript_path}</code></div>
          <div className="muted">章节：{result.chapters.join(", ")}</div>
        </div>
      )}
    </div>
  );
}
