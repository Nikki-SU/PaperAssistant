"""SPEC §8.3：三角色记忆自动追加。

- assistant.md：助手 AI 的所有输出
- reviewer.md：审阅 AI 的事实核查日志（已在 ai_orchestrator 的 _append_reviewer_log 中写）
- secretary.md：秘书 AI 的修订/审阅记录

所有写入路径：projects/{name}/memories/{role}.md

注意：本模块仅做「日志追加」。reviewer.md 的写入由 ai_orchestrator.verify_with_auditor 全权负责，
本模块不重复写 reviewer.md。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from ..config import get_settings
from ..storage import append_role_memory_entry

logger = logging.getLogger(__name__)


_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe_project_name(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip() or "_unnamed"


def _project_memory_dir(project: Optional[str]) -> Path:
    settings = get_settings()
    base = settings.projects_dir
    if project:
        d = base / _safe_project_name(project) / "memories"
    else:
        d = base / "_global" / "memories"
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_assistant_memory(
    project: Optional[str],
    *,
    stage: str = "",
    task_type: str = "",
    title: str = "",
    user_message: str = "",
    assistant_output: str = "",
    audit_status: str = "",
    rounds: int = 0,
    success: bool = True,
    error: str = "",
) -> Path:
    """追加一条助手记忆。

    SPEC §8.3：助手 AI 的所有输出都要进 assistant.md。
    """
    path = _project_memory_dir(project) / "assistant.md"
    short_user = (user_message or "").strip().splitlines()[0][:80] if user_message else ""
    eff_title = title or f"[{task_type or 'chat'}] {short_user}" or "(对话)"

    meta: dict[str, Any] = {}
    if stage:
        meta["阶段"] = stage
    if task_type:
        meta["任务类型"] = task_type
    if audit_status:
        meta["审阅状态"] = audit_status
    if rounds:
        meta["审阅轮次"] = rounds
    if not success:
        meta["状态"] = "失败"
        if error:
            meta["错误"] = error

    body_parts: list[str] = []
    if user_message:
        body_parts.append("**用户输入：**\n\n```\n" + user_message.strip() + "\n```")
    if assistant_output:
        body_parts.append("**助手输出：**\n\n" + assistant_output.rstrip())
    body = "\n\n".join(body_parts) if body_parts else "_(无内容)_"

    append_role_memory_entry(
        path,
        role_label="助手",
        title=eff_title,
        body=body,
        meta=meta,
    )
    return path


def append_secretary_memory(
    project: Optional[str],
    *,
    title: str,
    body: str,
    target_text: str = "",
    suggestion: str = "",
    accepted: Optional[bool] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Path:
    """追加一条秘书记忆。

    SPEC §8.3：秘书 AI 的修订建议与采纳情况。
    """
    path = _project_memory_dir(project) / "secretary.md"

    m: dict[str, Any] = dict(meta or {})
    if accepted is True:
        m.setdefault("采纳", "是")
    elif accepted is False:
        m.setdefault("采纳", "否")

    parts: list[str] = []
    if body:
        parts.append(body.rstrip())
    if target_text:
        parts.append("**原文：**\n\n```\n" + target_text.strip() + "\n```")
    if suggestion:
        parts.append("**修订建议：**\n\n" + suggestion.rstrip())
    full_body = "\n\n".join(parts) if parts else "_(无内容)_"

    append_role_memory_entry(
        path,
        role_label="秘书",
        title=title or "(秘书审阅)",
        body=full_body,
        meta=m,
    )
    return path
