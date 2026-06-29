/**
 * 单个工作区面板（SPEC §六）。
 *
 * 可切换内容类型（按 SPEC 完整列出）：
 * · AI 对话（含审计状态、交互式勾选组件）
 * · 搜索网站（内嵌 WebView，用户可自定义）
 * · 知识库检索
 * · Markdown 编辑器（所见即所得）
 * · LaTeX 预览
 * · 文献卡片列表
 * · 知识库卡片列表
 * · 监控目录 file_watcher（F6 新增，配合 SPEC §九）
 */
import type { Project } from "../api/client";
import { AIChatPanel } from "./panels/AIChatPanel";
import { WebViewPanel } from "./panels/WebViewPanel";
import { KBSearchPanel } from "./panels/KBSearchPanel";
import { MarkdownEditorPanel } from "./panels/MarkdownEditorPanel";
import { LatexPreviewPanel } from "./panels/LatexPreviewPanel";
import { LiteratureListPanel } from "./panels/LiteratureListPanel";
import { KBCardListPanel } from "./panels/KBCardListPanel";
import { FileWatcherPanel } from "./panels/FileWatcherPanel";
import StageGuidePanel from "./panels/StageGuidePanel";
import CitationAggregatePanel from "./panels/CitationAggregatePanel";

export type PaneKind =
  | "ai-chat"
  | "web"
  | "kb-search"
  | "md-editor"
  | "latex-preview"
  | "lit-list"
  | "kb-list"
  | "file-watcher"
  | "stage-guide"
  | "citation-aggregate";

export const PANE_KINDS: { value: PaneKind; label: string }[] = [
  { value: "ai-chat",       label: "AI 对话" },
  { value: "web",           label: "搜索网站" },
  { value: "kb-search",     label: "知识库检索" },
  { value: "md-editor",     label: "Markdown 编辑器" },
  { value: "latex-preview", label: "LaTeX 预览" },
  { value: "lit-list",      label: "文献卡片列表" },
  { value: "kb-list",       label: "知识库卡片列表" },
  { value: "file-watcher",  label: "监控目录（自动转换）" },
  { value: "stage-guide",       label: "阶段引导（G）" },
  { value: "citation-aggregate", label: "引用汇总（G）" },
];

interface Props {
  side: "left" | "right";
  kind: PaneKind;
  onKindChange: (k: PaneKind) => void;
  project: Project | null;
  // 编辑器联动：左 md 编辑 → 右 latex 同步
  mdContent: string;
  onMdChange: (s: string) => void;
  // 设置：4 个 AI 接口位状态等
  apiKeysReady: boolean;
  onOpenSettings: () => void;
  // 通用通知
  notify: (text: string, kind?: "ok" | "warn" | "error") => void;
  // G 阶段：StageGuidePanel 切换阶段时回调（父组件触发 updateProject）
  onStageChange?: (stage: string) => void | Promise<void>;
}

export function WorkPane(props: Props) {
  const {
    side, kind, onKindChange, project,
    mdContent, onMdChange, apiKeysReady, onOpenSettings, notify,
    onStageChange,
  } = props;

  return (
    <section className="work-pane">
      <header className="work-pane-head">
        <span className="pane-side-badge">{side === "left" ? "左工作区" : "右工作区"}</span>
        <select
          className="pane-kind-select"
          value={kind}
          onChange={(e) => onKindChange(e.target.value as PaneKind)}
        >
          {PANE_KINDS.map((k) => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>
      </header>

      <div className="work-pane-body">
        {kind === "ai-chat" && (
          <AIChatPanel
            project={project}
            apiKeysReady={apiKeysReady}
            onOpenSettings={onOpenSettings}
            notify={notify}
          />
        )}
        {kind === "web" && <WebViewPanel notify={notify} />}
        {kind === "kb-search" && <KBSearchPanel project={project} notify={notify} />}
        {kind === "md-editor" && (
          <MarkdownEditorPanel
            project={project}
            content={mdContent}
            onChange={onMdChange}
            notify={notify}
          />
        )}
        {kind === "latex-preview" && (
          <LatexPreviewPanel mdSource={mdContent} project={project} notify={notify} />
        )}
        {kind === "lit-list" && (
          <LiteratureListPanel project={project} notify={notify} />
        )}
        {kind === "kb-list" && <KBCardListPanel notify={notify} />}
        {kind === "file-watcher" && <FileWatcherPanel notify={notify} />}
        {kind === "stage-guide" && (
          <StageGuidePanel
            projectName={project?.name || ""}
            currentStage={project?.stage || "topic"}
            onStageChange={async (s) => {
              if (onStageChange) await onStageChange(s);
            }}
          />
        )}
        {kind === "citation-aggregate" && (
          <CitationAggregatePanel projectName={project?.name || ""} />
        )}
      </div>
    </section>
  );
}
