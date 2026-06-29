"""CSV 读写。

适用：文献卡片、知识库卡片、大类配置、自定义字段、引用选择记录。
"""
from __future__ import annotations
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    """读 CSV，返回字典列表。"""
    # TODO
    raise NotImplementedError


def write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    """原子写 CSV（写临时文件 → 替换）。"""
    # TODO
    raise NotImplementedError


def upsert_row(path: Path, row: dict, key_field: str) -> None:
    """按 key 插入或更新一行。"""
    # TODO
    raise NotImplementedError
