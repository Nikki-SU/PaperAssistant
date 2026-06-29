/**
 * 主入口（SPEC §六）。
 *
 * 布局：
 *   ┌──────┬────────────────────────────────────────┐
 *   │ 左栏 │           主工作区（双栏可调宽度）       │
 *   │ 可折 │  ┌──────────────┬─────────────────────┐ │
 *   │ 叠   │  │ 左工作区     │ 右工作区             │ │
 *   │ 项目 │  │ （独立切换） │ （独立切换）         │ │
 *   │ +阶段│  │             │                     │ │
 *   └──────┴──┴──────────────┴─────────────────────┘
 *
 * 每个工作区可独立切换为：AI 对话 / 搜索网站 / 知识库检索 / Markdown 编辑器 /
 *                       LaTeX 预览 / 文献卡片列表 / 知识库卡片列表
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import type { Project, SettingsSnapshot } from "./api/client";
import { LeftRail } from "./components/LeftRail";
import { WorkPane } from "./components/WorkPane";
import type { PaneKind } from "./components/WorkPane";
import { Toast } from "./components/Toast";
import type { ToastMsg } from "./components/Toast";
import { SettingsDialog } from "./components/SettingsDialog";
import { FirstRunDialog } from "./components/FirstRunDialog";
import { CreateProjectDialog, RenameDialog } from "./components/ProjectDialogs";

export default function App() {
  // ---- 顶层状态 ----
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsSnapshot | null>(null);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  // ---- UI 状态 ----
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [leftKind, setLeftKind] = useState<PaneKind>("ai-chat");
  const [rightKind, setRightKind] = useState<PaneKind>("md-editor");
  const [splitPct, setSplitPct] = useState(50);

  // ---- 对话框 ----
  const [firstRun, setFirstRun] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);

  // ---- 编辑器联动状态 ----
  const [mdContent, setMdContent] = useState<string>(
    "# 我的论文草稿\n\n在这里写正文。左/右工作区可分别切换为 Markdown 编辑器 / LaTeX 预览来实时联动。\n"
  );

  const active = useMemo(
    () => projects.find((p) => p.name === activeName) ?? null,
    [projects, activeName]
  );

  const notify = useCallback(
    (text: string, kind: "ok" | "warn" | "error" = "ok") => {
      setToast({ text, kind: kind === "warn" ? "error" : kind });
    },
    []
  );

  // ---- 初始化：检查后端 + 加载设置 + 加载项目 ----
  useEffect(() => {
    void (async () => {
      try {
        await api.health();
        setBackendOk(true);
      } catch (e) {
        setBackendOk(false);
        notify("无法连接 PaperAssistant 后端（127.0.0.1:8181），请先运行 dev-pa.ps1", "error");
        return;
      }
      try {
        const s = await api.getSettings();
        setSettings(s);
        // 首次启动：默认目录且 4 个 key 全空 → 弹引导
        const noKeys = s.api_roles.every((r) => !r.api_key_set);
        if (s.is_default_root && noKeys) {
          setFirstRun(true);
        }
      } catch (e) {
        notify(`加载设置失败: ${String(e)}`, "error");
      }
      try {
        const r = await api.listProjects();
        setProjects(r.projects);
        setActiveName((cur) => cur ?? r.projects[0]?.name ?? null);
      } catch (e) {
        notify(`加载项目失败: ${String(e)}`, "error");
      }
    })();
  }, [notify]);

  const apiKeysReady = !!settings?.api_roles.some(
    (r) => r.role === "assistant" && r.api_key_set
  );

  // ---- 项目操作 ----
  async function refreshProjects() {
    try {
      const r = await api.listProjects();
      setProjects(r.projects);
    } catch (e) {
      notify(`刷新项目失败: ${String(e)}`, "error");
    }
  }

  async function createProject(input: { name?: string; topic: string; perspective: string }) {
    try {
      const r = await api.createProject(input);
      setProjects((ps) => [r.project, ...ps]);
      setActiveName(r.project.name);
      setShowCreate(false);
      // G 阶段：创建即进入 topic，自动应用默认面板
      if (r.stage_info) {
        setLeftKind(r.stage_info.default_left_pane as PaneKind);
        setRightKind(r.stage_info.default_right_pane as PaneKind);
      }
      if (r.project.is_placeholder_name) {
        notify(`已创建占位项目「${r.project.name}」，选题完成后可重命名`, "ok");
      } else {
        notify(`已创建项目「${r.project.name}」`, "ok");
      }
    } catch (e) {
      notify(`创建失败: ${String(e)}`, "error");
    }
  }

  async function deleteProject(name: string) {
    if (!confirm(`确定删除项目「${name}」？此操作不可逆。\n（仅从索引移除，磁盘上的目录暂保留）`)) return;
    try {
      await api.deleteProject(name);
      setProjects((ps) => ps.filter((p) => p.name !== name));
      if (activeName === name) {
        setActiveName(null);
      }
      notify(`已删除「${name}」`, "ok");
    } catch (e) {
      notify(`删除失败: ${String(e)}`, "error");
    }
  }

  async function doRename(oldName: string, newName: string) {
    try {
      const r = await api.renameProject(oldName, newName);
      setProjects((ps) => ps.map((p) => (p.name === oldName ? r.project : p)));
      setActiveName(r.project.name);
      setRenameTarget(null);
      notify(`已重命名为「${r.project.name}」`, "ok");
    } catch (e) {
      notify(`重命名失败: ${String(e)}`, "error");
    }
  }

  async function switchStage(stage: string) {
    if (!active) return;
    try {
      const r = await api.updateProject(active.name, { stage });
      setProjects((ps) => ps.map((p) => (p.name === r.project.name ? r.project : p)));
      // G 阶段：阶段变更时按 stage_info 自动应用默认面板
      if (r.stage_changed && r.stage_info) {
        setLeftKind(r.stage_info.default_left_pane as PaneKind);
        setRightKind(r.stage_info.default_right_pane as PaneKind);
        notify(`已切换到「${r.stage_info.label}」阶段，已自动应用默认面板`, "ok");
      }
    } catch (e) {
      notify(`切换阶段失败: ${String(e)}`, "error");
    }
  }

  // G 阶段：StageGuidePanel 直接传递的阶段切换回调
  async function handleStageChangeFromPanel(stage: string) {
    await switchStage(stage);
  }

  // ---- 拖拽分隔条 ----
  const draggingRef = useRef(false);
  function onDragStart() { draggingRef.current = true; }
  useEffect(() => {
    function move(e: MouseEvent) {
      if (!draggingRef.current) return;
      const root = document.querySelector(".work-area") as HTMLElement | null;
      if (!root) return;
      const r = root.getBoundingClientRect();
      const pct = ((e.clientX - r.left) / r.width) * 100;
      setSplitPct(Math.max(20, Math.min(80, pct)));
    }
    function up() { draggingRef.current = false; }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  // ---- 渲染 ----
  return (
    <div className={"app-shell " + (railCollapsed ? "rail-collapsed" : "")}>
      <LeftRail
        collapsed={railCollapsed}
        onToggle={() => setRailCollapsed((v) => !v)}
        projects={projects}
        activeName={activeName}
        onSelect={setActiveName}
        onCreate={() => setShowCreate(true)}
        onRename={(name) => setRenameTarget(name)}
        onDelete={deleteProject}
        onStageChange={switchStage}
        onOpenSettings={() => setShowSettings(true)}
      />

      <main className="main-area">
        <header className="top-bar">
          <span className="muted">
            {active
              ? `当前项目 · ${active.name} · ${stageLabel(active.stage)}`
              : "未选项目"}
          </span>
          <span className="muted-small">
            {backendOk === false ? "● 后端未连接"
              : backendOk === true ? `● ${settings?.data_root ?? ""}`
              : "连接中…"}
            {apiKeysReady ? "  · AI 已配置" : "  · AI 未配置"}
          </span>
        </header>

        <div className="work-area">
          <div style={{ width: `${splitPct}%` }}>
            <WorkPane
              side="left"
              kind={leftKind}
              onKindChange={setLeftKind}
              project={active}
              mdContent={mdContent}
              onMdChange={setMdContent}
              apiKeysReady={apiKeysReady}
              onOpenSettings={() => setShowSettings(true)}
              notify={notify}
              onStageChange={handleStageChangeFromPanel}
            />
          </div>
          <div className="splitter" onMouseDown={onDragStart} />
          <div style={{ width: `${100 - splitPct}%` }}>
            <WorkPane
              side="right"
              kind={rightKind}
              onKindChange={setRightKind}
              project={active}
              mdContent={mdContent}
              onMdChange={setMdContent}
              apiKeysReady={apiKeysReady}
              onOpenSettings={() => setShowSettings(true)}
              notify={notify}
              onStageChange={handleStageChangeFromPanel}
            />
          </div>
        </div>
      </main>

      {firstRun && settings && (
        <FirstRunDialog
          current={settings}
          notify={notify}
          onSkip={() => setFirstRun(false)}
          onDone={(s) => { setSettings(s); setFirstRun(false); setShowSettings(true); }}
        />
      )}

      <SettingsDialog
        open={showSettings}
        onClose={() => setShowSettings(false)}
        onSaved={(s) => setSettings(s)}
        notify={notify}
      />

      <CreateProjectDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreate={createProject}
      />

      <RenameDialog
        open={!!renameTarget}
        oldName={renameTarget ?? ""}
        onClose={() => setRenameTarget(null)}
        onRename={(n) => doRename(renameTarget!, n)}
      />

      <Toast msg={toast} onClose={() => setToast(null)} />
    </div>
  );
}

function stageLabel(stage: string): string {
  return {
    topic: "选题",
    review: "文献综述",
    writing: "正文撰写",
    citation: "引用",
    typesetting: "排版",
  }[stage] ?? stage;
}

