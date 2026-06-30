/**
 * PaperAssistant backend client（FastAPI @ 127.0.0.1:8181）。
 *
 * 所有方法在网络/HTTP 错误时抛出，由组件层捕获并上报 debug-assistant。
 */

import { daReport } from "../lib/debugAssistant";

const BASE =
  (import.meta as unknown as { env?: { VITE_API_BASE?: string } }).env
    ?.VITE_API_BASE ?? "http://127.0.0.1:8181";

export interface Project {
  name: string;
  stage: string;
  perspective: string;
  topic: string;
  created_at: string;
  last_modified: string;
  is_placeholder_name?: boolean;
}

export interface LiteratureCard {
  doi: string;
  title: string;
  journal: string;
  first_author: string;
  corresponding_author: string;
  keywords: string;
  abstract: string;
  category: string;
  subcategory: string;
  status: string;
  last_modified: string;
  [k: string]: string;
}

export interface CitationRow {
  doi: string;
  label: string;
  used_in: string;
  note: string;
  added_at: string;
}

export interface ApiRoleConfig {
  role: string;
  endpoint: string;
  model: string;
  api_key_set: boolean;
  timeout: string;
  last_modified: string;
}

export interface CategoryRow {
  perspective: string;
  category: string;
  subcategory: string;
}

export interface CustomFieldRow {
  field_name: string;
  field_type: string;
  description: string;
}

export interface SettingsSnapshot {
  data_root: string;
  monitor_dir: string;
  is_default_root: boolean;
  pointer_file: string;
  api_roles: ApiRoleConfig[];
  categories: CategoryRow[];
  custom_fields: CustomFieldRow[];
}



export interface StageStep {
  id: number;
  title: string;
  actor: string;
  audit: string;
}

export interface StageInfo {
  stage: string;
  label: string;
  default_left_pane: string;
  default_right_pane: string;
  steps: StageStep[];
  intro_md: string;
  expected_panels: string[];
  audit_hint: string;
  all_stages?: StageInfo[];
}

export interface SelectionRow {
  doi: string;
  stage: string;
  selected: string; // "true" / "false"（CSV 持久化为字符串）
  source_label: string;
  note: string;
  updated_at: string;
}

export interface SelectionInput {
  doi: string;
  stage: string;
  selected: boolean;
  source_label?: string;
  note?: string;
}

export interface AggregateResult {
  written: number;
  by_stage_selected_count: Record<string, number>;
  empty_stages: string[];
  skipped_no_doi: number;
  selected_csv_path: string;
}

export interface ProjectWithStage {
  project: Project;
  stage_info?: StageInfo;
  stage_changed?: boolean;
  is_placeholder_name?: boolean;
}

export type AIRole = "assistant" | "auditor" | "secretary";

export interface AIChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

// SPEC §4.3：12 种任务类型
export type AIChatTaskType =
  // 必须自动核查（6）
  | "summarize_literature"
  | "extract_textbook"
  | "extract_methodology"
  | "compare_literature"
  | "regen_literature_card"
  | "generate_knowledge_card"
  // 建议（4）
  | "recommend_topic"
  | "recommend_keywords"
  | "suggest_method"
  | "suggest_framework"
  // 自由（2）
  | "free_chat"
  | "other";

export type AIChatPolicy = "must_audit" | "suggestion" | "free";

export interface TaskTypeInfo {
  key: AIChatTaskType;
  label: string;
  policy: AIChatPolicy;
  requires_sources: boolean;
}

export interface ChatSource {
  title?: string;
  snippet: string;
}

export interface AIChatRequest {
  role?: AIRole;
  messages: AIChatMessage[];
  project?: string;
  stage?: string;
  task_type?: AIChatTaskType;
  sources?: ChatSource[];
  extra?: Record<string, unknown>;
}

// SPEC §4.3：6 种 audit_status
export type AuditStatus =
  | "verified"
  | "failed"
  | "not_configured"
  | "suggestion"
  | "user"
  | "error";

export interface AIChatResponse {
  success: boolean;
  role: string;
  effective_role: string;
  output: string;
  audit_status: AuditStatus;
  audit_rounds: number;
  audit_feedback: string;
  audit_log_path: string;
  audit_dropped: boolean;
  task_type: string;
  task_label: string;
  error: string;
  error_code: string;
  project?: string | null;
  stage?: string | null;
}

export interface AIRoleStatus {
  role: string;
  configured: boolean;
  has_endpoint: boolean;
  has_key: boolean;
  has_model: boolean;
  endpoint: string;
  model: string;
}

export interface VerifySource {
  title?: string;
  snippet: string;
}

export interface VerifyRequest {
  content: string;
  sources: VerifySource[];
  project?: string;
  max_rounds?: number;
}

export interface VerifyResponse {
  status: "verified" | "failed" | "not_configured" | "error";
  final_content: string;  // failed 时后端会清空（硬丢弃，禁止入库）
  rounds: number;
  last_feedback: string;
  log_path: string;
  audit_status: AuditStatus;
}

// 知识库相关（与后端 KNOWLEDGE_CSV_HEADERS 对齐）
export interface KnowledgeCard {
  card_id: string;
  subject: string;
  title: string;
  prompt: string;
  summary: string;
  audited: string;             // "true" / "false"
  source_book: string;
  source_section: string;
  last_modified: string;
  [k: string]: string;
}

export interface SubjectInfo {
  subject: string;
  textbook_count: number;
  card_count: number;
}

export interface TextbookInfo {
  name: string;
  size: number;
  uploaded_at: string;
  md_extracted?: boolean;
  [k: string]: string | number | boolean | undefined;
}

// 临时知识（追加入参）
export interface TempKnowledgeAppendInput {
  title: string;
  content: string;
  source?: string;
  section?: string;
  task_type?: string;
  audited: boolean;
}
// 临时知识文件包含 Markdown 全文，items 概念已废弃
export interface TempKnowledgeRead {
  project: string;
  path: string;
  content: string;
  size_bytes: number;
}

async function _json<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(input, init);
  } catch (e) {
    void daReport({
      error: e,
      severity: "error",
      operation_path: typeof input === "string" ? input : "(req)",
      user_action: "fetch",
    });
    throw e;
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    const err = new Error(`HTTP ${resp.status} ${resp.statusText}: ${text}`);
    void daReport({
      error: err,
      severity: "warning",
      operation_path: resp.url,
      context: { status: resp.status, body: text.slice(0, 400) },
    });
    throw err;
  }
  return (await resp.json()) as T;
}

export const api = {
  // ---------- health ----------
  health() {
    return _json<{ status: string; service: string; data_root: string }>(
      `${BASE}/api/health`
    );
  },

  // ---------- settings ----------
  getSettings() {
    return _json<SettingsSnapshot>(`${BASE}/api/settings`);
  },
  setDataRoot(path: string) {
    return _json<{ ok: boolean; data_root: string; monitor_dir: string; is_default_root: boolean }>(
      `${BASE}/api/settings/data-root`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      }
    );
  },
  setMonitorDir(path: string) {
    return _json<{ ok: boolean; monitor_dir: string }>(`${BASE}/api/settings/monitor-dir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  },
  listApiConfig() {
    return _json<{ items: ApiRoleConfig[] }>(`${BASE}/api/settings/api-config`);
  },
  saveApiConfig(input: {
    role: string;
    endpoint?: string;
    model?: string;
    api_key?: string | null;
    timeout?: number;
  }) {
    return _json<{ ok: boolean; role: string; api_key_set: boolean }>(
      `${BASE}/api/settings/api-config`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }
    );
  },
  saveCategories(items: CategoryRow[]) {
    return _json<{ ok: boolean; count: number }>(
      `${BASE}/api/settings/category-config`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      }
    );
  },
  saveCustomFields(items: CustomFieldRow[]) {
    return _json<{ ok: boolean; count: number }>(
      `${BASE}/api/settings/custom-fields`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      }
    );
  },

  // ---------- project ----------
  listProjects() {
    return _json<{ projects: Project[] }>(`${BASE}/api/project`);
  },
  createProject(input: { name?: string; topic?: string; perspective?: string }) {
    return _json<ProjectWithStage>(`${BASE}/api/project`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },
  updateProject(
    name: string,
    patch: { stage?: string; perspective?: string; topic?: string }
  ) {
    return _json<ProjectWithStage>(
      `${BASE}/api/project/${encodeURIComponent(name)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }
    );
  },
  renameProject(oldName: string, newName: string) {
    return _json<{ project: Project; old_name: string; new_name: string }>(
      `${BASE}/api/project/${encodeURIComponent(oldName)}/rename`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_name: newName }),
      }
    );
  },
  deleteProject(name: string) {
    return _json<{ name: string; deleted_from_index: boolean }>(
      `${BASE}/api/project/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
  },

  // ---------- literature ----------
  listLiterature(q?: string) {
    const u = new URL(`${BASE}/api/literature`);
    if (q) u.searchParams.set("q", q);
    return _json<{ cards: LiteratureCard[]; total: number }>(u.toString());
  },
  upsertLiterature(card: Partial<LiteratureCard> & { doi: string }) {
    return _json<{ card: LiteratureCard; created: boolean }>(
      `${BASE}/api/literature`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(card),
      }
    );
  },
  async uploadPDF(file: File, opt: { doi?: string; title?: string } = {}) {
    const u = new URL(`${BASE}/api/literature/upload`);
    if (opt.doi) u.searchParams.set("doi", opt.doi);
    if (opt.title) u.searchParams.set("title", opt.title);
    const fd = new FormData();
    fd.append("file", file);
    return _json<{
      card: LiteratureCard;
      created: boolean;
      mineru: { success: boolean; message: string; page_count?: number; truncated?: boolean };
    }>(u.toString(), { method: "POST", body: fd });
  },

  // ---------- citation ----------
  listCitations(project: string) {
    return _json<{ citations: CitationRow[] }>(
      `${BASE}/api/citation/${encodeURIComponent(project)}`
    );
  },
  addCitation(
    project: string,
    input: { doi: string; label?: string; used_in?: string; note?: string }
  ) {
    return _json<{ citation: CitationRow; created: boolean }>(
      `${BASE}/api/citation/${encodeURIComponent(project)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }
    );
  },

  // ---------- typesetting ----------
  exportManuscript(project: string) {
    return _json<{
      project: string;
      manuscript_path: string;
      chapters: string[];
    }>(`${BASE}/api/typesetting/${encodeURIComponent(project)}/export`, {
      method: "POST",
    });
  },

  renderTex(project: string) {
    return _json<{
      project: string;
      tex_path: string;
      bytes: number;
      had_title_var: boolean;
      had_body_var: boolean;
    }>(`${BASE}/api/typesetting/${encodeURIComponent(project)}/render_tex`, {
      method: "POST",
    });
  },

  compilePdf(project: string) {
    return _json<{
      project: string;
      compiled: boolean;
      pdf_path?: string;
      bytes?: number;
      tectonic_bin?: string;
      reason?: "tectonic_not_found" | "tectonic_failed" | "timeout";
      hint?: string;
      returncode?: number;
      stderr_tail?: string;
      stdout_tail?: string;
    }>(`${BASE}/api/typesetting/${encodeURIComponent(project)}/compile_pdf`, {
      method: "POST",
    });
  },

  // ---------- ai ----------
  aiChat(input: AIChatRequest) {
    return _json<AIChatResponse>(`${BASE}/api/ai/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: input.role ?? "assistant",
        messages: input.messages,
        project: input.project ?? null,
        stage: input.stage ?? null,
        task_type: input.task_type ?? "free_chat",
        sources: input.sources ?? [],
        extra: input.extra ?? null,
      }),
    });
  },
  aiStatus() {
    return _json<{ items: AIRoleStatus[] }>(`${BASE}/api/ai/status`);
  },
  aiTaskTypes() {
    return _json<{ items: TaskTypeInfo[] }>(`${BASE}/api/ai/task_types`);
  },
  aiVerify(input: VerifyRequest) {
    return _json<VerifyResponse>(`${BASE}/api/ai/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: input.content,
        sources: input.sources,
        project: input.project ?? null,
        max_rounds: input.max_rounds ?? 5,
      }),
    });
  },

  // ---------- knowledge (SPEC §8.2) ----------
  listSubjects() {
    return _json<{ subjects: SubjectInfo[] }>(`${BASE}/api/knowledge/subjects`);
  },
  createSubject(subject: string) {
    const u = new URL(`${BASE}/api/knowledge/subjects`);
    u.searchParams.set("subject", subject);
    return _json<{ ok: boolean; subject: string }>(u.toString(), { method: "POST" });
  },
  listTextbooks(subject: string) {
    const u = new URL(`${BASE}/api/knowledge/textbooks`);
    u.searchParams.set("subject", subject);
    return _json<{ items: TextbookInfo[] }>(u.toString());
  },
  async uploadTextbook(file: File, subject: string) {
    const u = new URL(`${BASE}/api/knowledge/textbook`);
    u.searchParams.set("subject", subject);
    const fd = new FormData();
    fd.append("file", file);
    return _json<{ ok: boolean; subject: string; name: string; mineru: { success: boolean; message: string } }>(
      u.toString(),
      { method: "POST", body: fd }
    );
  },
  deleteTextbook(subject: string, name: string) {
    return _json<{ ok: boolean }>(
      `${BASE}/api/knowledge/textbooks/${encodeURIComponent(subject)}/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
  },
  listKnowledgeCards(subject?: string, q?: string, limit?: number) {
    const u = new URL(`${BASE}/api/knowledge`);
    if (subject) u.searchParams.set("subject", subject);
    if (q) u.searchParams.set("q", q);
    if (limit !== undefined) u.searchParams.set("limit", String(limit));
    return _json<{ cards: KnowledgeCard[]; total: number }>(u.toString());
  },
  upsertKnowledgeCard(card: {
    card_id?: string;
    subject: string;
    title: string;
    prompt?: string;
    summary: string;
    source_book?: string;
    source_section?: string;
    audited: boolean;
  }) {
    return _json<{ card: KnowledgeCard; created: boolean; markdown_path: string }>(`${BASE}/api/knowledge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(card),
    });
  },
  getKnowledgeCard(cardId: string) {
    return _json<{ card: KnowledgeCard }>(
      `${BASE}/api/knowledge/${encodeURIComponent(cardId)}`
    );
  },
  async getKnowledgeCardMarkdown(cardId: string): Promise<string> {
    const resp = await fetch(
      `${BASE}/api/knowledge/by-id/markdown/${encodeURIComponent(cardId)}`
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
    return resp.text();
  },
  deleteKnowledgeCard(cardId: string) {
    return _json<{ card_id: string; subject: string; deleted_from_index: boolean }>(
      `${BASE}/api/knowledge/${encodeURIComponent(cardId)}`,
      { method: "DELETE" }
    );
  },

  // ---------- temp_knowledge (SPEC §8.4) ----------
  getTempKnowledge(project: string) {
    return _json<TempKnowledgeRead>(
      `${BASE}/api/temp_knowledge/${encodeURIComponent(project)}`
    );
  },
  appendTempKnowledge(project: string, input: TempKnowledgeAppendInput) {
    return _json<{ ok: boolean; project: string; path: string; appended: boolean }>(
      `${BASE}/api/temp_knowledge/${encodeURIComponent(project)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }
    );
  },
  clearTempKnowledge(project: string) {
    return _json<{ ok: boolean; project: string; backup_path: string }>(
      `${BASE}/api/temp_knowledge/${encodeURIComponent(project)}/clear`,
      { method: "POST" }
    );
  },
  deleteTempKnowledge(project: string) {
    return _json<{ ok: boolean; project: string }>(
      `${BASE}/api/temp_knowledge/${encodeURIComponent(project)}`,
      { method: "DELETE" }
    );
  },

  // ---------- draft 正文读写（SPEC §六 / §7.3） ----------
  async getDraft(project: string): Promise<string> {
    const r = await fetch(`${BASE}/api/project/${encodeURIComponent(project)}/draft`);
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`getDraft ${r.status}: ${txt}`);
    }
    return await r.text();
  },
  saveDraft(project: string, content: string) {
    return _json<{ name: string; path: string; bytes: number; saved_at: string }>(
      `${BASE}/api/project/${encodeURIComponent(project)}/draft`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }
    );
  },

  // ---------- file_watcher (SPEC §九) ----------
  watcherStatus() {
    return _json<{
      running: boolean;
      monitor_dir: string;
      output_root: string;
      processed_count: number;
      mineru_configured: boolean;
    }>(`${BASE}/api/file_watcher/status`);
  },
  watcherStart() {
    return _json<{ ok: boolean; running: boolean }>(
      `${BASE}/api/file_watcher/start`,
      { method: "POST" }
    );
  },
  watcherStop() {
    return _json<{ ok: boolean; running: boolean }>(
      `${BASE}/api/file_watcher/stop`,
      { method: "POST" }
    );
  },
  watcherScan() {
    return _json<{ ok: boolean; processed_this_round: number }>(
      `${BASE}/api/file_watcher/scan`,
      { method: "POST" }
    );
  },
  watcherProcessed(limit?: number) {
    const u = new URL(`${BASE}/api/file_watcher/processed`);
    if (limit !== undefined) u.searchParams.set("limit", String(limit));
    return _json<{ items: Record<string, string>[]; total: number }>(u.toString());
  },

  // ---------- G 阶段：stage-info + selections（SPEC §六 / §7.1-7.5） ----------
  getStageInfo(project: string, stage?: string) {
    const u = new URL(`${BASE}/api/project/${encodeURIComponent(project)}/stage-info`);
    if (stage) u.searchParams.set("stage", stage);
    return _json<{ current: StageInfo; all_stages: StageInfo[] }>(u.toString());
  },
  listSelections(project: string, stage?: string) {
    const u = new URL(`${BASE}/api/project/${encodeURIComponent(project)}/selections`);
    if (stage) u.searchParams.set("stage", stage);
    return _json<{ selections: SelectionRow[]; by_stage: Record<string, { selected: number; deselected: number }> }>(u.toString());
  },
  saveSelection(project: string, input: SelectionInput) {
    return _json<{ selection: SelectionRow; total: number }>(
      `${BASE}/api/project/${encodeURIComponent(project)}/selections`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }
    );
  },
  saveSelectionsBulk(project: string, items: SelectionInput[]) {
    return _json<{ saved: SelectionRow[]; count: number }>(
      `${BASE}/api/project/${encodeURIComponent(project)}/selections/bulk`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      }
    );
  },
  deleteSelection(project: string, doi: string, stage: string) {
    const u = new URL(`${BASE}/api/project/${encodeURIComponent(project)}/selections`);
    u.searchParams.set("doi", doi);
    u.searchParams.set("stage", stage);
    return _json<{ doi: string; stage: string; removed: boolean; remaining: number }>(
      u.toString(),
      { method: "DELETE" }
    );
  },
  aggregateSelections(project: string) {
    return _json<AggregateResult>(
      `${BASE}/api/project/${encodeURIComponent(project)}/selections/aggregate`,
      { method: "POST" }
    );
  },
};
