"""文献管理 API。

- 上传 PDF → 临时目录 → MinerU 解析为 Markdown → 入库 fulltext + cards.csv
- 查询 / 编辑 / 删除 文献卡片
- 搜索（标题 / 关键词 / 作者 / DOI 子串）

铁律：cards.csv 是唯一结构化主数据；每张卡片同时在 cards/ 下有 ``{doi}.md`` 全文。
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse

from ..config import get_settings
from ..models import LiteratureCard, LiteratureCardCreate
from ..services import MineruClient, auto_summarize_literature
from ..storage import (
    LIT_CSV_HEADERS,
    append_row,
    delete_row,
    ensure_csv,
    filter_rows,
    now_iso,
    read_rows,
    render_literature_card_md,
    upsert_row,
    write_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/literature", tags=["literature"])


_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$")


def _safe_doi_filename(doi: str) -> str:
    """把 DOI 转成安全的文件名（保留 / 用 _ 替代）。"""
    return re.sub(r"[\\/:*?\"<>|]", "_", doi.strip())


def _cards_csv() -> Path:
    p = get_settings().library_cards_csv
    ensure_csv(p, LIT_CSV_HEADERS)
    return p


def _ensure_doi(value: Optional[str], fallback_name: str) -> str:
    """若 DOI 缺失或非法，分配一个 ``local:{uuid}`` 占位主键。"""
    if value:
        v = value.strip().lower()
        if _DOI_RE.match(v):
            return v
    return f"local:{fallback_name}-{uuid.uuid4().hex[:8]}"


@router.get("")
def list_cards(
    q: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 200,
) -> dict:
    rows = read_rows(_cards_csv())
    if category:
        rows = [r for r in rows if r.get("category") == category]
    if q:
        ql = q.lower()
        rows = [
            r for r in rows
            if ql in (r.get("title") or "").lower()
            or ql in (r.get("doi") or "").lower()
            or ql in (r.get("first_author") or "").lower()
            or ql in (r.get("keywords") or "").lower()
        ]
    rows.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return {"cards": rows[:limit], "total": len(rows)}


@router.get("/by-doi/markdown/{doi:path}", response_class=PlainTextResponse)
def get_card_markdown(doi: str) -> str:
    md_path = get_settings().library_cards_dir / f"{_safe_doi_filename(doi)}.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail=f"卡片 Markdown 不存在：{doi}")
    return md_path.read_text(encoding="utf-8")


@router.get("/by-doi/fulltext/{doi:path}", response_class=PlainTextResponse)
def get_card_fulltext(doi: str) -> str:
    full_path = get_settings().library_fulltext_dir / f"{_safe_doi_filename(doi)}.md"
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"全文 Markdown 不存在：{doi}")
    return full_path.read_text(encoding="utf-8")


@router.get("/{doi:path}")
def get_card(doi: str) -> dict:
    rows = filter_rows(_cards_csv(), where={"doi": doi.lower()})
    if not rows:
        raise HTTPException(status_code=404, detail=f"文献不存在：{doi}")
    return {"card": rows[-1]}


@router.post("")
def upsert_card(body: LiteratureCardCreate) -> dict:
    """手动创建 / 更新文献卡片（不上传 PDF 的纯元数据入口）。"""
    doi = body.doi.strip().lower()
    if not doi:
        raise HTTPException(status_code=400, detail="doi 不能为空")

    row: dict = {k: ("" if v is None else v) for k, v in body.model_dump().items()}
    row["doi"] = doi
    row["status"] = row.get("status") or "draft"
    row["last_modified"] = now_iso()
    is_new, merged = upsert_row(_cards_csv(), LIT_CSV_HEADERS, row, primary_key="doi")

    md_path = get_settings().library_cards_dir / f"{_safe_doi_filename(doi)}.md"
    write_text(md_path, render_literature_card_md(merged))
    return {"card": merged, "created": is_new, "markdown_path": str(md_path)}


@router.delete("/{doi:path}")
def delete_card(doi: str) -> dict:
    ok = delete_row(_cards_csv(), "doi", doi.lower())
    if not ok:
        raise HTTPException(status_code=404, detail=f"文献不存在：{doi}")
    # 文件采取「保留 + 标记」策略，避免误删
    return {"doi": doi, "deleted_from_index": True}


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    doi: str = Query("", description="可选；不传则分配 local: 主键"),
    title: str = Query(""),
    project: str = Query("", description="项目名；非空且 MinerU 成功时触发自动总结链路"),
) -> dict:
    """上传 PDF：
    1. 临时存到 temp/monitor/
    2. 交给 MinerU client（当前为 stub）解析为 Markdown，落到 library/fulltext/{doi}.md
    3. 同步写一条 cards.csv 行 + cards/{doi}.md 卡片
    """
    settings = get_settings()
    settings.ensure_dirs()

    raw_name = Path(file.filename or "uploaded.pdf").name
    temp_path = settings.monitor_dir / f"{uuid.uuid4().hex[:8]}-{raw_name}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    final_doi = _ensure_doi(doi, fallback_name=Path(raw_name).stem)
    safe = _safe_doi_filename(final_doi)
    fulltext_path = settings.library_fulltext_dir / f"{safe}.md"

    mineru = MineruClient()
    result = mineru.parse(temp_path, fulltext_path)

    row: dict = {h: "" for h in LIT_CSV_HEADERS}
    row.update(
        {
            "doi": final_doi,
            "title": title or Path(raw_name).stem,
            "status": "ingested" if result.success else "failed",
            "last_modified": now_iso(),
        }
    )
    is_new, merged = upsert_row(_cards_csv(), LIT_CSV_HEADERS, row, primary_key="doi")
    card_md = settings.library_cards_dir / f"{safe}.md"
    write_text(card_md, render_literature_card_md(merged))

    # ---- 自动总结链路（SPEC §七.2）：MinerU 成功且指定了 project 时触发 ----
    auto_summary_info: dict = {"status": "skipped", "message": "未触发"}
    if result.success and project:
        try:
            asr = auto_summarize_literature(
                project=project,
                doi=final_doi,
                title=row["title"],
                fulltext_md_path=fulltext_path,
            )
            auto_summary_info = {
                "status": asr.status,
                "title": asr.title,
                "doi": asr.doi,
                "summary_chars": asr.summary_chars,
                "audit_rounds": asr.audit_rounds,
                "audit_log_path": asr.audit_log_path,
                "temp_knowledge_path": asr.temp_knowledge_path,
                "chunks_total": asr.chunks_total,
                "message": asr.message,
                "error_code": asr.error_code,
                "meta": asr.meta,
            }
        except Exception as exc:
            logger.exception("[upload] auto_summarize 异常（已降级）：%s", exc)
            auto_summary_info = {
                "status": "error",
                "message": f"auto_summarize 异常：{exc}",
                "error_code": "exception",
            }

    return {
        "card": merged,
        "created": is_new,
        "fulltext_path": str(fulltext_path),
        "card_markdown_path": str(card_md),
        "mineru": {
            "success": result.success,
            "message": result.message,
            "page_count": result.page_count,
            "truncated": result.truncated,
        },
        "auto_summary": auto_summary_info,
        "temp_pdf": str(temp_path),
    }
