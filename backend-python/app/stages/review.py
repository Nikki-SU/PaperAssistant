"""阶段二：文献综述（SPEC §7.2）。5 步；默认面板 左 ai-chat / 右 lit-list。"""
from __future__ import annotations

from pathlib import Path

from ..storage import append_role_memory_entry

STAGE_NAME = "review"
STAGE_LABEL = "文献综述"
DEFAULT_LEFT_PANE = "ai-chat"
DEFAULT_RIGHT_PANE = "lit-list"

STEPS = [
    {"id": 1, "title": "AI 推荐检索关键词 + 平台",  "actor": "assistant", "audit": "建议"},
    {"id": 2, "title": "用户检索并上传文献",        "actor": "user",      "audit": "—"},
    {"id": 3, "title": "AI 总结归纳，附来源引用",   "actor": "assistant", "audit": "必须核查"},
    {"id": 4, "title": "AI 询问勾选实际引用文献",   "actor": "assistant", "audit": "—"},
    {"id": 5, "title": "用户勾选 → 写入 selections", "actor": "user",      "audit": "—"},
]

INTRO_MD = (
    "# 文献综述阶段\n\n"
    "**目标：** 系统阅读、总结相关文献，初步圈定将引用的篇目。\n\n"
    "- 总结类输出必须经审阅 AI 事实核查；本阶段勾选的文献写入 `selections.csv`（stage=`review`）。\n"
    "- 进入「引用」阶段时会聚合各阶段勾选 → 生成 `citations/selected.csv`。\n"
)


def describe() -> dict:
    return {
        "stage": STAGE_NAME, "label": STAGE_LABEL,
        "default_left_pane": DEFAULT_LEFT_PANE, "default_right_pane": DEFAULT_RIGHT_PANE,
        "steps": STEPS, "intro_md": INTRO_MD,
        "expected_panels": ["ai-chat", "lit-list", "kb-search", "file-watcher"],
        "audit_hint": "推荐关键词=建议；总结文献=必须核查。勾选写入 selections.csv（stage=review）。",
    }


def on_enter(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"进入「{STAGE_LABEL}」阶段",
        body=(f"项目「{proj_name}」切换到 stage=`{STAGE_NAME}`。按 SPEC §7.2 五步推进。"),
        meta={"stage": STAGE_NAME, "time": now},
    )


def on_exit(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"离开「{STAGE_LABEL}」阶段",
        body=f"项目「{proj_name}」从 stage=`{STAGE_NAME}` 切出。",
        meta={"stage": STAGE_NAME, "time": now},
    )
