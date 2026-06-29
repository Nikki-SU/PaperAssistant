"""排版导出 API。

SPEC §五 + §九：用 Tectonic（内嵌 LaTeX 引擎）+ CSL 输出 PDF。
当前为骨架：
- POST /api/typesetting/{project}/export  → 把 paper/*.md 合并为 manuscript.md 并返回路径
- Tectonic 真实编译留 TODO（云端无法编译；本地由用户安装 Tectonic）
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..storage import now_iso, read_text, write_text

router = APIRouter(prefix="/api/typesetting", tags=["typesetting"])


def _paper_dir(project: str) -> Path:
    return get_settings().projects_dir / project / "paper"


@router.post("/{project}/export")
def export_manuscript(project: str) -> dict:
    paper_dir = _paper_dir(project)
    if not paper_dir.exists():
        raise HTTPException(status_code=404, detail="项目论文目录不存在")
    mds = sorted(paper_dir.glob("*.md"))
    if not mds:
        raise HTTPException(status_code=404, detail="paper/ 下没有任何 Markdown 章节")

    parts: list[str] = [f"<!-- exported_at: {now_iso()} -->\n"]
    for md in mds:
        parts.append(f"\n\n<!-- file: {md.name} -->\n")
        parts.append(read_text(md))
    out = paper_dir / "manuscript.md"
    write_text(out, "\n".join(parts))

    return {
        "project": project,
        "manuscript_path": str(out),
        "chapters": [m.name for m in mds],
        "tectonic": {
            "todo": True,
            "note": "Tectonic 编译为 PDF 留待本地实现；当前仅导出 manuscript.md。",
        },
    }
