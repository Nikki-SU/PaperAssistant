"""知识库卡片 Pydantic 模型（SPEC §八.2）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


KNOWLEDGE_CSV_HEADERS = [
    "card_id", "subject", "title", "prompt",
    "summary", "audited", "source_book", "source_section",
    "last_modified",
]


class KnowledgeCard(BaseModel):
    card_id: str
    subject: str
    title: str = ""
    prompt: str = ""
    summary: str = ""
    audited: bool = False  # 是否已通过事实核查
    source_book: str = ""
    source_section: str = ""
    last_modified: str = ""

    def to_row(self) -> dict[str, str]:
        d = self.model_dump()
        d["audited"] = "true" if self.audited else "false"
        return {k: ("" if v is None else str(v)) for k, v in d.items()}


class KnowledgeCardCreate(BaseModel):
    subject: str
    title: str
    prompt: str = ""
    summary: str = ""
    source_book: Optional[str] = None
    source_section: Optional[str] = None
