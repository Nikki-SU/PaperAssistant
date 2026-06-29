/**
 * StageGuidePanel —— 阶段引导面板（SPEC §六）
 *
 * 展示当前阶段的：
 * - 标题 / 默认面板提示
 * - 8 步工作流（actor、audit 标签）
 * - intro_md 简介
 * - 阶段切换按钮（topic / review / writing / citation / typesetting）
 *
 * 父组件传入：
 * - projectName: string（当前项目名）
 * - currentStage: string（来自 Project.stage）
 * - onStageChange(stage)：父组件调 api.updateProject 后，把 stage_info.default_*_pane 透传回 App
 */
import { useEffect, useState } from "react";
import { api, StageInfo } from "../../api/client";

interface Props {
  projectName: string;
  currentStage: string;
  onStageChange: (stage: string) => void | Promise<void>;
}

export default function StageGuidePanel({ projectName, currentStage, onStageChange }: Props) {
  const [info, setInfo] = useState<StageInfo | null>(null);
  const [all, setAll] = useState<StageInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    if (!projectName) {
      setInfo(null);
      setAll([]);
      return;
    }
    setLoading(true);
    setErr("");
    api
      .getStageInfo(projectName)
      .then((r) => {
        setInfo(r.current);
        setAll(r.all_stages || []);
      })
      .catch((e) => setErr(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [projectName, currentStage]);

  if (!projectName) {
    return (
      <div className="stage-guide stage-guide--empty">
        请先选择/创建项目，阶段引导将随项目阶段自动加载。
      </div>
    );
  }
  if (loading) return <div className="stage-guide stage-guide--loading">加载阶段引导…</div>;
  if (err) return <div className="stage-guide stage-guide--err">阶段引导加载失败：{err}</div>;
  if (!info) return <div className="stage-guide stage-guide--empty">暂无阶段信息</div>;

  return (
    <div className="stage-guide">
      <div className="stage-guide__header">
        <div className="stage-guide__title">
          <span className="stage-guide__chip">阶段</span>
          <h3>{info.label}</h3>
          <span className="stage-guide__code">{info.stage}</span>
        </div>
        <div className="stage-guide__panes">
          <span>默认左栏：<code>{info.default_left_pane}</code></span>
          <span>默认右栏：<code>{info.default_right_pane}</code></span>
        </div>
      </div>

      <div className="stage-guide__tabs">
        {all.map((s) => (
          <button
            key={s.stage}
            type="button"
            className={
              "stage-guide__tab" + (s.stage === info.stage ? " stage-guide__tab--active" : "")
            }
            onClick={() => {
              if (s.stage !== info.stage) onStageChange(s.stage);
            }}
            disabled={loading}
          >
            {s.label}
          </button>
        ))}
      </div>

      <pre className="stage-guide__intro">{info.intro_md}</pre>

      <table className="stage-guide__steps">
        <thead>
          <tr>
            <th>#</th>
            <th>步骤</th>
            <th>谁来做</th>
            <th>审阅</th>
          </tr>
        </thead>
        <tbody>
          {info.steps.map((step) => (
            <tr key={step.id}>
              <td>{step.id}</td>
              <td>{step.title}</td>
              <td>
                <code>{step.actor}</code>
              </td>
              <td>
                {step.audit === "—" ? (
                  <span className="stage-guide__audit stage-guide__audit--none">—</span>
                ) : step.audit.includes("核查") ? (
                  <span className="stage-guide__audit stage-guide__audit--strict">{step.audit}</span>
                ) : (
                  <span className="stage-guide__audit stage-guide__audit--soft">{step.audit}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="stage-guide__hint">
        <strong>审阅提示：</strong>
        {info.audit_hint}
      </div>
    </div>
  );
}
