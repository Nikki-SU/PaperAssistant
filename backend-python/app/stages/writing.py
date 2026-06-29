"""阶段三：正文撰写（SPEC §7.3）。4 子阶段；默认面板 左 md-editor / 右 latex-preview。"""
from __future__ import annotations

from pathlib import Path

from ..storage import append_role_memory_entry, write_text

STAGE_NAME = "writing"
STAGE_LABEL = "正文撰写"
DEFAULT_LEFT_PANE = "md-editor"
DEFAULT_RIGHT_PANE = "latex-preview"

STEPS = [
    {"id": "3.1", "title": "理论建设（推荐/上传/总结/勾选）", "actor": "user+ai", "audit": "建议+必须核查"},
    {"id": "3.2", "title": "方法论：归纳方法 + 教材流程 + 综合建议", "actor": "assistant", "audit": "必须核查+建议"},
    {"id": "3.3", "title": "数据：用户上传 + AI 提供方向参考",  "actor": "user+ai", "audit": "参考性"},
    {"id": "3.4", "title": "结果与结论（人类自写，AI 仅建议）", "actor": "user",     "audit": "建议"},
]

INTRO_MD = (
    "# 正文撰写阶段\n\n"
    "**视角分支：**\n"
    "- 社科：理论 → 研究设计 → 数据 → 结果和结论\n"
    "- 理科：实验 → 表征 → 机理 → 结果和结论\n\n"
    "**核心规则：**\n"
    "- 凡声称「来自某文献/教材」的内容必须经审阅 AI 核查（≤5 轮）。\n"
    "- 结果与结论由你自己写；AI 只能在标注「建议」的前提下提供方向参考。\n"
    "- 左栏 Markdown 编辑器写作，右栏 LaTeX 预览实时联动。\n"
)


def describe() -> dict:
    return {
        "stage": STAGE_NAME, "label": STAGE_LABEL,
        "default_left_pane": DEFAULT_LEFT_PANE, "default_right_pane": DEFAULT_RIGHT_PANE,
        "steps": STEPS, "intro_md": INTRO_MD,
        "expected_panels": ["md-editor", "latex-preview", "ai-chat", "lit-list", "kb-list"],
        "audit_hint": "方法/理论总结=必须核查；综合建议/结果方向=建议；数据解读=参考性。",
    }


def on_enter(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"进入「{STAGE_LABEL}」阶段",
        body=(f"项目「{proj_name}」切换到 stage=`{STAGE_NAME}`。写作时引用使用 `[@doi:xxx]` 标记。"),
        meta={"stage": STAGE_NAME, "time": now},
    )
    draft = proj_dir / "paper" / "draft.md"
    if not draft.exists():
        draft.parent.mkdir(parents=True, exist_ok=True)
        write_text(
            draft,
            f"# {proj_name}\n\n"
            f"<!-- 创建时间：{now} -->\n\n"
            f"## 引言\n\n"
            f"## 理论 / 实验\n\n"
            f"## 方法 / 表征\n\n"
            f"## 数据 / 机理\n\n"
            f"## 结果与结论\n\n"
            f"<!-- 由人类自写。AI 仅可标注「建议」。 -->\n",
        )


def on_exit(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"离开「{STAGE_LABEL}」阶段",
        body=f"项目「{proj_name}」从 stage=`{STAGE_NAME}` 切出。",
        meta={"stage": STAGE_NAME, "time": now},
    )
