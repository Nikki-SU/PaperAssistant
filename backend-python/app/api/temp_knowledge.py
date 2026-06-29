"""临时知识 API（SPEC §5.2 + §8.4）。

数据路径：{data_root}/projects/{name}/temp_knowledge.md

SPEC §5.2 表格：
  - 生命周期：当前对话期间
  - 作用域：仅当前对话
  - 经事实核查：✅（必须）
  - 可继承：✅（可手动转入知识库/文献库）
  - 可删除：✅

铁律 §4.3：写入 temp_knowledge.md 的所有条目都必须经事实核查，audited=true 才能落盘。
本路由仅做「日志型追加」：每条以 ### {时间} · {标题} 形式拼接到文件末尾。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..storage import append_role_memory_entry, read_text, write_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/temp_knowledge", tags=["temp_knowledge"])

_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _safe(name: str) -> str:
    return _SAFE_RE.sub("_", name).strip() or "_unnamed"


def _temp_knowledge_path(project: str) -> Path:
    return get_settings().projects_dir / _safe(project) / "temp_knowledge.md"


def _ensure_seed(path: Path, project: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_text(
        path,
        f"# {project} · 临时知识\n\n"
        f"> 创建时间：{now}\n\n"
        f"_所有条目均已通过事实核查（SPEC §4.3）。_\n",
    )


# ---------------- 模型 ----------------


class TempKnowledgeAppend(BaseModel):
    """SPEC §4.3：写入 temp_knowledge.md 必须 audited=true。"""
    title: str = Field(..., description="条目标题")
    content: str = Field(..., min_length=1, description="知识内容（已通过事实核查的 final_content）")
    source: str = Field("", description="来源文献 DOI / 教材名 / 卡片 id 等")
    section: str = Field("", description="来源章节")
    task_type: str = Field("", description="SPEC §4.3 任务类型，仅作日志标记")
    audited: bool = Field(False, description="必须为 true，否则拒绝写入")


# ---------------- 端点 ----------------


@router.get("/{project}")
def read_temp_knowledge(project: str) -> dict:
    """读取项目临时知识全文。文件不存在则自动种子。"""
    p = _temp_knowledge_path(project)
    _ensure_seed(p, project)
    return {
        "project": project,
        "path": str(p),
        "content": read_text(p),
        "size_bytes": p.stat().st_size if p.exists() else 0,
    }


@router.post("/{project}")
def append_entry(project: str, body: TempKnowledgeAppend) -> dict:
    """SPEC §8.4：往临时知识追加一条已通过事实核查的内容。"""
    if not body.audited:
        raise HTTPException(
            status_code=409,
            detail=(
                "临时知识写入必须 audited=true。"
                "请先 POST /api/ai/verify 取得 verified 结果，再以 audited=true 写入。"
            ),
        )

    p = _temp_knowledge_path(project)
    _ensure_seed(p, project)

    meta = {}
    if body.task_type:
        meta["任务类型"] = body.task_type
    if body.source:
        meta["来源"] = body.source
    if body.section:
        meta["章节"] = body.section
    meta["审阅状态"] = "✅ 已通过"

    append_role_memory_entry(
        p,
        role_label="临时知识",
        title=body.title,
        body=body.content,
        meta=meta,
    )
    return {
        "project": project,
        "path": str(p),
        "appended": True,
        "size_bytes": p.stat().st_size,
    }


@router.post("/{project}/clear")
def clear_temp_knowledge(project: str) -> dict:
    """清空临时知识（保留种子注释行）。SPEC §5.2 表格：可删除。"""
    p = _temp_knowledge_path(project)
    if not p.exists():
        _ensure_seed(p, project)
        return {"project": project, "cleared": False, "note": "原本就不存在，已建立空文件"}
    # 备份到 temp_knowledge.{ts}.md
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = p.with_name(f"temp_knowledge.{ts}.md")
    p.rename(backup)
    _ensure_seed(p, project)
    return {"project": project, "cleared": True, "backup": str(backup)}


@router.delete("/{project}")
def delete_temp_knowledge(project: str) -> dict:
    """彻底删除临时知识文件（不保留备份）。"""
    p = _temp_knowledge_path(project)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"临时知识不存在：{project}")
    p.unlink()
    return {"project": project, "deleted": True}
