import { useEffect, useState, useCallback } from "react";
import { api } from "./api/client";
import type { Project } from "./api/client";
import { ProjectSidebar } from "./components/ProjectSidebar";
import { StageNav } from "./components/StageNav";
import { Toast } from "./components/Toast";
import type { ToastMsg } from "./components/Toast";
import { TopicStage } from "./stages/TopicStage";
import { LiteratureReviewStage } from "./stages/LiteratureReviewStage";
import { WritingStage } from "./stages/WritingStage";
import { CitationStage } from "./stages/CitationStage";
import { TypesettingStage } from "./stages/TypesettingStage";

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [health, setHealth] = useState<{ data_root?: string; status?: string }>({});

  const active = projects.find((p) => p.name === activeName) ?? null;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.listProjects();
      setProjects(r.projects);
      setActiveName((prev) => prev ?? r.projects[0]?.name ?? null);
    } catch (e) {
      setToast({ text: `加载项目失败：${String(e)}`, kind: "error" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void api.health().then((h) => setHealth(h)).catch(() => {
      setToast({
        text: "无法连接 PaperAssistant 后端（127.0.0.1:8181）。请先运行 dev-pa.ps1。",
        kind: "error",
      });
    });
    void refresh();
  }, [refresh]);

  async function createProject(input: { name: string; topic: string; perspective: string }) {
    try {
      const r = await api.createProject(input);
      setProjects((ps) => [r.project, ...ps]);
      setActiveName(r.project.name);
      setToast({ text: `已创建项目：${r.project.name}`, kind: "ok" });
    } catch (e) {
      setToast({ text: `创建失败：${String(e)}`, kind: "error" });
    }
  }

  async function switchStage(stage: string) {
    if (!active) return;
    try {
      const r = await api.updateProject(active.name, { stage });
      setProjects((ps) => ps.map((p) => (p.name === r.project.name ? r.project : p)));
    } catch (e) {
      setToast({ text: `切换阶段失败：${String(e)}`, kind: "error" });
    }
  }

  function onProjectChange(updated: Project) {
    setProjects((ps) => ps.map((p) => (p.name === updated.name ? updated : p)));
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🪐 PaperAssistant <span className="muted">· 本地优先学术写作</span></h1>
        <span className="muted">
          {health.status === "ok"
            ? `data: ${health.data_root ?? ""}`
            : "未连接后端"}
        </span>
      </header>

      <ProjectSidebar
        projects={projects}
        activeName={activeName}
        loading={loading}
        onSelect={setActiveName}
        onCreate={createProject}
        onRefresh={refresh}
      />

      <main className="app-main">
        {!active ? (
          <div className="section">
            <h2>欢迎</h2>
            <p>左侧点 <strong>+ 新建</strong> 创建第一个项目；项目按五个阶段推进：选题 → 文献综述 → 正文 → 引用 → 排版。</p>
            <p className="muted">
              当前后端：<code>{health.data_root ?? "(未连接)"}</code>
            </p>
          </div>
        ) : (
          <>
            <h2 style={{ margin: "0 0 12px" }}>{active.name}</h2>
            <StageNav project={active} onSwitch={switchStage} />
            {active.stage === "topic" && (
              <TopicStage project={active} onChange={onProjectChange} onToast={setToast} />
            )}
            {active.stage === "review" && (
              <LiteratureReviewStage project={active} onToast={setToast} />
            )}
            {active.stage === "writing" && <WritingStage project={active} />}
            {active.stage === "citation" && (
              <CitationStage project={active} onToast={setToast} />
            )}
            {active.stage === "typesetting" && (
              <TypesettingStage project={active} onToast={setToast} />
            )}
          </>
        )}
      </main>

      <Toast msg={toast} onClose={() => setToast(null)} />
    </div>
  );
}
