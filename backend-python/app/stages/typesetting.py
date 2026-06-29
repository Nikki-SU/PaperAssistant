"""阶段五：排版（SPEC §7.5）。默认面板 左 md-editor / 右 latex-preview。"""
from __future__ import annotations

from pathlib import Path

from ..storage import append_role_memory_entry, write_text

STAGE_NAME = "typesetting"
STAGE_LABEL = "排版"
DEFAULT_LEFT_PANE = "md-editor"
DEFAULT_RIGHT_PANE = "latex-preview"

STEPS = [
    {"id": 1, "title": "粘贴目标期刊格式要求",         "actor": "user",      "audit": "—"},
    {"id": 2, "title": "AI 生成 LaTeX 模板骨架",       "actor": "assistant", "audit": "建议"},
    {"id": 3, "title": "用户反馈 → 迭代",              "actor": "user+ai",   "audit": "—"},
    {"id": 4, "title": "Markdown ↔ LaTeX 实时联动",   "actor": "system",    "audit": "—"},
    {"id": 5, "title": "导出 .tex / Tectonic 编译 PDF", "actor": "user",     "audit": "—"},
]

INTRO_MD = (
    "# 排版阶段\n\n"
    "**目标：** 把 Markdown 正文按目标期刊格式渲染为 LaTeX / PDF。\n\n"
    "- 模板由你粘贴格式要求 → AI 生成骨架 → 你反馈迭代。\n"
    "- 引用标记 `[@doi:xxx]` 会按所选 CSL 格式替换。\n"
    "- 可一键编译 PDF（依赖 Tectonic；未配置时仅导出 manuscript.md）。\n"
)


def describe() -> dict:
    return {
        "stage": STAGE_NAME, "label": STAGE_LABEL,
        "default_left_pane": DEFAULT_LEFT_PANE, "default_right_pane": DEFAULT_RIGHT_PANE,
        "steps": STEPS, "intro_md": INTRO_MD,
        "expected_panels": ["md-editor", "latex-preview", "ai-chat", "stage-guide"],
        "audit_hint": "本阶段不涉及事实核查；AI 生成模板骨架时标注「建议」。",
    }


def on_enter(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"进入「{STAGE_LABEL}」阶段",
        body=(f"项目「{proj_name}」切换到 stage=`{STAGE_NAME}`。按 SPEC §7.5 二步推进。"),
        meta={"stage": STAGE_NAME, "time": now},
    )
    tpl = proj_dir / "paper" / "template.tex"
    if not tpl.exists():
        tpl.parent.mkdir(parents=True, exist_ok=True)
        write_text(
            tpl,
            "% PaperAssistant LaTeX 模板骨架（待 AI 按目标期刊格式补全）\n"
            "% 创建时间：" + now + "\n"
            "\\documentclass[11pt]{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{ctex}\n"
            "\\usepackage{amsmath, amssymb, graphicx, hyperref}\n"
            "\\title{" + proj_name + "}\n"
            "\\begin{document}\n"
            "\\maketitle\n"
            "% \\input{manuscript.tex}\n"
            "\\end{document}\n",
        )


def on_exit(proj_dir: Path, proj_name: str, now: str) -> None:
    append_role_memory_entry(
        proj_dir / "memories" / "assistant.md", role_label="助手",
        title=f"离开「{STAGE_LABEL}」阶段",
        body=f"项目「{proj_name}」从 stage=`{STAGE_NAME}` 切出。",
        meta={"stage": STAGE_NAME, "time": now},
    )
