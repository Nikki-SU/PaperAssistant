"""AI 对话 API（SPEC §4.3 / §4.5 / §六）。

端点：
- POST /api/ai/chat   通用聊天端点：
                       · task_type=free_chat → 助手 AI 自判（结构化输出 JSON）：
                         · category=factual_summary → 用 AI 声称的 claimed_sources 自动 verify_with_auditor
                         · category=suggestion       → 标 audit_status=suggestion，content 前置「【建议】」
                         · category=free             → 标 audit_status=user
                         （SPEC §4.3 触发标准：AI 输出**声称**来源就自动核查，无需用户预先指定 task_type）
                       · task_type ∈ 6 类必须核查 → 自动调 verify_with_auditor（系统/阶段触发用）
                       · task_type ∈ 4 类建议      → 标 audit_status=suggestion
- POST /api/ai/verify SPEC §4.3 事实核查 5 轮循环（手动兜底）
- GET  /api/ai/status 3 个角色的就绪状态（mineru 单独有上传端点）

铁律：失败必须降级，返回结构化错误而非 5xx。
铁律 §4.3：6 类必须核查任务在缺 sources 时直接 400；5 轮失败时硬丢弃 final_content。
铁律（自判）：助手 AI 自判 JSON 解析失败时，回退为 free + 警告日志，绝不当 factual_summary 误入库。
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..services import (
    AIRole,
    append_assistant_memory,
    get_orchestrator,
    load_role_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------- SPEC §4.3 任务类型 ----------------

# 必须自动事实核查（6 类）
MUST_AUDIT_TASKS = frozenset([
    "summarize_literature",      # 总结已上传文献
    "extract_textbook",          # 从课本/教材提炼知识点
    "extract_methodology",       # 从方法论教材提取操作流程
    "compare_literature",        # 从已读材料归纳对比
    "regen_literature_card",     # 文献卡片重新生成
    "generate_knowledge_card",   # 知识库卡片生成
])

# 不强制核查、需标注「建议」（4 类）
SUGGESTION_TASKS = frozenset([
    "recommend_topic",       # 推荐选题方向
    "recommend_keywords",    # 推荐检索关键词/平台
    "suggest_method",        # 综合研究方法建议
    "suggest_framework",     # 框架组织建议
])

# 自由对话（不标注，由用户自行判断）
FREE_TASKS = frozenset([
    "free_chat",
    "other",
])

ALL_TASKS = MUST_AUDIT_TASKS | SUGGESTION_TASKS | FREE_TASKS

TaskType = Literal[
    "summarize_literature",
    "extract_textbook",
    "extract_methodology",
    "compare_literature",
    "regen_literature_card",
    "generate_knowledge_card",
    "recommend_topic",
    "recommend_keywords",
    "suggest_method",
    "suggest_framework",
    "free_chat",
    "other",
]


# 各任务的人类可读名（用于 prompt 和日志）
TASK_LABELS: dict[str, str] = {
    "summarize_literature":    "总结已上传文献",
    "extract_textbook":        "从课本/教材提炼知识点",
    "extract_methodology":     "从方法论教材提取操作流程",
    "compare_literature":      "从已读材料归纳对比",
    "regen_literature_card":   "文献卡片重新生成",
    "generate_knowledge_card": "知识库卡片生成",
    "recommend_topic":         "推荐选题方向",
    "recommend_keywords":      "推荐检索关键词/平台",
    "suggest_method":          "综合研究方法建议",
    "suggest_framework":       "框架组织建议",
    "free_chat":               "自由对话",
    "other":                   "其他",
}


# ---------------- 模型 ----------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class SourceItem(BaseModel):
    """事实核查 / chat 任务的原文片段。"""
    title: str = ""
    snippet: str = ""


class ChatRequest(BaseModel):
    role: Literal["assistant", "auditor", "secretary"] = Field(
        "assistant", description="目标接口位"
    )
    messages: list[ChatMessage] = Field(..., min_length=1)
    project: Optional[str] = None
    stage: Optional[str] = None
    task_type: TaskType = Field("free_chat", description="SPEC §4.3 任务类型")
    sources: list[SourceItem] = Field(
        default_factory=list,
        description="原文片段；当 task_type ∈ 必须核查 6 类时必填",
    )
    extra: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_sources_required(self):
        if self.task_type in MUST_AUDIT_TASKS and not self.sources:
            raise ValueError(
                f"task_type={self.task_type} 属于 SPEC §4.3 必须核查的 6 类，"
                f"请同时传入 sources（至少 1 条原文片段）"
            )
        return self


class ChatResponse(BaseModel):
    success: bool
    role: str
    effective_role: str
    output: str
    # SPEC §4.3 审阅状态：
    # - verified:    必须类，5 轮内通过事实核查（output 已是 final_content）
    # - failed:      必须类，5 轮全失败，已硬丢弃（output="" 不入库）
    # - not_configured: 必须类，auditor 未配置（output 暂留但提示用户配 auditor）
    # - suggestion:  4 类推断任务，已加「建议」前缀
    # - user:        自由对话，由用户自行判断
    # - error:       AI 调用失败
    audit_status: Literal["verified", "failed", "not_configured", "suggestion", "user", "error"] = "user"
    audit_rounds: int = 0
    audit_feedback: str = ""
    audit_log_path: str = ""
    audit_dropped: bool = False  # 必须类 5 轮失败时 = true（output 已置空）
    error: str = ""
    error_code: str = ""
    project: Optional[str] = None
    stage: Optional[str] = None
    task_type: str = "free_chat"
    task_label: str = ""
    # commit δ：free_chat 自判路径专用（其它路径默认 None）
    self_judge_category: Optional[str] = None  # factual_summary | suggestion | free
    claimed_sources: list[str] = []  # AI 声称的来源（DOI/教材名/章节，已扁平化为字符串）


class RoleStatus(BaseModel):
    role: str
    configured: bool
    has_endpoint: bool
    has_key: bool
    has_model: bool
    endpoint: str = ""
    model: str = ""


# ---------------- 端点：状态 ----------------


@router.get("/status")
def chat_status() -> dict:
    """返回 3 个 AI 角色（assistant/auditor/secretary）的就绪状态。"""
    items: list[RoleStatus] = []
    for role in (AIRole.ASSISTANT, AIRole.AUDITOR, AIRole.SECRETARY):
        cfg = load_role_config(role.value)
        items.append(
            RoleStatus(
                role=role.value,
                configured=bool(cfg.api_key and cfg.endpoint and cfg.model),
                has_endpoint=bool(cfg.endpoint),
                has_key=bool(cfg.api_key),
                has_model=bool(cfg.model),
                endpoint=cfg.endpoint,
                model=cfg.model,
            )
        )
    return {"items": [it.model_dump() for it in items]}


@router.get("/task_types")
def list_task_types() -> dict:
    """SPEC §4.3：列出所有任务类型及其核查策略，给前端 selector 用。"""
    items = []
    for k in MUST_AUDIT_TASKS:
        items.append({"task_type": k, "label": TASK_LABELS[k], "policy": "must_audit",
                      "requires_sources": True})
    for k in SUGGESTION_TASKS:
        items.append({"task_type": k, "label": TASK_LABELS[k], "policy": "suggestion",
                      "requires_sources": False})
    for k in FREE_TASKS:
        items.append({"task_type": k, "label": TASK_LABELS[k], "policy": "free",
                      "requires_sources": False})
    return {"items": items}


# ---------------- 端点：chat ----------------


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    try:
        role = AIRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效 role: {body.role}")

    orch = get_orchestrator()
    orch.refresh()

    msgs = [m.model_dump() for m in body.messages]

    # SPEC §4.3 自判模式：free_chat 默认走 AI 自判（让 AI 自己判 category）
    # 由 _handle_free_chat_self_judge 处理整条链路（包括可能的自动 verify）
    if body.task_type == "free_chat" and role == AIRole.ASSISTANT:
        return _handle_free_chat_self_judge(orch, msgs, body)

    # 对 4 类建议任务，往 system 前置一句强约束，让助手必带「建议」前缀
    if body.task_type in SUGGESTION_TASKS:
        msgs = _prepend_suggestion_guard(msgs)
    # 对 6 类必须核查任务，往 system 前置一句强约束：必须基于 sources、不得编造来源
    elif body.task_type in MUST_AUDIT_TASKS:
        msgs = _prepend_must_audit_guard(msgs, body.sources)

    result = orch.chat(role, msgs, extra=body.extra)

    # 默认状态机
    audit_status: Literal["verified", "failed", "not_configured", "suggestion", "user", "error"] = "user"
    audit_rounds = 0
    audit_feedback = ""
    audit_log_path = ""
    audit_dropped = False
    final_output = result.output

    if not result.success:
        audit_status = "error"
    elif body.task_type in MUST_AUDIT_TASKS:
        # SPEC §4.3：必须类 → 自动跑 5 轮事实核查
        verify = orch.verify_with_auditor(
            content=result.output,
            sources=[s.model_dump() for s in body.sources],
            project=body.project,
        )
        audit_rounds = verify.rounds
        audit_feedback = verify.last_feedback
        audit_log_path = verify.log_path
        if verify.status == "verified":
            audit_status = "verified"
            final_output = verify.final_content
        elif verify.status == "failed":
            # 5 轮失败硬丢弃：output 清空 + dropped=true
            audit_status = "failed"
            final_output = ""
            audit_dropped = True
        elif verify.status == "not_configured":
            audit_status = "not_configured"
            # 内容暂留，但客户端应提示「请配置 auditor 再正式入库」
        else:  # "error"
            audit_status = "error"
    elif body.task_type in SUGGESTION_TASKS:
        audit_status = "suggestion"
        # 把「建议」前缀强行拼上，防助手忘加
        if final_output and not final_output.lstrip().startswith(("建议", "【建议", "Suggestion", "[建议")):
            final_output = "【建议】\n\n" + final_output
    else:
        audit_status = "user"

    # SPEC §8.3：助手 AI 的所有输出 → assistant.md
    # 只有真实有内容（非硬丢弃 + 非 error 失败）才记录；硬丢弃情况也记一行轨迹
    try:
        if body.project:
            short_user = ""
            for m in reversed(msgs):
                if m.get("role") == "user":
                    short_user = m.get("content", "")
                    break
            append_assistant_memory(
                body.project,
                stage=body.stage or "",
                task_type=body.task_type,
                user_message=short_user,
                assistant_output=final_output if final_output else f"_(已丢弃) {audit_feedback or ''}_",
                audit_status=audit_status,
                rounds=audit_rounds,
                success=result.success,
                error=result.error,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("append_assistant_memory failed: %s", e)

    return ChatResponse(
        success=result.success,
        role=body.role,
        effective_role=result.role.value,
        output=final_output,
        audit_status=audit_status,
        audit_rounds=audit_rounds,
        audit_feedback=audit_feedback,
        audit_log_path=audit_log_path,
        audit_dropped=audit_dropped,
        error=result.error,
        error_code=result.error_code,
        project=body.project,
        stage=body.stage,
        task_type=body.task_type,
        task_label=TASK_LABELS.get(body.task_type, body.task_type),
    )


# ---------------- 端点：verify ----------------


class VerifyRequest(BaseModel):
    content: str = Field(..., min_length=1, description="助手 AI 已生成的待审内容")
    sources: list[SourceItem] = Field(default_factory=list, description="原文引用片段")
    project: Optional[str] = None
    max_rounds: int = Field(5, ge=1, le=5)


class VerifyResponse(BaseModel):
    status: Literal["verified", "failed", "not_configured", "error"]
    final_content: str = ""
    rounds: int = 0
    last_feedback: str = ""
    log_path: str = ""
    audit_status: Literal["verified", "suggestion", "user", "error"] = "suggestion"


@router.post("/verify", response_model=VerifyResponse)
def verify(body: VerifyRequest) -> VerifyResponse:
    """SPEC §4.3：手动核查端点。chat 端点的必须类已自动调它，此端点保留兜底使用。"""
    orch = get_orchestrator()
    orch.refresh()
    result = orch.verify_with_auditor(
        body.content,
        [s.model_dump() for s in body.sources],
        project=body.project,
        max_rounds=body.max_rounds,
    )
    audit_status_map = {
        "verified": "verified",
        "failed": "error",
        "not_configured": "suggestion",
        "error": "error",
    }
    return VerifyResponse(
        status=result.status,
        final_content=result.final_content,
        rounds=result.rounds,
        last_feedback=result.last_feedback,
        log_path=result.log_path,
        audit_status=audit_status_map.get(result.status, "suggestion"),  # type: ignore
    )


# ---------------- prompt 守护 ----------------


_MUST_AUDIT_GUARD = """【系统约束 · SPEC §4.2/§4.3 — 不可违反】
你的输出将被「审阅 AI」逐句比对原文核查。请严格遵守：
1. 仅基于「原文片段」生成内容。任何超出原文的事实陈述都会被退回。
2. 不得引入原文中不存在的实质性新增信息（细微改写不算新增）。
3. 不得自行编造文献、数据、年份、作者、机构等。
4. 若原文不足以回答用户问题：明确告知缺什么、需要补充什么材料，不要发挥。
5. 不要在输出中带「建议」「我认为」等推断措辞——这是事实核查任务，不是建议任务。
"""

_SUGGESTION_GUARD = """【系统约束 · SPEC §4.3 — 推断类任务】
本任务属于「建议/推断」类，不强制事实核查。请遵守：
1. 输出必须以「【建议】」开头，明确这是推断性意见而非来自具体文献。
2. 不要捏造具体文献、DOI、年份；如要举例只说方向类别。
3. 用户的最终判断需要自己做，你只给参考方向。
"""


# SPEC §4.3 自判模式（free_chat 默认走它）：让助手 AI 输出结构化 JSON 自报核查需求。
# 触发标准（SPEC 原文）：「如果 AI 输出的内容声称来自某篇文献/某本教材的某部分，
# 就必须经过事实核查」→ 由 AI 自己在 category 字段里声明，而不是由用户在前端选 task_type。
_SELF_JUDGE_GUARD = """【系统约束 · SPEC §4.3 自判模式 — 必须严格遵守】
你必须用且仅用一个 JSON 对象回答，不要任何前后缀、解释或 Markdown 代码块包裹。格式：
{
  "content": "你要给用户看的回答正文，可以是 Markdown",
  "category": "factual_summary" | "suggestion" | "free",
  "claimed_sources": [{"title": "文献/教材名/章节", "snippet": "你引用或转述的原文片段（必填）"}]
}

category 的判定标准（你自己来判，不是用户选）：
- factual_summary: 你的 content 声称「来自某篇文献/某本教材的某部分」「该论文表明」「教材中提到」「实验数据显示」等任何**具体来源引用**。此时必须在 claimed_sources 里给出你实际引用的原文片段，每条 snippet 至少 30 字。无原文片段就严禁选这一类。
- suggestion: 你的 content 是推断/建议/方向性意见（如「我建议你考虑 XX 角度」「这个方向值得探索」），未声称具体来源。
- free: 闲聊、术语定义、用法解释、操作指引，无关任何文献来源。

铁律：
1. 严禁在 content 里写「根据 XX 文献…」但 claimed_sources 留空——这会被审阅 AI 当场打回。
2. 严禁编造 claimed_sources（DOI、作者、年份、页码均不准编）。如果你没有用户给的原文片段，category 必须 = suggestion 或 free。
3. JSON 必须可被 json.loads 解析；中文用 UTF-8。
"""


def _prepend_must_audit_guard(messages: list[dict], sources: list[SourceItem]) -> list[dict]:
    src_lines = []
    for i, s in enumerate(sources, 1):
        title = (s.title or f"片段 {i}").strip()
        snippet = (s.snippet or "").strip()
        if not snippet:
            continue
        src_lines.append(f"[{i}] {title}\n{snippet}")
    src_block = "\n\n".join(src_lines) if src_lines else "(无)"
    system_content = _MUST_AUDIT_GUARD + "\n【原文片段】\n" + src_block
    return [{"role": "system", "content": system_content}] + messages


def _prepend_suggestion_guard(messages: list[dict]) -> list[dict]:
    return [{"role": "system", "content": _SUGGESTION_GUARD}] + messages



# ---------------- SPEC §4.3 自判模式实装 ----------------


def _handle_free_chat_self_judge(orch, messages: list[dict], body: "ChatRequest") -> "ChatResponse":
    """free_chat 路径的 AI 自判核心。

    流程：
    1. 把 _SELF_JUDGE_GUARD 前置到 system，让助手 AI 输出结构化 JSON
    2. 解析 JSON → 取出 content / category / claimed_sources
    3. 解析失败 → 视为 free，原文返回 + 警告日志
    4. category=factual_summary 且 claimed_sources 非空 → 走 verify_with_auditor 5 轮循环
    5. category=suggestion → 前置「【建议】」
    6. category=free → audit_status=user
    """
    # 1) 注入自判约束
    judged_msgs = [{"role": "system", "content": _SELF_JUDGE_GUARD}] + messages
    # 优先用 OpenAI json_object 强制输出（DeepSeek/Qwen 兼容；不支持的会忽略）
    extra = dict(body.extra or {})
    extra.setdefault("response_format", {"type": "json_object"})

    result = orch.chat(AIRole.ASSISTANT, judged_msgs, extra=extra)

    # 2) 调用失败 → 直接返回 error
    if not result.success:
        return ChatResponse(
            success=False,
            role=body.role,
            effective_role=result.role.value,
            output="",
            audit_status="error",
            error=result.error,
            error_code=result.error_code,
            project=body.project,
            stage=body.stage,
            task_type="free_chat",
            task_label="自由对话（AI 自判）",
        )

    # 3) 解析 JSON
    parsed = _parse_self_judge_output(result.output)
    content = parsed.get("content", "").strip()
    category = parsed.get("category", "free")
    claimed_sources_raw = parsed.get("claimed_sources", []) or []
    parse_warning = parsed.get("_parse_warning", "")

    # 4) 校验 category & sources 配套（防 AI 撒谎）
    cleaned_sources = []
    for s in claimed_sources_raw:
        if not isinstance(s, dict):
            continue
        snippet = str(s.get("snippet") or "").strip()
        if len(snippet) < 10:
            continue
        cleaned_sources.append({
            "title": str(s.get("title") or "").strip(),
            "snippet": snippet,
        })

    # 没拿到 content → 用原始输出兜底
    if not content:
        content = result.output.strip()
        category = "free"
        parse_warning = parse_warning or "AI 未输出 JSON 中的 content 字段，已降级为自由对话"

    # AI 声称要核查但没给 sources → 强制降级为 suggestion（不能让无来源的内容混入临时知识）
    if category == "factual_summary" and not cleaned_sources:
        logger.warning("free_chat 自判：AI 声称 factual_summary 但 claimed_sources 为空，强制降为 suggestion")
        category = "suggestion"
        parse_warning = (parse_warning + " | AI 自判为 factual_summary 但未提供来源片段，已降级").strip(" |")

    final_output = content
    audit_status: Literal["verified", "failed", "not_configured", "suggestion", "user", "error"] = "user"
    audit_rounds = 0
    audit_feedback = parse_warning
    audit_log_path = ""
    audit_dropped = False

    # 5) 按 category 分流
    if category == "factual_summary":
        # 走 5 轮核查
        verify = orch.verify_with_auditor(
            content=content,
            sources=cleaned_sources,
            project=body.project,
        )
        audit_rounds = verify.rounds
        audit_feedback = (parse_warning + " | " + verify.last_feedback).strip(" |") if parse_warning else verify.last_feedback
        audit_log_path = verify.log_path
        if verify.status == "verified":
            audit_status = "verified"
            final_output = verify.final_content
        elif verify.status == "failed":
            audit_status = "failed"
            final_output = ""
            audit_dropped = True
        elif verify.status == "not_configured":
            audit_status = "not_configured"
        else:
            audit_status = "error"
    elif category == "suggestion":
        audit_status = "suggestion"
        if final_output and not final_output.lstrip().startswith(("【建议", "建议", "Suggestion", "[建议")):
            final_output = "【建议】\n\n" + final_output
    else:
        audit_status = "user"

    # 6) 记入项目 assistant.md 记忆
    try:
        if body.project:
            short_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    short_user = m.get("content", "")
                    break
            append_assistant_memory(
                body.project,
                stage=body.stage or "",
                task_type=f"free_chat[self_judge:{category}]",
                user_message=short_user,
                assistant_output=final_output if final_output else f"_(已丢弃) {audit_feedback or ''}_",
                audit_status=audit_status,
                rounds=audit_rounds,
                success=True,
                error="",
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("append_assistant_memory failed: %s", e)

    # 把 claimed_sources 扁平化为字符串列表给前端展示
    flat_sources: list[str] = []
    for s in claimed_sources_raw:
        if isinstance(s, dict):
            title = (s.get("title") or "").strip()
            snippet = (s.get("snippet") or "").strip()
            if title and snippet:
                flat_sources.append(f"{title} — {snippet[:120]}")
            elif title:
                flat_sources.append(title)
            elif snippet:
                flat_sources.append(snippet[:160])
        elif isinstance(s, str) and s.strip():
            flat_sources.append(s.strip())

    return ChatResponse(
        success=True,
        role=body.role,
        effective_role=result.role.value,
        output=final_output,
        audit_status=audit_status,
        audit_rounds=audit_rounds,
        audit_feedback=audit_feedback,
        audit_log_path=audit_log_path,
        audit_dropped=audit_dropped,
        error="",
        error_code="",
        project=body.project,
        stage=body.stage,
        task_type=f"free_chat:{category}",
        task_label={
            "factual_summary": "自由对话 · AI 自判：来源引用（自动核查）",
            "suggestion":      "自由对话 · AI 自判：建议（无需核查）",
            "free":            "自由对话 · AI 自判：闲聊（无需核查）",
        }.get(category, "自由对话（AI 自判）"),
        self_judge_category=category,
        claimed_sources=flat_sources,
    )


def _parse_self_judge_output(text: str) -> dict:
    """解析助手 AI 自判 JSON。失败时返回 {_parse_warning: ...}，由调用方降级。"""
    import json as _json
    if not text:
        return {"_parse_warning": "AI 未返回任何内容"}
    s = text.strip()
    # 去掉 ```json ... ``` 包裹
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    lb, rb = s.find("{"), s.rfind("}")
    if lb != -1 and rb > lb:
        s = s[lb : rb + 1]
    try:
        obj = _json.loads(s)
        if not isinstance(obj, dict):
            return {"_parse_warning": "JSON 不是对象"}
        cat = str(obj.get("category", "")).strip()
        if cat not in ("factual_summary", "suggestion", "free"):
            cat = "free"
        return {
            "content": str(obj.get("content", "") or ""),
            "category": cat,
            "claimed_sources": obj.get("claimed_sources") or [],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("self_judge JSON parse failed: %s, raw=%r", e, text[:200])
        return {
            "content": text,  # 用原始输出兜底
            "category": "free",
            "claimed_sources": [],
            "_parse_warning": f"AI 自判 JSON 解析失败（已降级为自由对话）: {e!s}",
        }
