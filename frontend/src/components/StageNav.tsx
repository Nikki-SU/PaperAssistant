import type { Project } from "../api/client";

export const STAGES: { key: string; label: string }[] = [
  { key: "topic", label: "1. 选题" },
  { key: "review", label: "2. 文献综述" },
  { key: "writing", label: "3. 正文撰写" },
  { key: "citation", label: "4. 引用" },
  { key: "typesetting", label: "5. 排版" },
];

export function StageNav({
  project,
  onSwitch,
}: {
  project: Project;
  onSwitch: (stage: string) => void;
}) {
  return (
    <div className="stage-nav">
      {STAGES.map((s) => (
        <button
          key={s.key}
          className={project.stage === s.key ? "active" : ""}
          onClick={() => onSwitch(s.key)}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
