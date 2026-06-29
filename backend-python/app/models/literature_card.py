"""文献卡片 Pydantic 模型（SPEC §八.1）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LiteratureCard(BaseModel):
    """对应 CSV 的列 + 一些 API 用的派生字段。"""

    doi: str = Field(..., description="主键，文献的 DOI（小写）")
    title: str = ""
    journal: str = ""
    first_author: str = ""
    corresponding_author: str = ""
    keywords: str = ""
    abstract: str = ""
    category: str = ""
    subcategory: str = ""

    # 社科视角
    theory: str = ""
    experiment_design: str = ""
    data: str = ""
    results: str = ""
    policy_suggestions: str = ""

    # 理科视角
    experiment: str = ""
    characterization: str = ""
    mechanism: str = ""
    application: str = ""

    # 自定义
    custom_fields: str = ""

    # 元信息
    status: str = "draft"
    last_modified: str = ""

    def to_row(self) -> dict[str, str]:
        return {k: ("" if v is None else str(v)) for k, v in self.model_dump().items()}


class LiteratureCardCreate(BaseModel):
    """API 入参：创建/更新文献卡片。doi 必填，其他可选。"""

    doi: str
    title: Optional[str] = None
    journal: Optional[str] = None
    first_author: Optional[str] = None
    corresponding_author: Optional[str] = None
    keywords: Optional[str] = None
    abstract: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    theory: Optional[str] = None
    experiment_design: Optional[str] = None
    data: Optional[str] = None
    results: Optional[str] = None
    policy_suggestions: Optional[str] = None
    experiment: Optional[str] = None
    characterization: Optional[str] = None
    mechanism: Optional[str] = None
    application: Optional[str] = None
    custom_fields: Optional[str] = None
    status: Optional[str] = None
