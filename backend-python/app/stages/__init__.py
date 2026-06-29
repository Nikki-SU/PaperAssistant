"""五阶段业务逻辑（SPEC §六 / §7.1–7.5）。

每个阶段模块定义：
- STAGE_NAME, STAGE_LABEL
- describe()  → 返回 stage info（steps, default panes, intro_md, audit_policy）
- on_enter(proj_dir, proj_name, now)  → 阶段切入副作用（写记忆 + 种子文件）
- on_exit(proj_dir, proj_name, now)   → 阶段切出副作用（汇总到助手记忆）

stage 切换由 project.update_project 调度，调用顺序为旧阶段 on_exit → 新阶段 on_enter。
"""
from __future__ import annotations

from typing import Any, Dict

from . import topic, review, writing, citation, typesetting

__all__ = [
    "topic", "review", "writing", "citation", "typesetting",
    "get_stage", "list_stages", "STAGE_REGISTRY",
]

STAGE_REGISTRY: Dict[str, Any] = {
    topic.STAGE_NAME: topic,
    review.STAGE_NAME: review,
    writing.STAGE_NAME: writing,
    citation.STAGE_NAME: citation,
    typesetting.STAGE_NAME: typesetting,
}


def get_stage(name: str):
    if name not in STAGE_REGISTRY:
        raise KeyError(f"未知阶段：{name}")
    return STAGE_REGISTRY[name]


def list_stages() -> list[dict]:
    return [m.describe() for m in STAGE_REGISTRY.values()]
