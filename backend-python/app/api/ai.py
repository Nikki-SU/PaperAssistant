"""AI 对话 API（SPEC §4.3 / §4.5 / §六）。

端点：
- POST /api/ai/chat   通用聊天端点，按 task_type 自动分流：
                       · 6 类必须核查 → 自动调 verify_with_auditor
                       · 4 类建议      → 标 audit_status=suggestion
                       · free_chat/other → 标 audit_status=user
- POST /api/ai/verify SPEC §4.3 事实核查 5 轮循环
- GET  /api/ai/status 3 个角色的就绪状态（mineru 单独有上传端点）

铁律：失败必须降级，返回结构化错误而非 5xx，方便前端友好提示。
铁律 §4.3：6 类必须核查任务在缺 sources 时直接 400；5 轮失败时硬丢弃 final_content。
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
