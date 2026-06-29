/**
 * 阶段三 - 正文撰写
 * 对应 SPEC：项目二 §七
 */

interface Props {
  project: string | null;
}

export default function WritingStage({ project }: Props) {
  if (!project) {
    return <div className="empty-state">请先选择或创建一个项目</div>;
  }
  return (
    <div className="stage">
      <h2>阶段三 - 正文撰写</h2>
      {/* TODO: 双栏可切换工作区（AI对话 / 知识库检索 / Markdown 编辑器 / LaTeX 预览等） */}
      <div className="placeholder">TODO: 阶段三 - 正文撰写 工作区</div>
    </div>
  );
}
