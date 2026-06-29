"""Markdown 读写。

适用：文献全文、课本全文、论文正文、记忆、临时知识、LaTeX 模板、卡片内容。
"""
from __future__ import annotations
from pathlib import Path


def read_markdown(path: Path) -> str:
    """读 Markdown 文件。"""
    return path.read_text(encoding="utf-8")


def write_markdown(path: Path, content: str) -> None:
    """写 Markdown 文件（原子写）。"""
    # TODO: 原子写 + 自动创建父目录
    raise NotImplementedError


def append_markdown(path: Path, content: str) -> None:
    """追加内容到 Markdown 末尾（用于记忆文件）。"""
    # TODO
    raise NotImplementedError


def parse_card_markdown(path: Path) -> dict:
    """解析卡片 Markdown（formatter + body）→ 字段字典。
    
    用于卡片 Markdown ↔ CSV 双向同步。
    """
    # TODO: 简单 YAML frontmatter 解析
    raise NotImplementedError
