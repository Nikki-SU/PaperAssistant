"""AI 对话 API（SPEC §四 / §六）。

端点：
- POST /api/ai/chat   通用聊天端点，按 role 路由（assistant/auditor/secretary）
- POST /api/ai/verify SPEC §4.3 事实核查 5 轮循环
- GET  /api/ai/status 3 个角色的就绪状态（不含 mineru —— mineru 单独有上传端点）

铁律：失败必须降级，返回结构化错误而非 5xx，方便前端友好提示。
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import (
    AIRole,
    get_orchestrator,
    load_role_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------------- 模型 ----------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str


class ChatRequest(BaseModel):
    role: Literal["assistant", "auditor", "secretary"] = Field(
        "assistant", description="目标接口位"
    )
    messages: list[ChatMessage] = Field(..., min_length=1)
    project: Optional[str] = None
    stage: Optional[str] = None
    extra: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    success: bool
    role: str
    effective_role: str
    output: str
    audit_status: Literal["verified", "suggestion", "user", "error"] = "suggestion"
    error: str = ""
    error_code: str = ""
    project: Optional[str] = None
    stage: Optional[str] = None


class RoleStatus(BaseModel):
    role: str
    configured: bool
    has_endpoint: bool
    has_key: bool
    has_model: bool
    endpoint: str = ""
    model: str = ""


# ---------------- 端点 ----------------


@router.get("/status")
def chat_status() -> dict:
    """返回 3 个 AI 角色（assistant/auditor/secretary）的就绪状态。
    mineru 走 /api/literature/upload，不在这里。
    """
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


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    try:
        role = AIRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效 role: {body.role}")

    orch = get_orchestrator()
    # 每次调用前 refresh，确保读到设置面板最新的配置
    orch.refresh()

    msgs = [m.model_dump() for m in body.messages]
    result = orch.chat(role, msgs, extra=body.extra)

    audit_status: Literal["verified", "suggestion", "user", "error"]
    if not result.success:
        audit_status = "error"
    elif result.role == AIRole.AUDITOR:
        audit_status = "verified"
    else:
        audit_status = "suggestion"

    return ChatResponse(
        success=result.success,
        role=body.role,
        effective_role=result.role.value,
        output=result.output,
        audit_status=audit_status,
        error=result.error,
        error_code=result.error_code,
        project=body.project,
        stage=body.stage,
    )



# ---------------- SPEC §4.3 事实核查 ----------------


class SourceItem(BaseModel):
    title: str = ""
    snippet: str = ""


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
    """SPEC §4.3：让 auditor 检查 content 是否与 sources 一致。

    - 一致且无新增 → status=verified
    - 5 轮仍未通过 → status=failed（内容应被业务侧丢弃）
    - auditor 未配置 → status=not_configured
    - 中途调用失败 → status=error
    """
    orch = get_orchestrator()
    orch.refresh()
    result = orch.verify_with_auditor(
        body.content,
        [s.model_dump() for s in body.sources],
        project=body.project,
        max_rounds=body.max_rounds,
    )
    # 把 status 映射到前端用的 audit_status，省得前端再翻译一次
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
