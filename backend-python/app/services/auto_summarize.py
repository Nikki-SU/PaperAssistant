"""文献上传后自动总结链路（SPEC §七.2 · 阶段2 文献获取与处理自动化）。

链路：
  1. MinerU 成功解析 PDF → fulltext.md
  2. 自动切块（按 12000 字符上限，避免单次上下文爆）
  3. 助手 AI 逐块出"事实摘要"（首块带元信息抽取）
  4. 拼接 → 审阅 AI 5 轮事实核查
  5. 通过 → 追加写入项目 temp_knowledge.md（audited=true 通道）
  6. 未通过 → 硬丢弃，不写入

铁律：
  - SPEC §四.3：写入 temp_knowledge 必须 audited=true
  - SPEC §四.5：助手/审阅必须独立 API（由 ai_orchestrator 保证）
  - 所有产物只落 Markdown（本模块不写 JSON）
  - 任何失败都降级返回，不抛异常出业务边界
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..storage import append_role_memory_entry, write_text
from .ai_orchestrator import AIRole, get_orchestrator

logger = logging.getLogger(__name__)


# ============== 调参常量 ==============

#: 切块上限（字符）。MinerU 输出按段落切；助手单次输入控制在 ~12k 字符
MAX_CHUNK_CHARS = 12000

#: 每块目标摘要长度（字符），合并后整篇约 2-5k 字符
TARGET_SUMMARY_CHARS = 800

#: 首块额外提取的元信息字段
_META_FIELDS = ["标题", "第一作者", "发表年份", "期刊/会议", "DOI", "关键词", "研究领域"]


# ============== 返回结构 ==============


@dataclass
class AutoSummarizeResult:
    """文献自动总结结果。

    status 取值：
      - written:        已通过审阅并写入 temp_knowledge.md
      - dropped:        助手生成完毕但审阅 5 轮未通过，已丢弃
      - skipped:        fulltext.md 太短/为空，跳过
      - not_configured: 助手或审阅 AI 未配置，跳过
      - error:          MinerU 之外的链路错误（已降级）
    """
    status: str
    title: str = ""
    doi: str = ""
    summary_chars: int = 0
    audit_rounds: int = 0
    audit_log_path: str = ""
    temp_knowledge_path: str = ""
    message: str = ""
    chunks_total: int = 0
    error_code: str = ""
    meta: dict = field(default_factory=dict)


# ============== 提示词 ==============

_SUMMARIZE_SYSTEM = (
    "你是学术文献「事实摘要」助手。你的唯一任务是从给定的论文片段中提炼**原文已明确陈述的事实**，"
    "禁止任何推断、扩展、跨段落归纳、跨文献联想、价值判断。\n\n"
    "## 严格规则\n"
    "1. 只输出原文中**字面写到的**事实；原文没说的，绝对不写。\n"
    "2. 禁止使用「可能」「或许」「应该」「我们认为」「这表明」「说明」「意味着」等推断性词汇。\n"
    "3. 不写学术评价（如「这是首次」「具有重要意义」），除非原文逐字写了。\n"
    "4. 不补全省略的实验细节、不合并跨段结论。\n"
    "5. 引用具体数据时尽量带单位和上下文条件（如「在 AM 1.5G 标准光照下 PCE=24.3%」）。\n\n"
    "## 输出格式（Markdown）\n"
    "- 用无序列表 `-` 逐条列出事实，每条 1-3 行。\n"
    "- 涉及数值/化学式/参数时务必精确照抄。\n"
    "- 不写引言、不写总结、不写「以下是要点」。直接开始列表。\n"
)

_META_EXTRACT_SYSTEM = (
    "你是文献元信息抽取助手。从给定的论文片段（通常是首页/摘要附近）抽取以下字段：\n"
    f"{chr(10).join('- ' + f for f in _META_FIELDS)}\n\n"
    "## 严格规则\n"
    "1. 原文未写的字段输出空字符串，禁止猜测。\n"
    "2. 关键词若原文有 Keywords 行则照抄，否则留空。\n"
    "3. 输出格式严格为 Markdown 无序列表，每行 `- **字段名**：值`。\n"
    "4. 不要写其他任何文字。\n"
)


# ============== 辅助函数 ==============


def _split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """按段落优先切块；段落过长时按句号兜底切。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    buf: List[str] = []
    buf_len = 0

    # 优先按双换行（段落）切
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs:
        p_len = len(para)
        if p_len > max_chars:
            # 段落本身就超长 → 先冲刷 buf，再按句号兜底切
            if buf:
                chunks.append("\n\n".join(buf))
                buf, buf_len = [], 0
            sentences = re.split(r"(?<=[。.!?！？])\s+", para)
            sub_buf: List[str] = []
            sub_len = 0
            for s in sentences:
                if sub_len + len(s) > max_chars and sub_buf:
                    chunks.append(" ".join(sub_buf))
                    sub_buf, sub_len = [], 0
                sub_buf.append(s)
                sub_len += len(s)
            if sub_buf:
                chunks.append(" ".join(sub_buf))
            continue

        if buf_len + p_len > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf, buf_len = [], 0
        buf.append(para)
        buf_len += p_len

    if buf:
        chunks.append("\n\n".join(buf))

    return [c for c in chunks if c.strip()]


def _parse_meta_from_md_list(md: str) -> dict:
    """解析元信息抽取 AI 的输出（无序列表 → dict）。"""
    out: dict = {}
    for line in md.splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*(.+?)\*\*[：:]\s*(.*)$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if val:
                out[key] = val
    return out


# ============== 主入口 ==============


def auto_summarize_literature(
    project: str,
    doi: str,
    title: str,
    fulltext_md_path: Path,
) -> AutoSummarizeResult:
    """文献自动总结主入口（SPEC §七.2）。

    Args:
        project: 项目名（用于落 temp_knowledge.md 路径）
        doi: 文献 DOI（含 local: 占位）
        title: 文献标题（兜底显示用）
        fulltext_md_path: MinerU 解析出的 fulltext Markdown 路径

    Returns:
        AutoSummarizeResult: 携带状态与落盘路径，**不会抛异常**。
    """
    safe_title = (title or "未命名").strip()

    # ---- 1. 读 fulltext ----
    if not fulltext_md_path or not fulltext_md_path.exists():
        return AutoSummarizeResult(
            status="skipped", title=safe_title, doi=doi,
            message="fulltext Markdown 不存在，可能 MinerU 失败",
            error_code="no_fulltext",
        )
    try:
        fulltext = fulltext_md_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.exception("[auto_summarize] 读 fulltext 失败：%s", exc)
        return AutoSummarizeResult(
            status="error", title=safe_title, doi=doi,
            message=f"读 fulltext 失败：{exc}", error_code="read_failed",
        )
    if len(fulltext) < 200:
        return AutoSummarizeResult(
            status="skipped", title=safe_title, doi=doi,
            message=f"fulltext 太短（{len(fulltext)} 字符），跳过自动总结",
            error_code="too_short",
        )

    orchestrator = get_orchestrator()

    # 助手必须配置；审阅可选（不配则不写入临时知识，只返回 not_configured）
    if not orchestrator.is_configured(AIRole.ASSISTANT):
        return AutoSummarizeResult(
            status="not_configured", title=safe_title, doi=doi,
            message="助手 AI 未配置，跳过自动总结。请到「设置 → AI 接口位 → assistant」填写。",
            error_code="assistant_not_configured",
        )

    # ---- 2. 切块 ----
    chunks = _split_into_chunks(fulltext, MAX_CHUNK_CHARS)
    if not chunks:
        return AutoSummarizeResult(
            status="skipped", title=safe_title, doi=doi,
            message="切块为空，跳过", error_code="empty_chunks",
        )

    logger.info(
        "[auto_summarize] doi=%s title=%s fulltext_chars=%d chunks=%d",
        doi, safe_title[:60], len(fulltext), len(chunks),
    )

    # ---- 3. 首块抽取元信息（可选，失败不阻塞） ----
    meta: dict = {}
    try:
        meta_resp = orchestrator.chat(
            AIRole.ASSISTANT,
            messages=[
                {"role": "system", "content": _META_EXTRACT_SYSTEM},
                {"role": "user", "content": chunks[0][:6000]},
            ],
        )
        if meta_resp.success:
            meta = _parse_meta_from_md_list(meta_resp.output)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[auto_summarize] 元信息抽取失败（已忽略）：%s", exc)

    # ---- 4. 逐块出事实摘要 ----
    chunk_summaries: List[str] = []
    for idx, chunk in enumerate(chunks, 1):
        target_chars = max(400, TARGET_SUMMARY_CHARS // max(1, len(chunks) // 3 or 1))
        user_msg = (
            f"【文献】{safe_title}\n"
            f"【DOI】{doi}\n"
            f"【片段 {idx}/{len(chunks)}】\n\n"
            f"{chunk}\n\n"
            f"---\n请按系统提示给出该片段的事实摘要（目标约 {target_chars} 字符）。"
        )
        resp = orchestrator.chat(
            AIRole.ASSISTANT,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        if not resp.success:
            logger.warning(
                "[auto_summarize] 片段 %d/%d 总结失败（已降级跳过该片段）：%s",
                idx, len(chunks), resp.error,
            )
            continue
        chunk_summaries.append(f"### 片段 {idx}/{len(chunks)}\n\n{resp.output.strip()}")

    if not chunk_summaries:
        return AutoSummarizeResult(
            status="error", title=safe_title, doi=doi,
            message="所有片段总结调用均失败，已降级",
            error_code="all_chunks_failed",
            chunks_total=len(chunks),
        )

    merged_summary = "\n\n".join(chunk_summaries)

    # ---- 5. 审阅 AI 事实核查 ----
    # sources 传 chunk 本身（截断防超长），让审阅 AI 比对
    sources = [
        {"title": f"原文片段 {i+1}", "snippet": c[:4000]}
        for i, c in enumerate(chunks)
    ]
    verify = orchestrator.verify_with_auditor(
        content=merged_summary, sources=sources, project=project, max_rounds=5,
    )

    if verify.status == "not_configured":
        return AutoSummarizeResult(
            status="not_configured", title=safe_title, doi=doi,
            summary_chars=len(merged_summary), chunks_total=len(chunks),
            message="审阅 AI 未配置，自动总结结果未写入临时知识（避免污染）。",
            error_code="auditor_not_configured", meta=meta,
            audit_log_path=verify.log_path,
        )

    if verify.status != "verified":
        return AutoSummarizeResult(
            status="dropped", title=safe_title, doi=doi,
            summary_chars=len(merged_summary),
            audit_rounds=verify.rounds, audit_log_path=verify.log_path,
            chunks_total=len(chunks),
            message=f"审阅未通过（{verify.status}，{verify.rounds} 轮）：{verify.last_feedback[:200]}",
            error_code=f"audit_{verify.status}", meta=meta,
        )

    final_content = verify.final_content or merged_summary

    # ---- 6. 写入临时知识（audited=true 通道） ----
    from ..config import get_settings

    safe_project_name = re.sub(r'[\\/:*?"<>|]', "_", project).strip() or "_default"
    tk_path = (
        get_settings().projects_dir / safe_project_name / "temp_knowledge.md"
    )

    entry_title = f"[自动总结] {safe_title}"
    entry_meta = {
        "DOI": doi,
        "标题": safe_title,
        "来源": f"MinerU 解析 + 助手 AI 自动总结",
        "审阅状态": f"✅ 已通过（{verify.rounds} 轮）",
        "审阅日志": verify.log_path,
        "片段数": str(len(chunks)),
    }
    # 携带 AI 抽取的元信息
    for k in _META_FIELDS:
        if k in meta and k != "标题":  # 标题已有
            entry_meta[k] = meta[k]

    try:
        append_role_memory_entry(
            tk_path,
            role_label="临时知识",
            title=entry_title,
            body=final_content,
            meta=entry_meta,
        )
    except Exception as exc:
        logger.exception("[auto_summarize] 写入 temp_knowledge 失败：%s", exc)
        return AutoSummarizeResult(
            status="error", title=safe_title, doi=doi,
            summary_chars=len(final_content),
            audit_rounds=verify.rounds, audit_log_path=verify.log_path,
            chunks_total=len(chunks),
            message=f"审阅通过但写入失败：{exc}",
            error_code="write_failed", meta=meta,
        )

    return AutoSummarizeResult(
        status="written", title=safe_title, doi=doi,
        summary_chars=len(final_content),
        audit_rounds=verify.rounds, audit_log_path=verify.log_path,
        temp_knowledge_path=str(tk_path),
        chunks_total=len(chunks),
        message=f"已通过 {verify.rounds} 轮审阅，写入临时知识 ({len(final_content)} 字符)",
        meta=meta,
    )
