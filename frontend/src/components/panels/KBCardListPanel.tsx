/**
 * 知识库卡片列表（SPEC §六 / §8.2）。
 *
 * 当前阶段：占位 —— 知识库后端接口尚未独立暴露（B 计划补 /api/knowledge）。
 */
export function KBCardListPanel({ notify }: { notify: (s: string, k?: "ok" | "warn" | "error") => void }) {
  return (
    <div className="kb-list">
      <div className="muted-block">
        <strong>知识库卡片</strong>
        <p>
          目录：<code>data_root/knowledge/</code>（CSV + Markdown 双向同步）
        </p>
        <p className="muted">
          列表接口将于 B 计划接入。
        </p>
        <button
          className="primary-btn"
          onClick={() => notify("知识库接口待 B 计划接入", "warn")}
        >
          刷新
        </button>
      </div>
    </div>
  );
}
