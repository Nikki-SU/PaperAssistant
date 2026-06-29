"""引用管理 API：CSL 格式化、引用列表生成。

对应 SPEC：项目二 §七.4 引用
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/{project}/list")
def list_citations(project: str) -> dict:
    """汇总该项目各阶段已勾选的文献，返回去重列表。"""
    # TODO: 读 projects/{project}/citations/selected.csv
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/{project}/format")
def format_citations(project: str, style: str = "apa") -> dict:
    """按 CSL 格式化引用（apa / gb-t-7714-2015 / chicago 等）。"""
    # TODO: 调用 citeproc-py + 本地 CSL 样式文件
    raise HTTPException(status_code=501, detail="Not implemented yet")
