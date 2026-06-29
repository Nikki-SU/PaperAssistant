"""阶段一：选题（SPEC §7.1）。8 步工作流；默认面板 左 ai-chat / 右 kb-list。"""
from __future__ import annotations

from pathlib import Path

from ..storage import append_role_memory_entry, write_text

STAGE_NAME = "topic"
STAGE_LABEL = "选题"
DEFAULT_LEFT_PANE = "ai-chat"
DEFAULT_RIGHT_PANE = "kb-list"

STEPS = [
    {"id": 1, "title": "输入论文要求 + 课程/学科",     "actor": "user",       "audit": "—"},
    {"id": 2, "title": "AI 列出已有教材 / 推荐关键词", "actor": "assistant",  "audit": "建议"},
    {"id": 3, "title": "上传课本 → 总结入临时知识",   "actor": "user+ai",    "audit": "必须核查"},
    {"id": 4, "title": "AI 推荐选题方向 + 检索关键词", "actor": "assistant",  "audit": "建议"},
    {"id": 5, "title": "用户自行检索（爬取仅展示）",   "actor": "user",       "audit": "—"},
    {"id": 6, "title": "上传文献 → 总结入临时知识",   "actor": "user+ai",    "audit": "必须核查"},
    {"id": 7, "title": "AI 推荐具体选题",             "actor": "assistant",  "audit": "建议"},
    {"id": 8, "title": "用户选定 → 项目改名",          "actor": "user",       "audit": "—"},
]

INTRO_MD = (
    "# 选题阶段\n\n"
    "**目标：** 在本地知识库 + 检索结果基础上由 AI 给出**建议**，由你拍板选题。\n\n"
    "- AI **不会**凭空给出具体文献内容。所有「来自某本书/某篇文献」必须经审阅 AI 核查（≤5 轮）。\n"
    "- 选题方向 / 检索关键词等推断性内容会被标注「💡 建议」。\n"
    "- 选定选题后，可在左栏项目行点 ⋯ → 重命名以更新项目名称。\n"
)


def describe() -> dict:
    return {
        "stage": STAGE_NAME, "label": STAGE_LABEL,
        "default_left_pane": DEFAULT_LEFT_PANE, "default_right_pane": DEFAULT_RIGHT_PANE,
        "steps": STEPS, "intro_md": INTRO_MD,
        "expected_panels": ["ai-chat", "kb-list", "kb-search", "web"],
        "audit_hint": "建议类（选题方向/关键词）标注「建议」；总结类（教材/文献）必须核查 ≤5 轮。",
    }


def on_enter(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"进入「{STAGE_LABEL}」阶段",
        body=(f"项目「{proj_name}」切换到 stage=`{STAGE_NAME}`。按 SPEC §7.1 八步推进。"),
        meta={"stage": STAGE_NAME, "time": now},
    )
    temp_kb = proj_dir / "temp_knowledge.md"
    if not temp_kb.exists():
        write_text(
            temp_kb,
            f"# {proj_name} · 临时知识\n\n"
            f"> 创建时间：{now}\n\n"
            f"_每次「总结上传材料」经审阅事实核查后追加到这里。_\n",
        )


def on_exit(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"离开「{STAGE_LABEL}」阶段",
        body=f"项目「{proj_name}」从 stage=`{STAGE_NAME}` 切出。",
        meta={"stage": STAGE_NAME, "time": now},
    )
