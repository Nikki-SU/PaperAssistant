/**
 * CitationAggregatePanel —— 引用汇总面板（SPEC §7.4）
 *
 * 功能：
 * - 列出 selections.csv 全部行（按 stage 分组）
 * - 一键 aggregate → 写 citations/selected.csv（同 doi 跨 stage 用 ; 合并 used_in）
 * - 显示 by_stage_selected_count 与 empty_stages 警告
 * - 单条 delete selection
 *
 * commit β 新增：
 * - 「已写入引用列表」区：调 listCitations 显示 citations/citations.csv
 * - 每条 citation 支持「删除」→ DELETE /api/citation/{project}/{doi}
 */
import { useCallback, useEffect, useState } from "react";
import { api, AggregateResult, SelectionRow, CitationRow } from "../../api/client";

interface Props {
  projectName: string;
}

const STAGE_LABELS: Record<string, string> = {
  topic: "选题",
  review: "文献综述",
  writing: "正文撰写",
  citation: "引用整理",
  typesetting: "排版",
};

export default function CitationAggregatePanel({ projectName }: Props) {
  const [rows, setRows] = useState<SelectionRow[]>([]);
  const [byStage, setByStage] = useState<Record<string, { selected: number; deselected: number }>>({});
  const [agg, setAgg] = useState<AggregateResult | null>(null);
  const [citations, setCitations] = useState<CitationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deletingCit, setDeletingCit] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  const refresh = useCallback(async () => {
    if (!projectName) return;
    setLoading(true);
    setErr("");
    try {
      const r = await api.listSelections(projectName);
      setRows(r.selections);
      setByStage(r.by_stage);
      // 同时刷新已写入的 citations
      try {
        const c = await api.listCitations(projectName);
        setCitations(c.citations);
      } catch (e2: any) {
        // citations 加载失败不阻塞 selections 刷新
        console.warn("listCitations 失败:", e2?.message || e2);
      }
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, [projectName]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleAggregate = async () => {
    if (!projectName) return;
    setBusy(true);
    setErr("");
    setInfo("");
    try {
      const r = await api.aggregateSelections(projectName);
      setAgg(r);
      setInfo(
        `已写入 citations/selected.csv：${r.written} 条；空阶段：${
          r.empty_stages.length ? r.empty_stages.join(", ") : "无"
        }`
      );
      // 汇总后立即刷新 citations 列表
      try {
        const c = await api.listCitations(projectName);
        setCitations(c.citations);
      } catch (e2: any) {
        console.warn("listCitations 失败:", e2?.message || e2);
      }
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (doi: string, stage: string) => {
    if (!projectName) return;
    setBusy(true);
    setErr("");
    try {
      await api.deleteSelection(projectName, doi, stage);
      await refresh();
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteCitation = async (doi: string) => {
    if (!projectName) return;
    if (!confirm(`确认删除引用？\n\n  DOI: ${doi}\n\n会从 citations/citations.csv 移除该行（selections.csv 不动）。`)) {
      return;
    }
    setDeletingCit(doi);
    setErr("");
    try {
      await api.deleteCitation(projectName, doi);
      setInfo(`已删除引用：${doi}`);
      const c = await api.listCitations(projectName);
      setCitations(c.citations);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setDeletingCit(null);
    }
  };

  if (!projectName) {
    return <div className="cite-aggregate cite-aggregate--empty">请先选择项目</div>;
  }

  // 按 doi 分组以预览 used_in 合并效果
  const grouped: Record<string, SelectionRow[]> = {};
  for (const r of rows) {
    if (String(r.selected).toLowerCase() !== "true") continue;
    if (!r.doi) continue;
    (grouped[r.doi] = grouped[r.doi] || []).push(r);
  }

  return (
    <div className="cite-aggregate">
      <div className="cite-aggregate__header">
        <h3>引用汇总</h3>
        <div className="cite-aggregate__counters">
          {Object.entries(byStage).map(([s, c]) => (
            <span key={s} className="cite-stage-chip">
              {STAGE_LABELS[s] || s}: <strong>{c.selected}</strong>/
              <em>{c.selected + c.deselected}</em>
            </span>
          ))}
        </div>
        <div className="cite-aggregate__actions">
          <button type="button" onClick={refresh} disabled={loading || busy}>
            刷新
          </button>
          <button
            type="button"
            onClick={handleAggregate}
            disabled={loading || busy}
            className="cite-aggregate__primary"
          >
            一键汇总 → selected.csv
          </button>
        </div>
      </div>

      {err && <div className="cite-aggregate__err">{err}</div>}
      {info && <div className="cite-aggregate__ok">{info}</div>}

      {agg && (
        <div className="cite-aggregate__summary">
          <div>
            写入：<strong>{agg.written}</strong> 条；跳过无 doi：{agg.skipped_no_doi}
          </div>
          <div>by_stage：{JSON.stringify(agg.by_stage_selected_count)}</div>
          {agg.empty_stages.length > 0 && (
            <div className="cite-aggregate__warn">
              ⚠ 空阶段：{agg.empty_stages.map((s) => STAGE_LABELS[s] || s).join("、")}
              （review/writing 阶段无勾选可能导致引用清单空缺，建议补勾选）
            </div>
          )}
          <div className="cite-aggregate__path">输出路径：{agg.selected_csv_path}</div>
        </div>
      )}

      <h4 className="cite-aggregate__subtitle">
        勾选明细（按 doi 分组预览 used_in）
      </h4>
      {Object.keys(grouped).length === 0 ? (
        <div className="cite-aggregate__empty">还没有勾选任何文献</div>
      ) : (
        <table className="cite-aggregate__table">
          <thead>
            <tr>
              <th>doi</th>
              <th>used_in（合并后）</th>
              <th>每个 stage 来源</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([doi, list]) => {
              const stages = list.map((r) => r.stage);
              return (
                <tr key={doi}>
                  <td>
                    <code>{doi}</code>
                  </td>
                  <td>
                    <code>{[...new Set(stages)].join(";")}</code>
                  </td>
                  <td>
                    {list.map((r) => (
                      <span key={r.stage} className="cite-stage-chip">
                        {STAGE_LABELS[r.stage] || r.stage}
                        {r.note && <span title={r.note}> · 注</span>}
                      </span>
                    ))}
                  </td>
                  <td>
                    {list.map((r) => (
                      <button
                        key={r.stage}
                        type="button"
                        onClick={() => handleDelete(r.doi, r.stage)}
                        disabled={busy}
                        className="cite-aggregate__del"
                      >
                        从 {STAGE_LABELS[r.stage] || r.stage} 删除
                      </button>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h4 className="cite-aggregate__subtitle" style={{ marginTop: 18 }}>
        已写入引用列表（citations/citations.csv · 共 {citations.length} 条）
      </h4>
      {citations.length === 0 ? (
        <div className="cite-aggregate__empty">
          引用列表为空。点「一键汇总」生成 selected.csv，或在写作时通过 AI 添加引用。
        </div>
      ) : (
        <table className="cite-aggregate__table">
          <thead>
            <tr>
              <th>doi</th>
              <th>label</th>
              <th>used_in</th>
              <th>note</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {citations.map((c) => (
              <tr key={c.doi}>
                <td>
                  <code>{c.doi}</code>
                </td>
                <td>{c.label || "—"}</td>
                <td>
                  <code>{c.used_in || "—"}</code>
                </td>
                <td title={c.note || ""}>
                  {c.note ? c.note.slice(0, 40) + (c.note.length > 40 ? "…" : "") : "—"}
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => handleDeleteCitation(c.doi)}
                    disabled={deletingCit === c.doi || busy}
                    className="cite-aggregate__del"
                    title="DELETE /api/citation/{project}/{doi}"
                  >
                    {deletingCit === c.doi ? "删除中…" : "删除引用"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
