/**
 * 知识库检索（SPEC §六）。
 *
 * 当前阶段：占位 + 接入计划说明。
 * - 知识库结构：data_root/knowledge/{md, cards/cards.csv}
 * - 真正接口待 B 计划补充（搜全文 + 按卡片字段过滤）
 */
import type { Project } from "../../api/client";

export function KBSearchPanel({ project, notify }: { project: Project | null; notify: (s: string, k?: "ok" | "warn" | "error") => void }) {
  return (
    <div className="kb-search">
      <div className="muted-block">
        <strong>知识库检索</strong>
        <p>
          目录：<code>data_root/knowledge/</code>。当前项目：<code>{project?.name ?? "未选"}</code>
        </p>
        <p className="muted">
          检索接口将于 B 计划接入（基于 BM25 / 卡片字段过滤 / 全文模糊匹配）。
        </p>
      </div>
      <div className="kb-search-form">
        <input
          className="search-input"
          placeholder="输入关键词（占位，未接入）"
          onKeyDown={(e) => {
            if (e.key === "Enter") notify("检索接口待 B 计划接入", "warn" as never);
          }}
        />
      </div>
    </div>
  );
}
