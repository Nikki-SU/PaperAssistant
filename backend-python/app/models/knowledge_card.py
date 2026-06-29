"""知识库卡片数据模型。

对应 SPEC：项目二 §八.2 知识库卡片
"""
from __future__ import annotations
from pydantic import BaseModel, Field


class KnowledgeCard(BaseModel):
    card_id: str
    subject: str  # 学科
    textbook: str  # 教材名
    title: str
    user_prompt: str  # 用户自定义提示词
    content: str  # AI 提取的内容（已经过事实核查）
    source_excerpt: str  # 原文佐证片段
    audit_log: str = ""  # 审计日志（reviewer.md 摘要）
    status: str = "reviewed"
    last_modified: str = ""
