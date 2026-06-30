"""五阶段自动推进端点（SPEC §七）。

每个阶段提供 `POST /api/stages/{stage}/auto_advance`：前端按当前 step 触发，后端：
1. 读取项目上下文（临时知识 / 文献卡片 / 知识库 / 已勾选文献）
2. 根据 step 的 audit 类型走不同 AI 路径：
   - "建议"  → 助手 AI 单次输出 + suggestion 角标，不走核查
   - "核查"  → 助手 AI 输出 + verify_with_auditor 5 轮，未通过硬丢弃
3. 通过的「核查」结果自动写入 temp_knowledge.md（audited=true 通道）

铁律：
- SPEC §四.3：所有声称来源的内容必须 ≤5 轮核查通过才能入库
- SPEC §四.5：审阅 AI 独立于助手 AI（orchestrator 已保证）
- 任何 AI 失败都降级返回，前端展示 message + error_code

子阶段（writing）按 SPEC §7.3 三种子流程：theory / method / data
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services import (
    AIRole,
    append_role_memory_entry,  # noqa: F401  (备用)
    get_orchestrator,
)
from ..storage import (
    LIT_CSV_HEADERS,
    append_role_memory_entry as storage_append_role_memory_entry,
    ensure_csv,
    read_rows,
    read_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stages", tags=["stages_auto"])


_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip() or "_default"


def _temp_knowledge_md(project: str) -> Path:
    return get_settings().projects_dir / _safe(project) / "temp_knowledge.md"


def _list_literature_cards(project: str, limit: int = 50) -> list[dict]:
    """读项目可见文献卡片（当前实现：全局 cards.csv 全量取，按 last_modified 倒序）。"""
    p = get_settings().library_cards_csv
    ensure_csv(p, LIT_CSV_HEADERS)
    rows = read_rows(p)
    rows.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return rows[:limit]


# ============== Pydantic 模型 ==============


class StageAutoAdvanceBody(BaseModel):
    project: str = Field(..., min_length=1, description="项目名")
    step: int = Field(..., ge=1, le=8, description="阶段内步骤号")
    user_input: str = Field("", description="用户输入（如论文要求 / 检索关键词反馈等）")
    substage: Optional[str] = Field(
        None, description="writing 阶段子流程：theory / method / data / conclusion"
    )
    extra_sources: list[dict] = Field(
        default_factory=list,
        description="额外原文片段（每条 {title, snippet}），用于核查类步骤",
    )


class StageAutoAdvanceResult(BaseModel):
    stage: str
    step: int
    audit_kind: str  # suggestion | verified_summary | dropped | error | skipped
    content: str
    sources_used: list[dict] = Field(default_factory=list)
    audit_rounds: int = 0
    audit_log_path: str = ""
    written_to_temp_knowledge: bool = False
    temp_knowledge_path: str = ""
    error_code: str = ""
    message: str = ""


# ============== 通用助手 ==============


_SUGGEST_GUARD = (
    "你是论文写作助手。当前任务输出**纯建议性内容**，禁止声称来自任何具体文献/教材，"
    "所有推断必须以「建议」「可能」等措辞表达，且不得编造引用、DOI、作者、年份。"
    "如确实需要引用，仅使用用户在上下文中给出的文献。"
)

_VERIFIED_GUARD = (
    "你是论文写作助手。当前任务必须**严格基于给定原文**生成总结/归纳，"
    "禁止任何原文未明确写出的推断、补全、跨段联想。所有数据/引用必须可在原文中字面找到。"
    "输出会进入审阅 AI 5 轮事实核查循环，未通过将被丢弃。"
)


def _call_assistant(messages: list[dict]) -> tuple[bool, str, str]:
    """返回 (success, content, error_code)。"""
    orch = get_orchestrator()
    if not orch.is_configured(AIRole.ASSISTANT):
        return False, "", "assistant_not_configured"
    resp = orch.chat(AIRole.ASSISTANT, messages=messages)
    if not resp.success:
        return False, resp.error, resp.error_code or "unknown"
    return True, resp.output.strip(), ""


def _run_suggestion(
    *, project: str, stage: str, step: int, prompt: str
) -> StageAutoAdvanceResult:
    """建议类输出：不走核查。"""
    ok, content, err = _call_assistant(
        messages=[
            {"role": "system", "content": _SUGGEST_GUARD},
            {"role": "user", "content": prompt},
        ]
    )
    if not ok:
        return StageAutoAdvanceResult(
            stage=stage, step=step, audit_kind="error",
            content="", error_code=err,
            message=f"建议生成失败：{content[:200] if content else err}",
        )

    return StageAutoAdvanceResult(
        stage=stage, step=step, audit_kind="suggestion",
        content=f"💡 **建议（未经事实核查）**\n\n{content}",
        message="建议类输出（不走核查，不入临时知识）",
    )


def _run_verified_summary(
    *,
    project: str, stage: str, step: int,
    prompt: str, sources: list[dict], entry_title: str,
) -> StageAutoAdvanceResult:
    """核查类输出：助手生成 → 5 轮核查 → 通过则写入 temp_knowledge.md。"""
    ok, content, err = _call_assistant(
        messages=[
            {"role": "system", "content": _VERIFIED_GUARD},
            {"role": "user", "content": prompt},
        ]
    )
    if not ok:
        return StageAutoAdvanceResult(
            stage=stage, step=step, audit_kind="error",
            content="", error_code=err, sources_used=sources,
            message=f"助手生成失败：{content[:200] if content else err}",
        )

    orch = get_orchestrator()
    verify = orch.verify_with_auditor(
        content=content, sources=sources, project=project, max_rounds=5,
    )

    if verify.status == "not_configured":
        return StageAutoAdvanceResult(
            stage=stage, step=step, audit_kind="error",
            content=content, error_code="auditor_not_configured",
            sources_used=sources, audit_log_path=verify.log_path,
            message="审阅 AI 未配置，本次「核查类」输出未入临时知识。请到设置 → AI 接口位 → auditor 填写。",
        )

    if verify.status != "verified":
        return StageAutoAdvanceResult(
            stage=stage, step=step, audit_kind="dropped",
            content="", error_code=f"audit_{verify.status}",
            audit_rounds=verify.rounds, audit_log_path=verify.log_path,
            sources_used=sources,
            message=f"事实核查 {verify.rounds} 轮未通过，已硬丢弃：{verify.last_feedback[:200]}",
        )

    final = verify.final_content or content
    tk_path = _temp_knowledge_md(project)
    storage_append_role_memory_entry(
        tk_path,
        role_label="临时知识",
        title=entry_title,
        body=final,
        meta={
            "阶段": stage,
            "步骤": str(step),
            "审阅状态": f"✅ 已通过（{verify.rounds} 轮）",
            "审阅日志": verify.log_path,
            "来源数": str(len(sources)),
        },
    )

    return StageAutoAdvanceResult(
        stage=stage, step=step, audit_kind="verified_summary",
        content=final, sources_used=sources,
        audit_rounds=verify.rounds, audit_log_path=verify.log_path,
        written_to_temp_knowledge=True, temp_knowledge_path=str(tk_path),
        message=f"事实核查通过（{verify.rounds} 轮），已写入 temp_knowledge.md",
    )


# ============== 阶段一：选题 ==============


def _stage_topic(body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    project = body.project
    step = body.step
    tk_md = read_text(_temp_knowledge_md(project)) if _temp_knowledge_md(project).exists() else ""
    cards = _list_literature_cards(project, limit=30)
    lit_brief = "\n".join(
        f"- {c.get('title','(无题)')}（{c.get('first_author','')}, {c.get('doi','')}）"
        for c in cards[:20]
    ) or "（暂无文献卡片）"

    if step == 1:
        return StageAutoAdvanceResult(
            stage="topic", step=1, audit_kind="skipped",
            content="本步骤为用户输入：请在 user_input 中填写论文要求与课程/学科。",
            message="步骤 1 由用户输入，AI 不动作",
        )

    if step == 2:
        prompt = (
            f"用户的论文要求：\n{body.user_input or '（未提供，请提示用户先填写）'}\n\n"
            f"当前文献库已有卡片：\n{lit_brief}\n\n"
            "请：\n"
            "1. 推断学科一级分类与可能的二级方向（仅基于用户描述，标注「建议」）\n"
            "2. 列出已有文献中与该方向相关的卡片（不强行拼凑）\n"
            "3. 给出 5-8 个推荐检索关键词（中英文混合）\n"
            "禁止编造任何具体文献名/DOI。"
        )
        return _run_suggestion(project=project, stage="topic", step=2, prompt=prompt)

    if step == 3:
        # 由 /api/literature/upload?project=X 上传后自动 auto_summarize 触发
        return StageAutoAdvanceResult(
            stage="topic", step=3, audit_kind="skipped",
            content="本步骤由用户上传课本/教材触发（通过 /api/literature/upload?project=X 自动总结链路）。",
            message="此步骤通过文献上传链路自动推进，无需直接调用 auto_advance",
        )

    if step == 4:
        prompt = (
            f"用户的论文要求：\n{body.user_input or '（未提供）'}\n\n"
            f"当前临时知识（已通过事实核查的教材/文献摘要）：\n{tk_md[:6000] or '（暂无）'}\n\n"
            f"文献库卡片摘要：\n{lit_brief}\n\n"
            "请基于以上信息推荐 3-5 个**具体可行的选题方向**：\n"
            "- 每个选题写 1 段（方向描述 + 切入点 + 与已有素材的契合点）\n"
            "- 末尾给出该选题再补充的检索关键词\n"
            "- 全部标注「💡 建议」，不要编造具体引用"
        )
        return _run_suggestion(project=project, stage="topic", step=4, prompt=prompt)

    if step == 5:
        return StageAutoAdvanceResult(
            stage="topic", step=5, audit_kind="skipped",
            content="本步骤为用户自行检索，AI 不动作。",
            message="步骤 5 由用户操作",
        )

    if step == 6:
        return StageAutoAdvanceResult(
            stage="topic", step=6, audit_kind="skipped",
            content="本步骤由用户上传文献触发（通过 /api/literature/upload?project=X 自动总结链路）。",
            message="此步骤通过文献上传链路自动推进",
        )

    if step == 7:
        prompt = (
            f"基于以下材料给出 2-3 个**具体的论文选题**（带主标题 + 副标题/聚焦点）：\n\n"
            f"用户论文要求：\n{body.user_input or '（未提供）'}\n\n"
            f"临时知识：\n{tk_md[:8000] or '（暂无）'}\n\n"
            f"文献库：\n{lit_brief}\n\n"
            "每个选题：\n- 主标题\n- 副标题/聚焦点\n- 一句话写为什么这个题可做\n"
            "- 列举 2-3 篇最相关的已有文献（从上方文献库中精确挑选，不编造）\n"
            "全部标注「💡 建议」。"
        )
        return _run_suggestion(project=project, stage="topic", step=7, prompt=prompt)

    if step == 8:
        return StageAutoAdvanceResult(
            stage="topic", step=8, audit_kind="skipped",
            content="本步骤由用户选定选题后调 PATCH /api/project/{old}/rename 更新项目名。",
            message="步骤 8 由用户操作",
        )

    raise HTTPException(status_code=400, detail=f"topic 阶段无步骤 {step}")


# ============== 阶段二：文献综述 ==============


def _stage_review(body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    project = body.project
    step = body.step
    tk_md = read_text(_temp_knowledge_md(project)) if _temp_knowledge_md(project).exists() else ""
    cards = _list_literature_cards(project, limit=50)

    if step == 1:
        prompt = (
            f"用户的论文要求 / 当前选题：\n{body.user_input or '（未提供）'}\n\n"
            "请推荐：\n"
            "1. 该选题应使用的英文 + 中文检索关键词（各 5-8 个）\n"
            "2. 推荐 3-5 个检索平台（Web of Science / Scopus / Google Scholar / CNKI / arXiv 等，"
            "按该学科适配度排序）\n"
            "3. 说明每个关键词适合什么类型的文献（综述/方法/数据集）\n"
            "全部标注「💡 建议」。"
        )
        return _run_suggestion(project=project, stage="review", step=1, prompt=prompt)

    if step == 2:
        return StageAutoAdvanceResult(
            stage="review", step=2, audit_kind="skipped",
            content="本步骤为用户检索并上传文献（可监控目录自动转）。",
            message="步骤 2 由用户操作或 file_watcher 触发",
        )

    if step == 3:
        # 按话题归纳：将已上传的文献摘要（来自 temp_knowledge）做归纳，需核查
        if not tk_md or len(tk_md) < 200:
            return StageAutoAdvanceResult(
                stage="review", step=3, audit_kind="skipped",
                content="临时知识为空，请先上传文献触发自动总结。",
                message="临时知识不足，无法归纳",
            )
        sources = [{"title": "项目临时知识汇总", "snippet": tk_md[:8000]}]
        # 额外可挂用户传入的 extra_sources
        sources.extend(body.extra_sources)
        prompt = (
            f"以下是项目已上传文献的事实摘要汇总：\n\n{tk_md[:10000]}\n\n"
            "请按 **3-5 个话题** 归纳这些文献：\n"
            "- 每个话题：标题 + 涉及的文献（必须从上方汇总中精确挑出，不编造）\n"
            "- 每个话题写一段 200-400 字的事实归纳（只用上方原文已陈述的内容）\n"
            "- 严格附 DOI 来源引用（用 [@doi:xxx] 格式）\n"
            "禁止任何推断、价值评价、未在原文中出现的连接。"
        )
        return _run_verified_summary(
            project=project, stage="review", step=3,
            prompt=prompt, sources=sources,
            entry_title="[综述阶段] 文献按话题归纳",
        )

    if step in (4, 5):
        return StageAutoAdvanceResult(
            stage="review", step=step, audit_kind="skipped",
            content="本步骤由前端交互式勾选实现（POST /api/selections）。",
            message=f"步骤 {step} 由用户勾选，AI 不动作",
        )

    raise HTTPException(status_code=400, detail=f"review 阶段无步骤 {step}")


# ============== 阶段三：正文撰写 ==============


def _stage_writing(body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    project = body.project
    step = body.step
    substage = (body.substage or "").strip().lower()
    if substage not in ("theory", "method", "data", "conclusion"):
        raise HTTPException(
            status_code=400,
            detail="writing 阶段必须指定 substage ∈ {theory, method, data, conclusion}",
        )

    tk_md = read_text(_temp_knowledge_md(project)) if _temp_knowledge_md(project).exists() else ""
    cards_brief = "\n".join(
        f"- {c.get('title','(无题)')}（DOI: {c.get('doi','')}）"
        for c in _list_literature_cards(project, limit=30)
    ) or "（暂无文献卡片）"

    # ---- 3.1 理论建设 ----
    if substage == "theory" and step == 1:
        prompt = (
            f"用户当前选题：{body.user_input or '（未提供）'}\n"
            f"已有文献库：\n{cards_brief}\n\n"
            "请推荐 3-5 篇**应当再查的理论文献方向**：\n"
            "- 每条：研究领域 + 具体关键词 + 推荐来源（期刊/会议/综述/经典教材）\n"
            "- 不要给具体文献名/DOI（避免编造），只给检索方向\n"
            "全部标注「💡 建议」。"
        )
        return _run_suggestion(project=project, stage="writing.theory", step=1, prompt=prompt)

    if substage == "theory" and step == 3:
        # 上传理论文献后总结入临时知识 → 由 auto_summarize 链路完成
        return StageAutoAdvanceResult(
            stage="writing.theory", step=3, audit_kind="skipped",
            content="本步骤由 /api/literature/upload?project=X 触发自动总结链路。",
            message="通过文献上传自动推进",
        )

    # ---- 3.2 方法论 ----
    if substage == "method" and step in (1, 2):
        if not tk_md or len(tk_md) < 200:
            return StageAutoAdvanceResult(
                stage="writing.method", step=step, audit_kind="skipped",
                content="临时知识不足，请先上传方法论相关文献或教材。",
                message="临时知识为空",
            )
        sources = [{"title": "项目临时知识汇总", "snippet": tk_md[:8000]}]
        sources.extend(body.extra_sources)
        topic = "文献" if step == 1 else "方法论教材"
        prompt = (
            f"以下是项目临时知识中关于 {topic} 的内容：\n\n{tk_md[:10000]}\n\n"
            "请按方法分类归纳：\n"
            "- 每个方法：名称 + 来源（必须附 DOI 或教材引用，禁止编造）+ 适用场景\n"
            "- 严格只用上方已经过事实核查的内容\n"
            "- 末尾标注每条结论的 [@doi:xxx] 引用位置"
        )
        return _run_verified_summary(
            project=project, stage="writing.method", step=step,
            prompt=prompt, sources=sources,
            entry_title=f"[方法论] 从{topic}归纳",
        )

    if substage == "method" and step == 3:
        prompt = (
            f"基于以下临时知识中的方法归纳：\n\n{tk_md[:8000]}\n\n"
            "请给出**方法选择的综合建议**：\n"
            "- 推荐 2-3 个候选方法\n- 每个方法写优劣对比\n- 给出最终倾向 + 理由\n"
            "全部标注「💡 建议」，不要编造任何上方未出现的方法/文献。"
        )
        return _run_suggestion(project=project, stage="writing.method", step=3, prompt=prompt)

    if substage == "method" and step == 4:
        if not tk_md or len(tk_md) < 200:
            return StageAutoAdvanceResult(
                stage="writing.method", step=4, audit_kind="skipped",
                content="临时知识不足，无法提取详细流程。",
                message="临时知识为空",
            )
        confirmed = (body.user_input or "").strip()
        if not confirmed:
            return StageAutoAdvanceResult(
                stage="writing.method", step=4, audit_kind="skipped",
                content="请在 user_input 中说明用户确认的方法（例如：'确认使用 DFT + 实验对照'）。",
                message="缺少用户确认的方法",
            )
        sources = [{"title": "项目临时知识汇总", "snippet": tk_md[:8000]}]
        sources.extend(body.extra_sources)
        prompt = (
            f"用户确认采用：{confirmed}\n\n"
            f"临时知识：\n\n{tk_md[:10000]}\n\n"
            "请基于上方原文提取该方法的**详细流程**：\n"
            "- 步骤 1, 2, 3...（按原文顺序）\n- 每步附原文来源 [@doi:xxx]\n"
            "- 禁止补全任何原文未写到的步骤细节"
        )
        return _run_verified_summary(
            project=project, stage="writing.method", step=4,
            prompt=prompt, sources=sources,
            entry_title=f"[方法论] {confirmed} 详细流程",
        )

    # ---- 3.3 数据 ----
    if substage == "data" and step == 2:
        if not body.user_input:
            return StageAutoAdvanceResult(
                stage="writing.data", step=2, audit_kind="skipped",
                content="请在 user_input 中填入已上传的数据/分析结果文本（或在 extra_sources 传 snippet）。",
                message="无数据内容",
            )
        prompt = (
            f"用户上传的数据/分析结果：\n\n{body.user_input[:8000]}\n\n"
            "请给出**结论方向参考**（不替用户下定论）：\n"
            "- 数据中显示的趋势\n- 可能的解释方向（标注「建议」）\n"
            "- 还需补充的对照实验或额外分析\n"
            "全部标注「💡 建议」，最终结论由人类自写。"
        )
        return _run_suggestion(project=project, stage="writing.data", step=2, prompt=prompt)

    # ---- 3.4 结论 ----
    if substage == "conclusion":
        return StageAutoAdvanceResult(
            stage="writing.conclusion", step=step, audit_kind="skipped",
            content="SPEC §7.3.4：最终结论由人类自写。AI 仅在用户主动调 /api/ai/chat 时提供方向参考。",
            message="结论由人类自写",
        )

    raise HTTPException(
        status_code=400,
        detail=f"writing 阶段无 substage={substage} step={step} 的自动推进逻辑",
    )


# ============== 阶段四：引用 ==============


def _stage_citation(body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    return StageAutoAdvanceResult(
        stage="citation", step=body.step, audit_kind="skipped",
        content=(
            "引用阶段不走 AI 自动推进：\n"
            "- 步骤 1-2：由 GET /api/selections 汇总用户勾选\n"
            "- 步骤 3-5：由 /api/citation/format + /api/citation/render 完成（CSL 引擎）"
        ),
        message="引用阶段由 selections + citation 路由处理，无 AI 任务",
    )


# ============== 阶段五：排版 ==============


def _stage_typesetting(body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    step = body.step
    if step == 2:
        if not body.user_input:
            return StageAutoAdvanceResult(
                stage="typesetting", step=2, audit_kind="skipped",
                content="请在 user_input 中粘贴用户给定的格式要求。",
                message="缺少格式要求",
            )
        prompt = (
            f"用户给定的格式要求：\n\n{body.user_input}\n\n"
            "请生成一个 **LaTeX 模板骨架**：\n"
            "- 严格按用户要求设置 documentclass、字号、间距、页边距、引用样式\n"
            "- 标题/作者/正文/参考文献结构齐全\n- 给出 ```latex 代码块\n"
            "- 不引入未在用户要求中提到的包/样式（避免编造）"
        )
        # 模板生成属于建议类（用户会迭代反馈）
        return _run_suggestion(project=body.project, stage="typesetting", step=2, prompt=prompt)

    return StageAutoAdvanceResult(
        stage="typesetting", step=step, audit_kind="skipped",
        content=(
            "排版阶段：\n"
            "- 步骤 1：用户粘贴格式要求\n"
            "- 步骤 2：调本端点 auto_advance(step=2) 生成模板\n"
            "- 步骤 3：用户反馈→迭代（继续调 /api/ai/chat 或本端点）\n"
            "- 步骤 4：确认模板后 → /api/typesetting/compile 一键编译 PDF"
        ),
        message="其他步骤由用户操作或专用路由处理",
    )


# ============== 路由 ==============


_DISPATCH = {
    "topic": _stage_topic,
    "review": _stage_review,
    "writing": _stage_writing,
    "citation": _stage_citation,
    "typesetting": _stage_typesetting,
}


@router.post("/{stage}/auto_advance", response_model=StageAutoAdvanceResult)
def stage_auto_advance(stage: str, body: StageAutoAdvanceBody) -> StageAutoAdvanceResult:
    """五阶段自动推进端点。

    根据 stage + step（+ writing 阶段的 substage）路由到不同 AI 任务。
    建议类不走核查；核查类走 5 轮 verify，未通过硬丢弃不入库。
    """
    handler = _DISPATCH.get(stage)
    if handler is None:
        raise HTTPException(
            status_code=400,
            detail=f"未知阶段 {stage}，应为 topic/review/writing/citation/typesetting",
        )
    try:
        return handler(body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[stages_auto] %s step=%d 未捕获异常：%s", stage, body.step, exc)
        return StageAutoAdvanceResult(
            stage=stage, step=body.step, audit_kind="error",
            content="", error_code="exception",
            message=f"未捕获异常（已降级）：{exc}",
        )
