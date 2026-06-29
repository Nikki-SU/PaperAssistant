/**
 * 左栏（SPEC §六）。
 *
 * - 可折叠：折叠时只剩一根带"展开"按钮的窄条
 * - 上半：项目列表（可创建/选中/重命名/删除）
 * - 下半：阶段导航（选中项目时显示当前阶段）
 *
 * 严格按 SPEC：项目列表 + 五阶段导航 共一栏，左侧可折叠。
 */
import { useState } from "react";
import type { Project } from "../api/client";

export const STAGES: { value: string; label: string }[] = [
  { value: "topic",         label: "选题" },
  { value: "review",        label: "文献综述" },
  { value: "writing",       label: "正文撰写" },
  { value: "citation",      label: "引用" },
  { value: "typesetting",   label: "排版" },
];

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  projects: Project[];
  activeName: string | null;
  onSelect: (name: string) => void;
  onCreate: () => void;
  onRename: (oldName: string) => void;
  onDelete: (name: string) => void;
  onStageChange: (stage: string) => void;
  onOpenSettings: () => void;
}

export function LeftRail(props: Props) {
  const {
    collapsed, onToggle, projects, activeName,
    onSelect, onCreate, onRename, onDelete, onStageChange,
    onOpenSettings,
  } = props;

  const active = projects.find((p) => p.name === activeName) ?? null;

  if (collapsed) {
    return (
      <aside className="left-rail left-rail-collapsed">
        <button className="left-rail-toggle" onClick={onToggle} title="展开左栏">
          ⏵
        </button>
        <div className="collapsed-divider" />
        <div className="collapsed-dots">
          {projects.slice(0, 8).map((p) => (
            <button
              key={p.name}
              className={"collapsed-dot" + (p.name === activeName ? " active" : "")}
              title={p.name}
              onClick={() => onSelect(p.name)}
            >
              {(p.name || "?").slice(0, 1)}
            </button>
          ))}
        </div>
      </aside>
    );
  }

  return (
    <aside className="left-rail">
      <div className="left-rail-head">
        <span className="brand">🪐 PaperAssistant</span>
        <button className="left-rail-toggle" onClick={onToggle} title="折叠左栏">
          ⏴
        </button>
      </div>

      <section className="left-section">
        <div className="left-section-title">
          <span>项目列表</span>
          <button className="ghost-btn" onClick={onCreate} title="新建项目">
            ＋
          </button>
        </div>
        <div className="project-list">
          {projects.length === 0 && (
            <div className="empty-hint">还没有项目，点 ＋ 新建</div>
          )}
          {projects.map((p) => (
            <ProjectRow
              key={p.name}
              project={p}
              active={p.name === activeName}
              onClick={() => onSelect(p.name)}
              onRename={() => onRename(p.name)}
              onDelete={() => onDelete(p.name)}
            />
          ))}
        </div>
      </section>

      <section className="left-section">
        <div className="left-section-title">
          <span>阶段</span>
          <span className="muted-small">
            {active ? active.name : "未选项目"}
          </span>
        </div>
        <div className="stage-list">
          {STAGES.map((s) => {
            const cur = active?.stage === s.value;
            return (
              <button
                key={s.value}
                disabled={!active}
                className={"stage-row" + (cur ? " current" : "")}
                onClick={() => active && onStageChange(s.value)}
              >
                <span className="stage-bullet">{cur ? "●" : "○"}</span>
                <span>{s.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      <div className="left-rail-foot">
        <button className="footer-btn" onClick={onOpenSettings}>
          ⚙ 设置
        </button>
      </div>
    </aside>
  );
}

function ProjectRow(props: {
  project: Project;
  active: boolean;
  onClick: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const { project, active, onClick, onRename, onDelete } = props;
  return (
    <div className={"project-row" + (active ? " active" : "")}>
      <button className="project-row-main" onClick={onClick}>
        <span className="project-name" title={project.name}>
          {project.is_placeholder_name ? (
            <em className="placeholder-name">{project.name}</em>
          ) : (
            project.name
          )}
        </span>
        <span className="project-meta">{project.stage}</span>
      </button>
      <button
        className="row-more"
        onClick={() => setMenu((v) => !v)}
        title="更多操作"
      >
        ⋯
      </button>
      {menu && (
        <div className="row-menu" onMouseLeave={() => setMenu(false)}>
          <button onClick={() => { setMenu(false); onRename(); }}>重命名</button>
          <button onClick={() => { setMenu(false); onDelete(); }} className="danger">
            删除
          </button>
        </div>
      )}
    </div>
  );
}
