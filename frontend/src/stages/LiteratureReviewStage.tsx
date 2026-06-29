import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LiteratureCard, Project } from "../api/client";
import type { ToastMsg } from "../components/Toast";

interface Props {
  project: Project;
  onToast: (m: ToastMsg) => void;
}

export function LiteratureReviewStage({ project, onToast }: Props) {
  const [cards, setCards] = useState<LiteratureCard[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.listLiterature(q);
      setCards(r.cards);
    } catch (e) {
      onToast({ text: `加载文献失败：${String(e)}`, kind: "error" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const r = await api.uploadPDF(file, { title: file.name.replace(/\.pdf$/i, "") });
        onToast({
          text: `已入库：${r.card.title}${r.mineru.success ? "" : "（MinerU 未配置）"}`,
          kind: r.mineru.success ? "ok" : "info",
        });
      }
      await refresh();
    } catch (e) {
      onToast({ text: `上传失败：${String(e)}`, kind: "error" });
    } finally {
      setUploading(false);
    }
  }

  async function addCitation(doi: string) {
    try {
      await api.addCitation(project.name, { doi });
      onToast({ text: `已加入本项目引用：${doi}`, kind: "ok" });
    } catch (e) {
      onToast({ text: `加入引用失败：${String(e)}`, kind: "error" });
    }
  }

  return (
    <>
      <div className="section">
        <h2>📚 文献综述 · 上传</h2>
        <p className="muted">
          拖入 PDF 或点击选择文件。后端会临时存放到 <code>temp/monitor</code>，调用 MinerU 解析为 Markdown，并入库到 <code>library/fulltext</code> 和 <code>library/cards/cards.csv</code>。
        </p>
        <label
          className={`upload-zone ${drag ? "drag" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            handleFiles(e.dataTransfer.files);
          }}
        >
          <div>{uploading ? "上传中..." : "拖入 PDF 或点击选择文件"}</div>
          <input
            type="file"
            accept="application/pdf,.pdf"
            multiple
            style={{ display: "none" }}
            onChange={(e) => handleFiles(e.target.files)}
          />
        </label>
      </div>

      <div className="section">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>📖 文献库</h2>
          <div className="row" style={{ gap: 6 }}>
            <input
              placeholder="按标题 / DOI / 作者 / 关键词搜索"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ maxWidth: 320 }}
              onKeyDown={(e) => e.key === "Enter" && refresh()}
            />
            <button onClick={refresh} disabled={loading}>{loading ? "..." : "刷新"}</button>
          </div>
        </div>

        {cards.length === 0 ? (
          <div className="muted" style={{ marginTop: 12 }}>
            文献库还是空的。上传几篇 PDF 试试，或直接在「正文撰写」前进行调研。
          </div>
        ) : (
          <table className="lit-table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>标题</th>
                <th style={{ width: 200 }}>DOI</th>
                <th style={{ width: 120 }}>期刊</th>
                <th style={{ width: 100 }}>状态</th>
                <th style={{ width: 80 }}></th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.doi}>
                  <td>
                    <div>{c.title || "(无标题)"}</div>
                    <div className="muted">{c.first_author}</div>
                  </td>
                  <td><code style={{ fontSize: 12 }}>{c.doi}</code></td>
                  <td>{c.journal || "-"}</td>
                  <td>{c.status}</td>
                  <td>
                    <button className="ghost" style={{ padding: "2px 8px" }} onClick={() => addCitation(c.doi)}>
                      引用
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
