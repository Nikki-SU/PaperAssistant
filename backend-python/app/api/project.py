"""项目管理 API。

数据目录结构（SPEC §五.1）：
data_root/projects/{name}/
├── memories/   ← Markdown：长期记忆、临时聊天摘要
├── paper/      ← Markdown：论文章节
├── citations/  ← CSV：本项目选定的引用
└── meta.csv    ← 单行 CSV：项目元信息（name, stage, perspective, created_at, last_modified）
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..storage import (
    append_row,
    ensure_csv,
    filter_rows,
    read_rows,
    upsert_row,
    delete_row,
    now_iso,
)

router = APIRouter(prefix="/api/project", tags=["project"])

PROJECTS_INDEX_HEADERS = [
    "name", "stage", "perspective", "topic", "created_at", "last_modified",
]
PROJECT_META_HEADERS = PROJECTS_INDEX_HEADERS  # 同结构，单行写在项目目录下

VALID_STAGES = ["topic", "review", "writing", "citation", "typesetting"]
VALID_PERSPECTIVES = ["", "social", "science"]  # 空表示尚未选择

_SAFE_NAME_RE = re.compile(r"^[\w\-. \u4e00-\u9fa5]{1,80}$")


def _projects_index_csv() -> Path:
    return get_settings().projects_dir / "_index.csv"


def _project_dir(name: str) -> Path:
    return get_settings().projects_dir / name


def _project_meta_csv(name: str) -> Path:
    return _project_dir(name) / "meta.csv"


def _validate_name(name: str) -> None:
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"非法项目名：{name!r}")


class ProjectCreate(BaseModel):
    name: str
    topic: str = ""
    perspective: str = ""  # social / science / ""


class ProjectUpdate(BaseModel):
    stage: str | None = None
    perspective: str | None = None
    topic: str | None = None


@router.get("")
def list_projects() -> dict:
    ensure_csv(_projects_index_csv(), PROJECTS_INDEX_HEADERS)
    rows = read_rows(_projects_index_csv())
    rows.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return {"projects": rows}


@router.post("")
def create_project(body: ProjectCreate) -> dict:
    _validate_name(body.name)
    if body.perspective and body.perspective not in VALID_PERSPECTIVES:
        raise HTTPException(status_code=400, detail=f"非法 perspective：{body.perspective}")
    proj_dir = _project_dir(body.name)
    if proj_dir.exists():
        raise HTTPException(status_code=409, detail=f"项目已存在：{body.name}")
    # 建子目录
    (proj_dir / "memories").mkdir(parents=True, exist_ok=True)
    (proj_dir / "paper").mkdir(parents=True, exist_ok=True)
    (proj_dir / "citations").mkdir(parents=True, exist_ok=True)

    now = now_iso()
    row = {
        "name": body.name,
        "stage": "topic",
        "perspective": body.perspective or "",
        "topic": body.topic or "",
        "created_at": now,
        "last_modified": now,
    }
    # 项目内独立 meta + 全局索引同时更新
    ensure_csv(_project_meta_csv(body.name), PROJECT_META_HEADERS)
    append_row(_project_meta_csv(body.name), PROJECT_META_HEADERS, row)
    upsert_row(
        _projects_index_csv(),
        PROJECTS_INDEX_HEADERS,
        row,
        primary_key="name",
    )
    return {"project": row}


@router.get("/{name}")
def get_project(name: str) -> dict:
    _validate_name(name)
    if not _project_dir(name).exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    rows = filter_rows(_projects_index_csv(), where={"name": name})
    if not rows:
        # 索引丢失时，从项目 meta 兜底
        rows = read_rows(_project_meta_csv(name))
    if not rows:
        raise HTTPException(status_code=404, detail=f"项目元信息缺失：{name}")
    return {"project": rows[-1]}


@router.patch("/{name}")
def update_project(name: str, body: ProjectUpdate) -> dict:
    _validate_name(name)
    if not _project_dir(name).exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    if body.stage is not None and body.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"非法 stage：{body.stage}")
    if body.perspective is not None and body.perspective not in VALID_PERSPECTIVES:
        raise HTTPException(status_code=400, detail=f"非法 perspective：{body.perspective}")

    rows = filter_rows(_projects_index_csv(), where={"name": name})
    base = rows[-1] if rows else {"name": name}
    if body.stage is not None:
        base["stage"] = body.stage
    if body.perspective is not None:
        base["perspective"] = body.perspective
    if body.topic is not None:
        base["topic"] = body.topic
    base["last_modified"] = now_iso()
    base.setdefault("created_at", base["last_modified"])
    upsert_row(
        _projects_index_csv(),
        PROJECTS_INDEX_HEADERS,
        base,
        primary_key="name",
    )
    upsert_row(
        _project_meta_csv(name),
        PROJECT_META_HEADERS,
        base,
        primary_key="name",
    )
    return {"project": base}


@router.delete("/{name}")
def delete_project(name: str) -> dict:
    _validate_name(name)
    proj_dir = _project_dir(name)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    # 仅从索引删除；不物理删除目录（数据安全：用户的资产）
    delete_row(_projects_index_csv(), "name", name)
    return {
        "name": name,
        "deleted_from_index": True,
        "files_kept_at": str(proj_dir),
        "note": "为保护用户数据，项目目录未物理删除。如需彻底清理请手动移除。",
    }
