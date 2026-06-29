"""文件监控 API（SPEC §九：监控目录自动检测）。

- GET /api/file_watcher/status  → 运行状态、监控目录、已处理项数
- POST /api/file_watcher/start  → 启动监控
- POST /api/file_watcher/stop   → 停止监控
- POST /api/file_watcher/scan   → 手动触发一次全量扫描
- GET /api/file_watcher/processed → 列已处理记录
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..services.file_watcher import (
    PROCESSED_INDEX_NAME,
    get_watcher,
    start_watcher,
    stop_watcher,
)

router = APIRouter(prefix="/api/file_watcher", tags=["file_watcher"])


@router.get("/status")
def status() -> dict:
    w = get_watcher()
    return {
        "running": w.is_running(),
        "monitor_dir": str(w.monitor_dir),
        "output_root": str(w.output_root),
        "processed_count": len(w._processed),  # noqa: SLF001
        "mineru_configured": w.mineru.enabled,
    }


@router.post("/start")
def start() -> dict:
    start_watcher()
    return {"ok": True, "running": True}


@router.post("/stop")
def stop() -> dict:
    stop_watcher()
    return {"ok": True, "running": False}


@router.post("/scan")
def scan() -> dict:
    """手动触发一次扫描。"""
    w = get_watcher()
    if not w.is_running():
        # 允许未启动时也可扫描
        w.monitor_dir.mkdir(parents=True, exist_ok=True)
        if not w._processed:  # noqa: SLF001
            from ..services.file_watcher import _read_processed_index
            w._processed = _read_processed_index(w.monitor_dir)  # noqa: SLF001
    count = w.trigger_scan()
    return {"ok": True, "processed_this_round": count}


@router.get("/processed")
def list_processed(limit: int = 200) -> dict:
    s = get_settings()
    idx = s.monitor_dir / PROCESSED_INDEX_NAME
    if not idx.exists():
        return {"items": [], "total": 0}
    items: list[dict] = []
    try:
        with open(idx, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            items = list(reader)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取索引失败：{e}")
    items = items[-limit:][::-1]  # 最近的在前
    return {"items": items, "total": len(items)}
