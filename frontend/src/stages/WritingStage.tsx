import type { Project } from "../api/client";

const SCIENCE_SECTIONS = [
  "实验设计与方法",
  "表征结果",
  "机理与讨论",
  "结论与应用",
];

const SOCIAL_SECTIONS = [
  "理论框架",
  "研究设计",
  "数据与分析",
  "结论与政策建议",
];

export function WritingStage({ project }: { project: Project }) {
  const sections = project.perspective === "social" ? SOCIAL_SECTIONS : SCIENCE_SECTIONS;
  return (
    <>
      <div className="section">
        <h2>✍️ 正文撰写</h2>
        <p className="muted">
          视角：<strong>{project.perspective || "未定（默认按理科）"}</strong>。
          下面四节按视角自动生成模板，AI 助手编辑能力会在后续版本接入。
        </p>
        <ol>
          {sections.map((s) => (
            <li key={s}>{s} <span className="muted">— 模板待生成（WIP）</span></li>
          ))}
        </ol>
      </div>
      <div className="section">
        <h2>规则提醒</h2>
        <ul className="muted">
          <li>声称「来自某文献」的所有句子，必须能在「文献综述」上传的卡片或全文 Markdown 中找到原文。</li>
          <li>推断性陈述请前置「建议」二字；缺信息时，先去补卡片。</li>
          <li>事实核查最多循环 5 次；后续版本会自动触发。</li>
        </ul>
      </div>
    </>
  );
}
