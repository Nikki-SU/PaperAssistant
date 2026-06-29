import { useState } from "react";
import type { Project } from "../api/client";

interface Props {
  projects: Project[];
  activeName: string | null;
  loading: boolean;
  onSelect: (name: string) => void;
  onCreate: (input: { name: string; topic: string; perspective: string }) => Promise<void>;
  onRefresh: () => void;
}

const PERSPECTIVES = [
  { v: "", label: "未定" },
  { v: "science", label: "理科" },
  { v: "social", label: "社科" },
];

export function ProjectSidebar({
  projects,
  activeName,
  loading,
  onSelect,
  onCreate,
  onRefresh,
}: Props) {
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [persp, setPersp] = useState("");
  const [submitting, setSubmitting] = useState(false);

  return (
    <aside className="app-sidebar">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <strong>项目</strong>
        <div className="row" style={{ gap: 4 }}>
          <button className="ghost" style={{ padding: "2px 8px" }} onClick={onRefresh}>
            ↻
          </button>
          <button style={{ padding: "2px 8px" }} onClick={() => setShow(!show)}>
            + 新建
          </button>
        </div>
      </div>

      {show && (
        <div className="section" style={{ padding: 8, marginBottom: 12 }}>
          <input
            placeholder="项目名"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ marginBottom: 6 }}
          />
          <input
            placeholder="主题（选填）"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            style={{ marginBottom: 6 }}
          />
          <select
            value={persp}
            onChange={(e) => setPersp(e.target.value)}
            style={{ marginBottom: 6 }}
          >
            {PERSPECTIVES.map((p) => (
              <option key={p.v} value={p.v}>视角：{p.label}</option>
            ))}
          </select>
          <div className="row" style={{ gap: 6 }}>
            <button
              disabled={!name.trim() || submitting}
              onClick={async () => {
                setSubmitting(true);
                try {
                  await onCreate({ name: name.trim(), topic, perspective: persp });
                  setName(""); setTopic(""); setPersp("");
                  setShow(false);
                } finally {
                  setSubmitting(false);
                }
              }}
            >
              {submitting ? "..." : "创建"}
            </button>
            <button className="ghost" onClick={() => setShow(false)}>取消</button>
          </div>
        </div>
      )}

      {loading && <div className="muted">加载中...</div>}
      {!loading && projects.length === 0 && (
        <div className="muted">还没有项目。点「+ 新建」开始。</div>
      )}
      {projects.map((p) => (
        <div
          key={p.name}
          className={`project-item ${activeName === p.name ? "active" : ""}`}
          onClick={() => onSelect(p.name)}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {p.name}
          </span>
          <span className="stage-tag">{p.stage}</span>
        </div>
      ))}
    </aside>
  );
}
