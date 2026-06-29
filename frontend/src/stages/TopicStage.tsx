import { useState } from "react";
import type { Project } from "../api/client";
import { api } from "../api/client";
import type { ToastMsg } from "../components/Toast";

interface Props {
  project: Project;
  onChange: (updated: Project) => void;
  onToast: (m: ToastMsg) => void;
}

const PERSPECTIVES = [
  { v: "", label: "未定" },
  { v: "science", label: "理科（实验→表征→机理→应用）" },
  { v: "social", label: "社科（理论→设计→数据→结论）" },
];

export function TopicStage({ project, onChange, onToast }: Props) {
  const [topic, setTopic] = useState(project.topic);
  const [persp, setPersp] = useState(project.perspective);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const r = await api.updateProject(project.name, { topic, perspective: persp });
      onChange(r.project);
      onToast({ text: "选题已保存", kind: "ok" });
    } catch (e) {
      onToast({ text: `保存失败：${String(e)}`, kind: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="section">
        <h2>📌 选题</h2>
        <p className="muted">
          描述你打算研究的主题；选择论文视角（理科 / 社科），后续阶段将按视角组织章节。
        </p>
        <textarea
          placeholder="例：钙钛矿太阳能电池在湿热环境下的稳定性提升机理"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <div style={{ marginTop: 8 }}>
          <select value={persp} onChange={(e) => setPersp(e.target.value)} style={{ maxWidth: 360 }}>
            {PERSPECTIVES.map((p) => (
              <option key={p.v} value={p.v}>视角：{p.label}</option>
            ))}
          </select>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={save} disabled={saving}>
            {saving ? "保存中..." : "保存选题"}
          </button>
        </div>
      </div>

      <div className="section">
        <h2>下一步</h2>
        <p className="muted">
          选定主题后切换到「文献综述」上传相关 PDF。本地优先：文件不会被上传到任何第三方。
        </p>
      </div>
    </>
  );
}
