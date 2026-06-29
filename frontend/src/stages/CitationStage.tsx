import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CitationRow, Project } from "../api/client";
import type { ToastMsg } from "../components/Toast";

export function CitationStage({
  project,
  onToast,
}: {
  project: Project;
  onToast: (m: ToastMsg) => void;
}) {
  const [rows, setRows] = useState<CitationRow[]>([]);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.listCitations(project.name);
      setRows(r.citations);
    } catch (e) {
      onToast({ text: `加载引用失败：${String(e)}`, kind: "error" });
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.name]);

  return (
    <div className="section">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>🔗 引用</h2>
        <button className="ghost" onClick={refresh} disabled={loading}>
          {loading ? "..." : "刷新"}
        </button>
      </div>
      {rows.length === 0 ? (
        <div className="muted" style={{ marginTop: 12 }}>
          本项目还没引用条目。去「文献综述」选中文献点「引用」加入。
        </div>
      ) : (
        <table className="lit-table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>DOI</th>
              <th>Label</th>
              <th>Used In</th>
              <th>添加时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.doi}>
                <td><code style={{ fontSize: 12 }}>{r.doi}</code></td>
                <td>{r.label}</td>
                <td>{r.used_in || "-"}</td>
                <td>{r.added_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
