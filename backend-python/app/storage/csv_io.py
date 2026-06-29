"""通用 CSV 读写工具。

所有结构化数据（文献卡片 / 知识库卡片 / 引用选择 / 大类配置）都走这里，
保持「单一存储 = 单一格式 = 单一函数」的纪律。

铁律：CSV 是落盘格式，不退化为 JSON。
"""
from __future__ import annotations

import csv
import io
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

_LOCK = threading.Lock()


def ensure_csv(path: Path, headers: list[str]) -> None:
    """若文件不存在则建立带表头的空 CSV。"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)


def read_rows(path: Path) -> list[dict[str, str]]:
    """读取 CSV 全部行（按表头对齐返回 dict 列表）。"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [{k: (v or "") for k, v in r.items()} for r in reader]


def append_row(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    """追加一行；自动补齐表头。"""
    with _LOCK:
        ensure_csv(path, headers)
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([_to_cell(row.get(h, "")) for h in headers])


def upsert_row(
    path: Path,
    headers: list[str],
    row: dict[str, Any],
    *,
    primary_key: str,
) -> tuple[bool, dict[str, str]]:
    """按 primary_key 更新或新建一行。返回 (is_new, 行内容)。"""
    pk_val = str(row.get(primary_key, "")).strip()
    if not pk_val:
        raise ValueError(f"primary_key {primary_key} 不能为空")
    with _LOCK:
        rows = read_rows(path)
        out: list[dict[str, str]] = []
        found = False
        merged: dict[str, str] = {}
        for r in rows:
            if r.get(primary_key) == pk_val:
                merged = dict(r)
                for k, v in row.items():
                    merged[k] = _to_cell(v)
                out.append(merged)
                found = True
            else:
                out.append(r)
        if not found:
            merged = {h: _to_cell(row.get(h, "")) for h in headers}
            out.append(merged)
        _write_all(path, headers, out)
        return (not found), merged


def delete_row(path: Path, primary_key: str, value: str) -> bool:
    """按主键删除一行；返回是否删除成功。"""
    with _LOCK:
        rows = read_rows(path)
        new_rows = [r for r in rows if r.get(primary_key) != value]
        if len(new_rows) == len(rows):
            return False
        if not rows:
            return False
        headers = list(rows[0].keys())
        _write_all(path, headers, new_rows)
        return True


def filter_rows(
    path: Path,
    *,
    where: Optional[dict[str, str]] = None,
    contains: Optional[dict[str, str]] = None,
) -> list[dict[str, str]]:
    """简单过滤：where 精确匹配，contains 子串包含。"""
    rows = read_rows(path)
    if where:
        for k, v in where.items():
            rows = [r for r in rows if r.get(k) == v]
    if contains:
        for k, v in contains.items():
            lv = v.lower()
            rows = [r for r in rows if lv in (r.get(k) or "").lower()]
    return rows


def _to_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    return str(v)


def _write_all(path: Path, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({h: _to_cell(r.get(h, "")) for h in headers})
    path.write_text(buf.getvalue(), encoding="utf-8")
