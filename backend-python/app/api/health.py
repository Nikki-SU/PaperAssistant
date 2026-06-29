"""健康检查与基础元信息。"""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "service": "paperassistant-backend",
        "version": "0.1.0",
        "data_root": str(s.data_root),
        "debug_assistant_enabled": s.debug_assistant_enabled,
    }
