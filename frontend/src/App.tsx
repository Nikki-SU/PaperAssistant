import { useState } from "react";
import TopicStage from "./stages/TopicStage";
import LiteratureReviewStage from "./stages/LiteratureReviewStage";
import WritingStage from "./stages/WritingStage";
import CitationStage from "./stages/CitationStage";
import TypesettingStage from "./stages/TypesettingStage";

/**
 * PaperAssistant 主界面骨架。
 * 对应 SPEC：项目二 §六. UI/UX 布局
 */

type Stage = "topic" | "review" | "writing" | "citation" | "typesetting";

const STAGES: { key: Stage; label: string }[] = [
  { key: "topic", label: "● 选题" },
  { key: "review", label: "○ 文献综述" },
  { key: "writing", label: "○ 正文撰写" },
  { key: "citation", label: "○ 引用" },
  { key: "typesetting", label: "○ 排版" },
];

export default function App() {
  const [currentProject, setCurrentProject] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("topic");

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>📚 PaperAssistant</h1>
        <section>
          <h2>项目列表</h2>
          {/* TODO: 项目列表组件 */}
          <div className="placeholder">（暂无项目）</div>
        </section>
        <section>
          <h2>阶段导航</h2>
          <nav>
            {STAGES.map((s) => (
              <button
                key={s.key}
                onClick={() => setStage(s.key)}
                className={stage === s.key ? "active" : ""}
              >
                {s.label}
              </button>
            ))}
          </nav>
        </section>
      </aside>
      <main className="workspace">
        {stage === "topic" && <TopicStage project={currentProject} />}
        {stage === "review" && <LiteratureReviewStage project={currentProject} />}
        {stage === "writing" && <WritingStage project={currentProject} />}
        {stage === "citation" && <CitationStage project={currentProject} />}
        {stage === "typesetting" && <TypesettingStage project={currentProject} />}
      </main>
    </div>
  );
}
