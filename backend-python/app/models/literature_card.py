"""文献卡片数据模型。

对应 SPEC：项目二 §八.1 文献卡片
CSV 字段：doi, title, journal, first_author, corresponding_author,
         keywords, abstract, category, subcategory, theory,
         experiment_design, data, results, policy_suggestions,
         experiment, characterization, mechanism, application,
         custom_fields, status, last_modified
"""
from __future__ import annotations
from pydantic import BaseModel, Field


class LiteratureCard(BaseModel):
    doi: str
    title: str
    journal: str
    first_author: str
    corresponding_author: str = ""
    keywords: list[str] = Field(default_factory=list)
    abstract: str = ""
    category: str = ""  # 大类
    subcategory: str = ""
    theory: str = ""
    experiment_design: str = ""
    data: str = ""
    results: str = ""
    policy_suggestions: str = ""
    experiment: str = ""
    characterization: str = ""
    mechanism: str = ""
    application: str = ""
    custom_fields: dict[str, str] = Field(default_factory=dict)
    status: str = "draft"  # draft / reviewed
    last_modified: str = ""
