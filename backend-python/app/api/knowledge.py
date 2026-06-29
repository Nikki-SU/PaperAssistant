"""知识库 API（SPEC §五.1 + §八.2）。

数据目录：
    {data_root}/knowledge/
    ├── {学科}/
    │   ├── textbooks/
    │   │   └── {课本名}.md          # 课本全文
    │   └── cards/
    │       ├── {card_id}.md         # 卡片正文
    │       └── cards.csv            # 学科级卡片索引
    └── _index.csv                   # 全学科卡片总索引

端点：
- 学科 / 课本：GET /api/knowledge/subjects、GET /api/knowledge/textbooks?subject=xxx
- 课本 PDF 上传 → MinerU → 落 knowledge/{subject}/textbooks/{name}.md：POST /api/knowledge/textbook
- 卡片：GET /api/knowledge | POST /api/knowledge | GET /api/knowledge/{card_id} | DELETE /api/knowledge/{card_id}
- 卡片正文 MD：GET /api/knowledge/by-id/markdown/{card_id}

铁律 §4.3：知识库卡片属于「必须经事实核查」的 6 类之一。
本路由本身不内嵌 verify 流程；调用方需通过 POST /api/ai/verify 取得 verified 结果，
然后用 audited=true 写入；upsert 时若 audited≠true 会被拒绝，避免污染知识库。
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..config import get_settings
from ..models import KNOWLEDGE_CSV_HEADERS, KnowledgeCard, KnowledgeCardCreate
from ..services import MineruClient
from ..storage import (
    append_row,
    delete_row,
    ensure_csv,
    filter_rows,
    now_iso,
    read_rows,
    render_knowledge_card_md,
    upsert_row,
    write_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_SAFE_SUBJECT_RE = re.compile(r"^[\w\-. \u4e00-\u9fa5]{1,40}$")
_SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|]')


def _knowledge_root() -> Path:
    return get_settings().knowledge_dir


def _global_cards_csv() -> Path:
    p = _knowledge_root() / "_index.csv"
    ensure_csv(p, KNOWLEDGE_CSV_HEADERS)
    return p


def _subject_dir(subject: str) -> Path:
    return _knowledge_root() / subject


def _subject_textbooks_dir(subject: str) -> Path:
    return _subject_dir(subject) / "textbooks"


def _subject_cards_dir(subject: str) -> Path:
    return _subject_dir(subject) / "cards"


def _subject_cards_csv(subject: str) -> Path:
    p = _subject_cards_dir(subject) / "cards.csv"
    ensure_csv(p, KNOWLEDGE_CSV_HEADERS)
    return p


def _validate_subject(subject: str) -> None:
    if not subject or not _SAFE_SUBJECT_RE.match(subject):
        raise HTTPException(status_code=400, detail=f"非法学科名：{subject!r}")


def _safe_filename(name: str) -> str:
    return _SAFE_NAME_RE.sub("_", name).strip()


# ---------------- 学科 / 课本 ----------------


@router.get("/subjects")
def list_subjects() -> dict:
    """列出 knowledge/ 下已建立的学科目录。"""
    root = _knowledge_root()
    if not root.exists():
        return {"subjects": []}
    items = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        textbooks = []
        tb_dir = d / "textbooks"
        if tb_dir.exists():
            textbooks = [p.name for p in sorted(tb_dir.iterdir()) if p.suffix == ".md"]
        cards_count = 0
        cards_csv = d / "cards" / "cards.csv"
        if cards_csv.exists():
            cards_count = len(read_rows(cards_csv))
        items.append({
            "subject": d.name,
            "textbook_count": len(textbooks),
            "card_count": cards_count,
        })
    return {"subjects": items}


@router.post("/subjects")
def create_subject(subject: str = Query(..., description="学科名")) -> dict:
    _validate_subject(subject)
    _subject_textbooks_dir(subject).mkdir(parents=True, exist_ok=True)
    _subject_cards_dir(subject).mkdir(parents=True, exist_ok=True)
    ensure_csv(_subject_cards_csv(subject), KNOWLEDGE_CSV_HEADERS)
    return {"subject": subject, "created": True}


@router.get("/textbooks")
def list_textbooks(subject: str = Query(..., description="学科名")) -> dict:
    _validate_subject(subject)
    d = _subject_textbooks_dir(subject)
    if not d.exists():
        return {"subject": subject, "textbooks": []}
    items = []
    for p in sorted(d.iterdir()):
        if p.suffix != ".md":
            continue
        items.append({
            "name": p.stem,
            "filename": p.name,
            "size_bytes": p.stat().st_size,
        })
    return {"subject": subject, "textbooks": items}


@router.get("/textbooks/{subject}/{name}", response_class=PlainTextResponse)
def get_textbook(subject: str, name: str) -> str:
    _validate_subject(subject)
    safe_name = _safe_filename(name)
    if not safe_name.endswith(".md"):
        safe_name += ".md"
    p = _subject_textbooks_dir(subject) / safe_name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"课本不存在：{subject}/{name}")
    return p.read_text(encoding="utf-8")


@router.post("/textbook")
async def upload_textbook(
    subject: str = Form(..., description="学科名"),
    name: str = Form("", description="可选课本显示名，缺省取 PDF 文件名"),
    file: UploadFile = File(...),
) -> dict:
    """SPEC §7.1：上传课本/教材 PDF → MinerU → knowledge/{subject}/textbooks/{name}.md。"""
    _validate_subject(subject)
    raw_name = Path(file.filename or "untitled.pdf").name
    display_name = name.strip() or Path(raw_name).stem

    # 把 PDF 暂存到 temp/monitor/
    settings = get_settings()
    temp_path = settings.monitor_dir / f"{uuid.uuid4().hex[:8]}-{raw_name}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    # 落地路径
    safe_display = _safe_filename(display_name) or "untitled"
    target_md = _subject_textbooks_dir(subject) / f"{safe_display}.md"
    target_md.parent.mkdir(parents=True, exist_ok=True)

    # 走 MinerU
    mineru = MineruClient()
    result = mineru.parse(temp_path, target_md)

    return {
        "subject": subject,
        "name": display_name,
        "markdown_path": str(target_md),
        "temp_pdf": str(temp_path),
        "mineru": {
            "success": result.success,
            "message": result.message,
            "page_count": result.page_count,
            "truncated": result.truncated,
        },
    }


@router.delete("/textbooks/{subject}/{name}")
def delete_textbook(subject: str, name: str) -> dict:
    _validate_subject(subject)
    safe_name = _safe_filename(name)
    if not safe_name.endswith(".md"):
        safe_name += ".md"
    p = _subject_textbooks_dir(subject) / safe_name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"课本不存在：{subject}/{name}")
    # 不物理删除，重命名为 .deleted 以保留历史
    backup = p.with_suffix(p.suffix + ".deleted")
    p.rename(backup)
    return {"subject": subject, "name": name, "deleted": True, "backup": str(backup)}


# ---------------- 卡片 ----------------


class KnowledgeCardUpsert(BaseModel):
    """卡片创建/更新入参。

    SPEC §4.3 铁律：知识库卡片必须经事实核查，audited=true 才能入库。
    若 audited=false，本端点直接拒绝（避免业务侧绕过守卫）。
    """
    card_id: Optional[str] = None  # 不传则自动生成
    subject: str
    title: str
    prompt: str = ""
    summary: str = ""
    source_book: str = ""
    source_section: str = ""
    audited: bool = False


@router.get("")
def list_cards(
    subject: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
) -> dict:
    """列卡片。优先从学科级 cards.csv 读，未指定学科时聚合全部学科。"""
    if subject:
        _validate_subject(subject)
        rows = read_rows(_subject_cards_csv(subject))
    else:
        rows = []
        root = _knowledge_root()
        if root.exists():
            for d in sorted(root.iterdir()):
                if not d.is_dir():
                    continue
                cards_csv = d / "cards" / "cards.csv"
                if cards_csv.exists():
                    rows.extend(read_rows(cards_csv))
    if q:
        ql = q.lower()
        rows = [
            r for r in rows
            if ql in (r.get("title") or "").lower()
            or ql in (r.get("prompt") or "").lower()
            or ql in (r.get("summary") or "").lower()
        ]
    rows.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return {"cards": rows[:limit], "total": len(rows)}


@router.get("/by-id/markdown/{card_id}", response_class=PlainTextResponse)
def get_card_markdown(card_id: str) -> str:
    rows = filter_rows(_global_cards_csv(), where={"card_id": card_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"卡片不存在：{card_id}")
    subject = rows[-1].get("subject", "")
    if not subject:
        raise HTTPException(status_code=500, detail="卡片索引缺 subject 字段")
    p = _subject_cards_dir(subject) / f"{card_id}.md"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"卡片 Markdown 不存在：{card_id}")
    return p.read_text(encoding="utf-8")


@router.get("/{card_id}")
def get_card(card_id: str) -> dict:
    rows = filter_rows(_global_cards_csv(), where={"card_id": card_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"卡片不存在：{card_id}")
    return {"card": rows[-1]}


@router.post("")
def upsert_card(body: KnowledgeCardUpsert) -> dict:
    """创建/更新知识库卡片。

    SPEC §4.3：必须 audited=true（即调用方已通过事实核查）才能入库。
    """
    _validate_subject(body.subject)

    if not body.audited:
        raise HTTPException(
            status_code=409,
            detail=(
                "知识库卡片必须经事实核查（audited=true）。"
                "请先调用 POST /api/ai/verify 验证 summary，"
                "通过后再以 audited=true 写入。"
            ),
        )

    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title 不能为空")
    if not body.summary.strip():
        raise HTTPException(status_code=400, detail="summary 不能为空")

    card_id = (body.card_id or "").strip() or f"k-{uuid.uuid4().hex[:10]}"
    row: dict = {
        "card_id": card_id,
        "subject": body.subject,
        "title": body.title,
        "prompt": body.prompt,
        "summary": body.summary,
        "audited": "true",
        "source_book": body.source_book,
        "source_section": body.source_section,
        "last_modified": now_iso(),
    }

    # 学科级 + 全局 双索引
    _subject_textbooks_dir(body.subject).mkdir(parents=True, exist_ok=True)
    _subject_cards_dir(body.subject).mkdir(parents=True, exist_ok=True)
    is_new_subj, merged_subj = upsert_row(
        _subject_cards_csv(body.subject), KNOWLEDGE_CSV_HEADERS, row, primary_key="card_id"
    )
    is_new_global, _ = upsert_row(
        _global_cards_csv(), KNOWLEDGE_CSV_HEADERS, row, primary_key="card_id"
    )

    md_path = _subject_cards_dir(body.subject) / f"{card_id}.md"
    write_text(md_path, render_knowledge_card_md(merged_subj))

    return {
        "card": merged_subj,
        "created": is_new_subj or is_new_global,
        "markdown_path": str(md_path),
    }


@router.delete("/{card_id}")
def delete_card(card_id: str) -> dict:
    rows = filter_rows(_global_cards_csv(), where={"card_id": card_id})
    if not rows:
        raise HTTPException(status_code=404, detail=f"卡片不存在：{card_id}")
    subject = rows[-1].get("subject", "")
    delete_row(_global_cards_csv(), "card_id", card_id)
    if subject:
        delete_row(_subject_cards_csv(subject), "card_id", card_id)
    return {"card_id": card_id, "subject": subject, "deleted_from_index": True}
