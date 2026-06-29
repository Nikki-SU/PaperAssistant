"""排版 API：LaTeX 模板、Markdown→LaTeX、PDF 编译（Tectonic）。

对应 SPEC：项目二 §七.5 排版
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/{project}/template")
def generate_template(project: str, format_spec: str) -> dict:
    """根据用户粘贴的格式要求生成 LaTeX 模板骨架。"""
    # TODO: 调助手 AI 生成 .tex 模板
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/{project}/compile")
def compile_pdf(project: str) -> dict:
    """Markdown → LaTeX → Tectonic 编译为 PDF。"""
    # TODO: 1) 替换引用标记 [@doi:xxx]；2) md→tex；3) tectonic compile
    raise HTTPException(status_code=501, detail="Not implemented yet")
