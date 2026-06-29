"""引用管理 API。

每个项目独立维护一份 citations.csv：
  doi, label, used_in, note, added_at
- doi：主键，必须先在 library/cards.csv 中存在
- label：写作中引用键（如 perovskite_stability_2024）
- used_in：以分号分隔的章节路径（如 paper/3-results.md;paper/4-discussion.md）
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..storage import (
    append_row,
    delete_row,
    ensure_csv,
    filter_rows,
    now_iso,
    read_rows,
    upsert_row,
)

router = APIRouter(prefix="/api/citation", tags=["citation"])

CITATION_HEADERS = ["doi", "label", "used_in", "note", "added_at"]


def _citations_csv(project: str) -> Path:
    return get_settings().projects_dir / project / "citations" / "citations.csv"


def _cards_csv() -> Path:
    return get_settings().library_cards_csv


class CitationAdd(BaseModel):
    doi: str
    label: str = ""
    used_in: str = ""
    note: str = ""


@router.get("/{project}")
def list_citations(project: str) -> dict:
    p = _citations_csv(project)
    ensure_csv(p, CITATION_HEADERS)
    rows = read_rows(p)
    return {"citations": rows}


@router.post("/{project}")
def add_citation(project: str, body: CitationAdd) -> dict:
    doi = body.doi.strip().lower()
    if not doi:
        raise HTTPException(status_code=400, detail="doi 不能为空")
    # 必须先存在于全局文献库
    if not filter_rows(_cards_csv(), where={"doi": doi}):
        raise HTTPException(
            status_code=409,
            detail=f"文献尚未入库，请先在「文献库」中上传或创建：{doi}",
        )
    p = _citations_csv(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    ensure_csv(p, CITATION_HEADERS)
    row = {
        "doi": doi,
        "label": body.label or doi.replace("/", "_"),
        "used_in": body.used_in,
        "note": body.note,
        "added_at": now_iso(),
    }
    is_new, merged = upsert_row(p, CITATION_HEADERS, row, primary_key="doi")
    return {"citation": merged, "created": is_new}


@router.delete("/{project}/{doi:path}")
def remove_citation(project: str, doi: str) -> dict:
    p = _citations_csv(project)
    if not p.exists():
        raise HTTPException(status_code=404, detail="项目引用表不存在")
    ok = delete_row(p, "doi", doi.lower())
    if not ok:
        raise HTTPException(status_code=404, detail=f"引用不存在：{doi}")
    return {"doi": doi, "removed": True}
