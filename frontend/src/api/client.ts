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
  // health
  health() {
    return _json<{ status: string; service: string; data_root: string }>(
      `${BASE}/api/health`
    );
  },

  // project
  listProjects() {
    return _json<{ projects: Project[] }>(`${BASE}/api/project`);
  },
  createProject(input: { name: string; topic?: string; perspective?: string }) {
    return _json<{ project: Project }>(`${BASE}/api/project`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },
  updateProject(
    name: string,
    patch: { stage?: string; perspective?: string; topic?: string }
  ) {
    return _json<{ project: Project }>(
      `${BASE}/api/project/${encodeURIComponent(name)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }
    );
  },
  deleteProject(name: string) {
    return _json<{ name: string; deleted_from_index: boolean }>(
      `${BASE}/api/project/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    );
  },

  // literature
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
      mineru: { success: boolean; message: string };
    }>(u.toString(), { method: "POST", body: fd });
  },

  // citation
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

  // typesetting
  exportManuscript(project: string) {
    return _json<{
      project: string;
      manuscript_path: string;
      chapters: string[];
    }>(`${BASE}/api/typesetting/${encodeURIComponent(project)}/export`, {
      method: "POST",
    });
  },
};
