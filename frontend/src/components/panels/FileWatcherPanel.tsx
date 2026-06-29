/**
 * 监控目录 file_watcher 控制台（SPEC §九）。
 *
 * F6 阶段新增（配合 E 阶段后端 file_watcher 服务）：
 *  · 状态卡片：running / monitor_dir / output_root / processed_count / mineru_configured
 *  · 控制按钮：启动 / 停止 / 立即扫描一次
 *  · 已处理列表（最近 N 条）：文件名 / sha1 / processed_at / 成功失败 / 输出 MD 路径
 *  · 自动刷新（每 5s 拉取一次状态）
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";

interface WatcherStatus {
  running: boolean;
  monitor_dir: string;
  output_root: string;
  processed_count: number;
  mineru_configured: boolean;
}

export function FileWatcherPanel({
  notify,
}: {
  notify: (s: string, k?: "ok" | "warn" | "error") => void;
}) {
  const [status, setStatus] = useState<WatcherStatus | null>(null);
  const [items, setItems] = useState<Record<string, string>[]>([]);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.watcherStatus();
      setStatus(s);
    } catch (e) {
      console.warn("watcherStatus failed:", e);
    }
  }, []);

  const loadProcessed = useCallback(async () => {
    try {
      const r = await api.watcherProcessed(50);
      setItems(r.items);
    } catch (e) {
      console.warn("watcherProcessed failed:", e);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    void loadProcessed();
  }, [loadStatus, loadProcessed]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = window.setInterval(() => {
      void loadStatus();
      void loadProcessed();
    }, 5000);
    return () => window.clearInterval(t);
  }, [autoRefresh, loadStatus, loadProcessed]);

  async function doStart() {
    setBusy(true);
    try {
      const r = await api.watcherStart();
      notify(r.running ? "watcher 已启动" : "watcher 启动失败", r.running ? "ok" : "warn");
      await loadStatus();
    } catch (e) {
      notify(`启动失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function doStop() {
    setBusy(true);
    try {
      const r = await api.watcherStop();
      notify(!r.running ? "watcher 已停止" : "停止失败", !r.running ? "ok" : "warn");
      await loadStatus();
    } catch (e) {
      notify(`停止失败: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function doScan() {
    setScanning(true);
    try {
      const r = await api.watcherScan();
      notify(`扫描完成，本轮处理 ${r.processed_this_round} 个文件`, "ok");
      await loadProcessed();
      await loadStatus();
    } catch (e) {
      notify(`扫描失败: ${String(e)}`, "error");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="watcher-panel">
      <header className="watcher-head">
        <h3>监控目录 file_watcher</h3>
        <label className="muted-small">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          {" "}5s 自动刷新
        </label>
      </header>

      {!status && <div className="muted">加载状态中…（如果后端未启动会一直为空）</div>}

      {status && (
        <div className="watcher-status">
          <div className={"watcher-state " + (status.running ? "running" : "stopped")}>
            {status.running ? "● 运行中" : "○ 已停止"}
          </div>
          <div className="watcher-info">
            <div>
              <strong>监控目录</strong>
              <code>{status.monitor_dir}</code>
            </div>
            <div>
              <strong>输出目录</strong>
              <code>{status.output_root}</code>
            </div>
            <div>
              <strong>已处理</strong>
              <span>{status.processed_count} 个文件</span>
            </div>
            <div>
              <strong>MinerU</strong>
              <span>
                {status.mineru_configured ? (
                  <span className="kb-audited-badge">已配置</span>
                ) : (
                  <span className="kb-unaudited-badge">未配置（占位模式）</span>
                )}
              </span>
            </div>
          </div>
          <div className="watcher-actions">
            <button
              className="primary-btn"
              onClick={() => void doStart()}
              disabled={busy || status.running}
            >
              启动
            </button>
            <button
              className="secondary-btn"
              onClick={() => void doStop()}
              disabled={busy || !status.running}
            >
              停止
            </button>
            <button
              className="secondary-btn"
              onClick={() => void doScan()}
              disabled={scanning}
            >
              {scanning ? "扫描中…" : "立即扫描一次"}
            </button>
          </div>
          <div className="muted-small">
            把 PDF 拖进监控目录即可自动转换；输出 Markdown 落到 <code>auto_imported/</code>。
            sha1 去重，同一文件多次拖入只会处理一次。MinerU 未配置时落占位 MD（不会丢文件）。
          </div>
        </div>
      )}

      <h4 style={{ marginTop: 16 }}>已处理文件（最近 50 条）</h4>
      {items.length === 0 && <div className="muted-small">暂无处理记录</div>}
      <div className="watcher-list">
        {items.map((it, idx) => (
          <div key={idx} className="watcher-row">
            <div className="watcher-row-head">
              <code className="watcher-fname">{it.file_name || "(未知文件)"}</code>
              <span
                className={
                  "watcher-result " +
                  (String(it.success).toLowerCase() === "true" ? "ok" : "fail")
                }
              >
                {String(it.success).toLowerCase() === "true" ? "✓ 成功" : "✗ 失败"}
              </span>
              <span className="muted-small">{it.processed_at || ""}</span>
            </div>
            {it.output_md && (
              <div className="muted-small">
                → <code>{it.output_md}</code>
              </div>
            )}
            {it.message && <div className="muted-small watcher-msg">{it.message}</div>}
            {it.sha1 && (
              <div className="muted-small">
                sha1: <code>{it.sha1.slice(0, 16)}…</code>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
