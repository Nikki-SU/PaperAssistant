"""勾选记录管理 API（SPEC §7.2 / §7.4）。

selections.csv 字段：doi, stage, selected, source_label, note, updated_at
- 复合键 (doi, stage) 唯一；同 doi 不同 stage 多条共存
- aggregate：把 selected=true 记录去重写入 citations/selected.csv，used_in 合并 stage 列表
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..stages import STAGE_REGISTRY, get_stage, list_stages
from ..storage import (
    append_row,
    ensure_csv,
    now_iso,
    read_rows,
)

router = APIRouter(prefix="/api/project", tags=["selections"])

SELECTIONS_HEADERS = ["doi", "stage", "selected", "source_label", "note", "updated_at"]
SELECTED_CSV_HEADERS = ["doi", "label", "used_in", "note", "added_at"]


def _selections_csv(project: str) -> Path:
    return get_settings().projects_dir / project / "selections.csv"


def _selected_csv(project: str) -> Path:
    return get_settings().projects_dir / project / "citations" / "selected.csv"


def _project_exists(project: str) -> bool:
    return (get_settings().projects_dir / project).exists()


class SelectionSave(BaseModel):
    doi: str
    stage: str
    selected: bool = True
    source_label: str = ""
    note: str = ""


class SelectionsBulk(BaseModel):
    items: list[SelectionSave]


@router.get("/{project}/selections")
def list_selections(project: str, stage: str = "") -> dict:
    if not _project_exists(project):
        raise HTTPException(status_code=404, detail=f"项目不存在：{project}")
    p = _selections_csv(project)
    ensure_csv(p, SELECTIONS_HEADERS)
    rows = read_rows(p)
    if stage:
        rows = [r for r in rows if r.get("stage") == stage]
    by_stage: dict[str, dict] = {}
    for r in rows:
        s = r.get("stage", "")
        b = by_stage.setdefault(s, {"selected": 0, "deselected": 0})
        if str(r.get("selected", "")).lower() == "true":
            b["selected"] += 1
        else:
            b["deselected"] += 1
    return {"selections": rows, "by_stage": by_stage}


@router.post("/{project}/selections")
def save_selection(project: str, body: SelectionSave) -> dict:
    if not _project_exists(project):
        raise HTTPException(status_code=404, detail=f"项目不存在：{project}")
    if body.stage not in STAGE_REGISTRY:
        raise HTTPException(status_code=400, detail=f"非法 stage：{body.stage}")
    if not body.doi.strip():
        raise HTTPException(status_code=400, detail="doi 不能为空")

    p = _selections_csv(project)
    ensure_csv(p, SELECTIONS_HEADERS)
    rows = read_rows(p)
    doi_lower = body.doi.lower().strip()
    rows_keep = [
        r for r in rows
        if not (r.get("doi", "").lower() == doi_lower and r.get("stage") == body.stage)
    ]
    row = {
        "doi": doi_lower,
        "stage": body.stage,
        "selected": "true" if body.selected else "false",
        "source_label": body.source_label,
        "note": body.note,
        "updated_at": now_iso(),
    }
    rows_keep.append(row)
    p.unlink(missing_ok=True)
    ensure_csv(p, SELECTIONS_HEADERS)
    for r in rows_keep:
        append_row(p, SELECTIONS_HEADERS, r)
    return {"selection": row, "total": len(rows_keep)}


@router.post("/{project}/selections/bulk")
def save_selections_bulk(project: str, body: SelectionsBulk) -> dict:
    saved = []
    for item in body.items:
        r = save_selection(project, item)
        saved.append(r["selection"])
    return {"saved": saved, "count": len(saved)}


@router.delete("/{project}/selections")
def delete_selection(project: str, doi: str, stage: str) -> dict:
    if not _project_exists(project):
        raise HTTPException(status_code=404, detail=f"项目不存在：{project}")
    p = _selections_csv(project)
    if not p.exists():
        raise HTTPException(status_code=404, detail="勾选表不存在")
    rows = read_rows(p)
    rows_keep = [r for r in rows if not (r.get("doi", "").lower() == doi.lower() and r.get("stage") == stage)]
    removed = len(rows) - len(rows_keep)
    p.unlink()
    ensure_csv(p, SELECTIONS_HEADERS)
    for r in rows_keep:
        append_row(p, SELECTIONS_HEADERS, r)
    return {"doi": doi, "stage": stage, "removed": removed > 0, "remaining": len(rows_keep)}


@router.post("/{project}/selections/aggregate")
def aggregate_selections(project: str) -> dict:
    """聚合 selected=true 的记录 → citations/selected.csv（同 doi 跨 stage 合并 used_in）。"""
    if not _project_exists(project):
        raise HTTPException(status_code=404, detail=f"项目不存在：{project}")
    p = _selections_csv(project)
    ensure_csv(p, SELECTIONS_HEADERS)
    rows = read_rows(p)

    selected_by_doi: dict[str, dict] = {}
    by_stage_count: dict[str, int] = {s: 0 for s in STAGE_REGISTRY}
    skipped_no_doi = 0
    for r in rows:
        doi = r.get("doi", "").strip().lower()
        if not doi:
            skipped_no_doi += 1
            continue
        is_selected = str(r.get("selected", "")).lower() == "true"
        stage = r.get("stage", "")
        if is_selected and stage in by_stage_count:
            by_stage_count[stage] += 1
        if not is_selected:
            continue
        if doi in selected_by_doi:
            prev_used = selected_by_doi[doi]["used_in"]
            if stage and stage not in prev_used.split(";"):
                selected_by_doi[doi]["used_in"] = (prev_used + ";" + stage) if prev_used else stage
            if r.get("note"):
                cur_note = selected_by_doi[doi]["note"]
                selected_by_doi[doi]["note"] = (cur_note + " | " + r.get("note", "")) if cur_note else r.get("note", "")
        else:
            selected_by_doi[doi] = {
                "doi": doi,
                "label": r.get("source_label") or doi.replace("/", "_"),
                "used_in": stage,
                "note": r.get("note", ""),
                "added_at": now_iso(),
            }

    out = _selected_csv(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    ensure_csv(out, SELECTED_CSV_HEADERS)
    for entry in selected_by_doi.values():
        append_row(out, SELECTED_CSV_HEADERS, entry)

    empty_stages = [s for s, cnt in by_stage_count.items() if cnt == 0 and s in {"review", "writing"}]

    return {
        "written": len(selected_by_doi),
        "by_stage_selected_count": by_stage_count,
        "empty_stages": empty_stages,
        "skipped_no_doi": skipped_no_doi,
        "selected_csv_path": str(out),
    }


@router.get("/{project}/stage-info")
def get_stage_info(project: str, stage: str = "") -> dict:
    """返回当前阶段（或指定 ?stage=）的工作流描述。"""
    if not _project_exists(project):
        raise HTTPException(status_code=404, detail=f"项目不存在：{project}")
    if not stage:
        meta_csv = get_settings().projects_dir / project / "meta.csv"
        if meta_csv.exists():
            rows = read_rows(meta_csv)
            if rows:
                stage = rows[-1].get("stage", "")
    if not stage:
        stage = "topic"
    if stage not in STAGE_REGISTRY:
        raise HTTPException(status_code=400, detail=f"非法 stage：{stage}")
    return {
        "current": get_stage(stage).describe(),
        "all_stages": list_stages(),
    }
