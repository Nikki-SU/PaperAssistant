"""项目管理 API（SPEC §五.1 + §7.1）。

数据目录结构：
data_root/projects/{name}/
├── memories/
│   ├── assistant.md   ← 助手 AI 的所有输出
│   ├── reviewer.md    ← 审阅 AI 的审计日志
│   └── secretary.md   ← 秘书 AI 的审阅记录
├── temp_knowledge.md  ← 当前对话期间的临时知识缓存
├── paper/
│   ├── draft.md       ← 论文正文
│   └── images/
├── citations/
│   └── selected.csv   ← 本项目最终引用清单
└── meta.csv           ← 单行 CSV：项目元信息

项目名称：
- 创建时可不传 name，自动用 ``未命名-{时间戳}`` 占位
- 选题阶段第 8 步用户选定后，调用 PATCH /api/project/{old}/rename 改名
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
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
    write_text,
)

router = APIRouter(prefix="/api/project", tags=["project"])

PROJECTS_INDEX_HEADERS = [
    "name", "stage", "perspective", "topic", "created_at", "last_modified",
]
PROJECT_META_HEADERS = PROJECTS_INDEX_HEADERS

CITATIONS_HEADERS = ["doi", "label", "used_in", "note", "added_at"]

VALID_STAGES = ["topic", "review", "writing", "citation", "typesetting"]
VALID_PERSPECTIVES = ["", "social", "science"]

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


def _placeholder_name() -> str:
    return "未命名-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _seed_project_files(proj_dir: Path, name: str, created_at: str) -> None:
    """SPEC §5.1：种下三角色记忆 + 临时知识 + 论文草稿 + 引用清单。"""
    (proj_dir / "memories").mkdir(parents=True, exist_ok=True)
    (proj_dir / "paper" / "images").mkdir(parents=True, exist_ok=True)
    (proj_dir / "citations").mkdir(parents=True, exist_ok=True)

    memories = {
        "assistant.md": (
            f"# {name} · 助手记忆\n\n"
            f"> 角色：助手 AI（主要输出）\n"
            f"> 创建时间：{created_at}\n\n"
            f"_此文件记录助手 AI 在本项目中的所有输出。_\n"
        ),
        "reviewer.md": (
            f"# {name} · 审阅记忆\n\n"
            f"> 角色：审阅 AI（事实核查日志）\n"
            f"> 创建时间：{created_at}\n\n"
            f"_此文件记录每一轮审阅的判定与依据。SPEC §4.3。_\n"
        ),
        "secretary.md": (
            f"# {name} · 秘书记忆\n\n"
            f"> 角色：秘书 AI（错别字/语法修正记录）\n"
            f"> 创建时间：{created_at}\n\n"
            f"_此文件记录秘书 AI 的修订建议与采纳情况。_\n"
        ),
    }
    for fname, content in memories.items():
        write_text(proj_dir / "memories" / fname, content)

    write_text(
        proj_dir / "temp_knowledge.md",
        f"# {name} · 临时知识\n\n"
        f"> 创建时间：{created_at}\n\n"
        f"_此文件存放当前对话中已经过事实核查的临时知识。SPEC §5.2。_\n"
        f"_对话结束后可清空或归档到知识库/文献库。_\n",
    )

    write_text(
        proj_dir / "paper" / "draft.md",
        f"# {name}\n\n"
        f"<!-- 创建时间：{created_at} -->\n\n"
        f"<!-- 正文从这里开始。引用使用 [@doi:xxx] 标记，排版阶段会替换。 -->\n",
    )

    citations_csv = proj_dir / "citations" / "selected.csv"
    ensure_csv(citations_csv, CITATIONS_HEADERS)


class ProjectCreate(BaseModel):
    name: str = ""           # 可空：自动用占位名
    topic: str = ""
    perspective: str = ""    # social / science / ""


class ProjectUpdate(BaseModel):
    stage: str | None = None
    perspective: str | None = None
    topic: str | None = None


class ProjectRename(BaseModel):
    new_name: str



def _decorate_project(row: dict) -> dict:
    """给 project dict 附加 is_placeholder_name 标志，供前端 UI 用。"""
    out = dict(row)
    out["is_placeholder_name"] = bool(out.get("name", "").startswith("未命名-"))
    return out


@router.get("")
def list_projects() -> dict:
    ensure_csv(_projects_index_csv(), PROJECTS_INDEX_HEADERS)
    rows = read_rows(_projects_index_csv())
    rows.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return {"projects": [_decorate_project(r) for r in rows]}


@router.post("")
def create_project(body: ProjectCreate) -> dict:
    name = body.name.strip() or _placeholder_name()
    _validate_name(name)
    if body.perspective and body.perspective not in VALID_PERSPECTIVES:
        raise HTTPException(status_code=400, detail=f"非法 perspective：{body.perspective}")
    proj_dir = _project_dir(name)
    if proj_dir.exists():
        raise HTTPException(status_code=409, detail=f"项目已存在：{name}")

    now = now_iso()
    _seed_project_files(proj_dir, name, now)

    row = {
        "name": name,
        "stage": "topic",
        "perspective": body.perspective or "",
        "topic": body.topic or "",
        "created_at": now,
        "last_modified": now,
    }
    ensure_csv(_project_meta_csv(name), PROJECT_META_HEADERS)
    append_row(_project_meta_csv(name), PROJECT_META_HEADERS, row)
    upsert_row(_projects_index_csv(), PROJECTS_INDEX_HEADERS, row, primary_key="name")
    return {"project": _decorate_project(row), "is_placeholder_name": name.startswith("未命名-")}


@router.get("/{name}")
def get_project(name: str) -> dict:
    _validate_name(name)
    if not _project_dir(name).exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    rows = filter_rows(_projects_index_csv(), where={"name": name})
    if not rows:
        rows = read_rows(_project_meta_csv(name))
    if not rows:
        raise HTTPException(status_code=404, detail=f"项目元信息缺失：{name}")
    return {"project": _decorate_project(rows[-1])}


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
    upsert_row(_projects_index_csv(), PROJECTS_INDEX_HEADERS, base, primary_key="name")
    upsert_row(_project_meta_csv(name), PROJECT_META_HEADERS, base, primary_key="name")
    return {"project": base}


@router.post("/{name}/rename")
def rename_project(name: str, body: ProjectRename) -> dict:
    """选题阶段第 8 步：选定选题后给项目改名。

    SPEC §7.1: "用户选择/自定选题 → 项目名称自动更新"
    """
    _validate_name(name)
    new_name = body.new_name.strip()
    _validate_name(new_name)
    if new_name == name:
        return {"project": _decorate_project(filter_rows(_projects_index_csv(), where={"name": name})[-1]), "renamed": False, "old_name": name, "new_name": name}

    old_dir = _project_dir(name)
    new_dir = _project_dir(new_name)
    if not old_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    if new_dir.exists():
        raise HTTPException(status_code=409, detail=f"目标名称已存在：{new_name}")

    shutil.move(str(old_dir), str(new_dir))

    rows = filter_rows(_projects_index_csv(), where={"name": name})
    base = rows[-1] if rows else {"name": new_name, "stage": "topic"}
    base["name"] = new_name
    base["last_modified"] = now_iso()
    delete_row(_projects_index_csv(), "name", name)
    upsert_row(_projects_index_csv(), PROJECTS_INDEX_HEADERS, base, primary_key="name")
    # meta.csv 在项目目录里，重写一份
    ensure_csv(_project_meta_csv(new_name), PROJECT_META_HEADERS)
    upsert_row(_project_meta_csv(new_name), PROJECT_META_HEADERS, base, primary_key="name")

    return {"project": _decorate_project(base), "renamed": True, "old_name": name, "new_name": base["name"]}


@router.delete("/{name}")
def delete_project(name: str) -> dict:
    _validate_name(name)
    proj_dir = _project_dir(name)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在：{name}")
    delete_row(_projects_index_csv(), "name", name)
    return {
        "name": name,
        "deleted_from_index": True,
        "files_kept_at": str(proj_dir),
        "note": "为保护用户数据，项目目录未物理删除。如需彻底清理请手动移除。",
    }
