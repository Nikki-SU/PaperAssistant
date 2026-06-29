/**
 * debug-assistant TypeScript SDK（内联精简版）。
 *
 * 直接内联避免在 Tauri 项目里 link 本地 npm 包。
 * 失败必须降级：连不上 server 时绝不抛错给业务侧。
 */

export interface DAConfig {
  project: string;
  module: string;
  host?: string;
  port?: number;
  enabled?: boolean;
  timeoutMs?: number;
}

export interface DAReportPayload {
  error?: unknown;
  error_type?: string;
  error_message?: string;
  stack_trace?: string;
  severity?: "info" | "warning" | "error" | "critical";
  context?: Record<string, unknown>;
  user_action?: string;
  stage?: string;
  operation_path?: string;
}

class DebugAssistantClient {
  private cfg: Required<DAConfig>;
  private base: string;

  constructor(cfg: DAConfig) {
    this.cfg = {
      host: "127.0.0.1",
      port: 8765,
      enabled: true,
      timeoutMs: 2000,
      ...cfg,
    } as Required<DAConfig>;
    this.base = `http://${this.cfg.host}:${this.cfg.port}`;
  }

  async report(payload: DAReportPayload): Promise<string | null> {
    if (!this.cfg.enabled) return null;
    const err = payload.error;
    const body: Record<string, unknown> = {
      project: this.cfg.project,
      module: this.cfg.module,
      severity: payload.severity ?? "error",
      error_type:
        payload.error_type ??
        (err instanceof Error ? err.name : typeof err) ??
        "UnknownError",
      error_message:
        payload.error_message ??
        (err instanceof Error ? err.message : String(err ?? "")),
      stack_trace:
        payload.stack_trace ??
        (err instanceof Error ? err.stack ?? "" : ""),
      context: payload.context ?? {},
      user_action: payload.user_action ?? "",
      stage: payload.stage ?? "",
      operation_path: payload.operation_path ?? "",
    };
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), this.cfg.timeoutMs);
      const resp = await fetch(`${this.base}/api/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!resp.ok) return null;
      const data = (await resp.json()) as { error_id?: string };
      return data.error_id ?? null;
    } catch {
      return null; // 静默降级
    }
  }

  installGlobalHandlers(): void {
    if (typeof window === "undefined") return;
    window.addEventListener("error", (event) => {
      const e = event as ErrorEvent;
      const err = e.error ?? new Error(e.message);
      void this.report({ error: err });
    });
    window.addEventListener("unhandledrejection", (event) => {
      const e = event as PromiseRejectionEvent;
      const err = e.reason instanceof Error ? e.reason : new Error(String(e.reason));
      void this.report({ error: err, error_type: "UnhandledRejection" });
    });
  }
}

let _client: DebugAssistantClient | null = null;

export function installDebugAssistant(cfg: DAConfig): void {
  _client = new DebugAssistantClient(cfg);
  _client.installGlobalHandlers();
}

export function daReport(payload: DAReportPayload): Promise<string | null> {
  if (!_client) return Promise.resolve(null);
  return _client.report(payload);
}
