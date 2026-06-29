"""阶段四：引用（SPEC §7.4）。核心：只有用户明确勾选的文献进入引用列表。默认面板 左 ai-chat / 右 lit-list。"""
from __future__ import annotations

from pathlib import Path

from ..storage import append_role_memory_entry

STAGE_NAME = "citation"
STAGE_LABEL = "引用"
DEFAULT_LEFT_PANE = "ai-chat"
DEFAULT_RIGHT_PANE = "lit-list"

STEPS = [
    {"id": 1, "title": "聚合各阶段勾选 → selected.csv", "actor": "system",    "audit": "—"},
    {"id": 2, "title": "0 勾选阶段警告：是否补勾",       "actor": "assistant", "audit": "—"},
    {"id": 3, "title": "用户选择引用格式",                "actor": "user",      "audit": "—"},
    {"id": 4, "title": "系统按 CSL 生成引用列表",        "actor": "system",    "audit": "—"},
    {"id": 5, "title": "确认 → 替换 [@doi:xxx] 标记",    "actor": "user",      "audit": "—"},
]

INTRO_MD = (
    "# 引用阶段\n\n"
    "**目标：** 把各阶段勾选的文献汇总成引用清单。\n\n"
    "- 进入本阶段时会自动「聚合」前置阶段的勾选 → `citations/selected.csv`。\n"
    "- 如果某阶段 0 勾选，会弹出补勾提醒。\n"
)


def describe() -> dict:
    return {
        "stage": STAGE_NAME, "label": STAGE_LABEL,
        "default_left_pane": DEFAULT_LEFT_PANE, "default_right_pane": DEFAULT_RIGHT_PANE,
        "steps": STEPS, "intro_md": INTRO_MD,
        "expected_panels": ["ai-chat", "lit-list", "md-editor", "citation-aggregate"],
        "audit_hint": "本阶段不涉及事实核查，仅勾选汇总 + 引用格式选择。",
    }


def on_enter(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"进入「{STAGE_LABEL}」阶段",
        body=(f"项目「{proj_name}」切换到 stage=`{STAGE_NAME}`。请聚合各阶段勾选。"),
        meta={"stage": STAGE_NAME, "time": now},
    )


def on_exit(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"离开「{STAGE_LABEL}」阶段",
        body=f"项目「{proj_name}」从 stage=`{STAGE_NAME}` 切出。",
        meta={"stage": STAGE_NAME, "time": now},
    )
