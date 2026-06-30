"""
搜索源管理 API（SPEC §六：搜索网站 - 用户自定义源）。

数据存储：data_root/config/search_sources.md（Markdown 表格）
铁律 2：仅 Markdown 落盘，禁 JSON。

URL 模板中用 ``{query}`` 占位符表示关键词，前端在拼装最终 iframe URL 时
应做 encodeURIComponent，避免中文/空格破坏 URL。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings


router = APIRouter(prefix="/api/search-sources", tags=["search-sources"])


# ============== 模型 ==============

class SearchSource(BaseModel):
    id: str
    name: str
    url_template: str = ""
    order: int = 0


class SearchSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    url_template: str = ""


class SearchSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    url_template: Optional[str] = None


class ReorderInput(BaseModel):
    ids: list[str]


# ============== 存储 ==============

_HEADER_LINES = [
    "# Search Sources",
    "",
    "PaperAssistant 文献搜索源配置（SPEC §六）。",
    "用户在 \"搜索网站\" 面板可见。URL 模板中用 `{query}` 占位符表示关键词。",
    "",
    "| id | name | url_template | order |",
    "| --- | --- | --- | --- |",
]


def _sources_md() -> Path:
    return get_settings().config_dir / "search_sources.md"


def _escape_cell(s: str) -> str:
    """Markdown 表格 cell 转义：| → \\|，换行 → 空格。"""
    return (
        s.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def _unescape_cell(s: str) -> str:
    return s.strip().replace("\\|", "|").replace("\\\\", "\\")


def _seed_if_missing(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(_HEADER_LINES)
    # 预置 x-mol + cnki，模板留空（用户首次使用时自行填入）
    lines.append("| xmol_default | x-mol |  | 1 |")
    lines.append("| cnki_default | cnki  |  | 2 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_TABLE_DIVIDER_RE = re.compile(r"^\|\s*-+\s*(\|\s*-+\s*)+\|?\s*$")


def _split_row(line: str) -> list[str]:
    """按未转义的 | 切分一行表格。"""
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(trimmed):
        ch = trimmed[i]
        if ch == "\\" and i + 1 < len(trimmed):
            buf.append(trimmed[i : i + 2])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return cells


def _load_all() -> list[SearchSource]:
    path = _sources_md()
    _seed_if_missing(path)
    items: list[SearchSource] = []
    in_table = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not in_table:
            if _TABLE_DIVIDER_RE.match(raw):
                in_table = True
            continue
        if not raw.strip().startswith("|"):
            continue
        cells = _split_row(raw)
        if len(cells) < 4:
            continue
        try:
            order = int(_unescape_cell(cells[3]))
        except ValueError:
            order = 0
        sid = _unescape_cell(cells[0])
        name = _unescape_cell(cells[1])
        if not sid or not name:
            continue
        items.append(
            SearchSource(
                id=sid,
                name=name,
                url_template=_unescape_cell(cells[2]),
                order=order,
            )
        )
    items.sort(key=lambda x: (x.order, x.id))
    return items


def _save_all(items: list[SearchSource]) -> None:
    path = _sources_md()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(_HEADER_LINES)
    for s in items:
        lines.append(
            f"| {_escape_cell(s.id)} | {_escape_cell(s.name)} | {_escape_cell(s.url_template)} | {int(s.order)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _next_id(existing: list[SearchSource]) -> str:
    existing_ids = {s.id for s in existing}
    for _ in range(50):
        new_id = f"src_{uuid.uuid4().hex[:8]}"
        if new_id not in existing_ids:
            return new_id
    # 极小概率分支，做硬性失败而不是静默碰撞
    raise RuntimeError("生成搜索源 ID 失败（uuid 冲突 50 次）")


# ============== 路由 ==============


@router.get("")
def list_sources() -> dict:
    items = _load_all()
    return {"items": [s.model_dump() for s in items]}


@router.post("")
def create_source(body: SearchSourceCreate) -> dict:
    items = _load_all()
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if any(s.name.strip() == new_name for s in items):
        raise HTTPException(status_code=400, detail=f"已存在同名搜索源：{new_name}")
    new = SearchSource(
        id=_next_id(items),
        name=new_name,
        url_template=body.url_template.strip(),
        order=max((s.order for s in items), default=0) + 1,
    )
    items.append(new)
    _save_all(items)
    return {"ok": True, "item": new.model_dump()}


@router.put("/{source_id}")
def update_source(source_id: str, body: SearchSourceUpdate) -> dict:
    items = _load_all()
    target = next((s for s in items if s.id == source_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"未找到搜索源 id={source_id}")
    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="名称不能为空")
        if any(s.id != source_id and s.name.strip() == new_name for s in items):
            raise HTTPException(status_code=400, detail=f"已存在同名搜索源：{new_name}")
        target.name = new_name
    if body.url_template is not None:
        target.url_template = body.url_template.strip()
    _save_all(items)
    return {"ok": True, "item": target.model_dump()}


@router.delete("/{source_id}")
def delete_source(source_id: str) -> dict:
    items = _load_all()
    n_before = len(items)
    items = [s for s in items if s.id != source_id]
    if len(items) == n_before:
        raise HTTPException(status_code=404, detail=f"未找到搜索源 id={source_id}")
    # 删除后顺序仍按现有 order 序列；不强行重排（保持稳定）
    _save_all(items)
    return {"ok": True, "deleted_id": source_id, "remaining": len(items)}


@router.post("/reorder")
def reorder(body: ReorderInput) -> dict:
    items = _load_all()
    id_set = {s.id for s in items}
    if set(body.ids) != id_set:
        raise HTTPException(status_code=400, detail="reorder ids 与现有搜索源不一致")
    order_map = {sid: idx + 1 for idx, sid in enumerate(body.ids)}
    for s in items:
        s.order = order_map[s.id]
    items.sort(key=lambda x: x.order)
    _save_all(items)
    return {"ok": True, "items": [s.model_dump() for s in items]}
