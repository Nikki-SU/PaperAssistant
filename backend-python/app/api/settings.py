"""设置接口（SPEC §四.5 / §五.1）。

提供给前端的全局设置 API：
- 数据根目录切换（写指针 + 重建 settings）
- 监控目录设置
- 4 个 AI 接口位（mineru/assistant/auditor/secretary）—— 不返回明文 key
- 分类配置 / 自定义字段
- API Key 实际值用独立 secret 文件保存（不落 csv，避免明文落盘）

设计纪律：
- 所有 config 都在 data_root/config/*.csv（落盘 CSV）
- API Key 单独放 data_root/config/api_keys.secret（600 权限）
- GET 返回的 api_config 永远只给 api_key_set=true/false，不返明文
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import (
    APP_CONFIG_HEADERS,
    API_CONFIG_HEADERS,
    CATEGORY_CONFIG_HEADERS,
    CUSTOM_FIELDS_HEADERS,
    DEFAULT_API_ROLES,
    get_settings,
    set_data_root,
)
from ..storage import read_rows, upsert_row

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ============== 模型 ==============

class SettingsSnapshot(BaseModel):
    data_root: str
    monitor_dir: str
    is_default_root: bool
    pointer_file: str
    api_roles: list[dict]
    categories: list[dict]
    custom_fields: list[dict]


class DataRootUpdate(BaseModel):
    path: str = Field(..., min_length=1, description="新的数据根目录绝对路径")


class MonitorDirUpdate(BaseModel):
    path: str = Field(..., min_length=1, description="监控目录绝对路径")


class ApiConfigUpdate(BaseModel):
    role: str = Field(..., description="mineru / assistant / auditor / secretary")
    endpoint: str = ""
    model: str = ""
    api_key: Optional[str] = Field(None, description="新 API Key 明文；不传则保持原值")
    timeout: int = 120


class CategoryUpdate(BaseModel):
    perspective: str
    category: str
    subcategory: str = ""


class CategoryBatch(BaseModel):
    items: list[CategoryUpdate]


class CustomField(BaseModel):
    field_name: str
    field_type: str = "text"
    description: str = ""


class CustomFieldsBatch(BaseModel):
    items: list[CustomField]


# ============== 工具 ==============

_VALID_ROLES = {"mineru", "assistant", "auditor", "secretary"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _secret_path() -> Path:
    return get_settings().config_dir / "api_keys.secret"


def _read_secrets() -> dict[str, str]:
    p = _secret_path()
    out: dict[str, str] = {}
    if not p.exists():
        return out
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    except Exception:
        return out
    return out


def _write_secrets(values: dict[str, str]) -> None:
    p = _secret_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items() if v]
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


def _default_root_str() -> str:
    home_docs = Path.home() / "Documents"
    if home_docs.exists():
        return str((home_docs / "PaperAssistant").resolve())
    return str((Path.home() / "PaperAssistant").resolve())


def _is_default_root(p: Path) -> bool:
    try:
        return Path(_default_root_str()).resolve() == p.resolve()
    except Exception:
        return False


def _read_api_config_full() -> list[dict]:
    s = get_settings()
    rows = read_rows(s.api_config_csv)
    secrets = _read_secrets()
    by_role = {r["role"]: r for r in rows}

    out: list[dict] = []
    for default in DEFAULT_API_ROLES:
        role = default["role"]
        existing = by_role.get(role, default)
        out.append({
            "role": role,
            "endpoint": existing.get("endpoint", "") or "",
            "model": existing.get("model", "") or "",
            "api_key_set": bool(secrets.get(role)),
            "timeout": existing.get("timeout", default["timeout"]) or default["timeout"],
            "last_modified": existing.get("last_modified", "") or "",
        })
    return out


# ============== 路由 ==============

@router.get("", response_model=SettingsSnapshot)
@router.get("/", response_model=SettingsSnapshot)
def get_settings_snapshot() -> SettingsSnapshot:
    s = get_settings()
    s.ensure_dirs()
    from ..config import POINTER_FILE
    return SettingsSnapshot(
        data_root=str(s.data_root),
        monitor_dir=str(s.monitor_dir),
        is_default_root=_is_default_root(s.data_root),
        pointer_file=str(POINTER_FILE),
        api_roles=_read_api_config_full(),
        categories=read_rows(s.category_config_csv),
        custom_fields=read_rows(s.custom_fields_csv),
    )


@router.post("/data-root")
def update_data_root(body: DataRootUpdate) -> dict:
    target = Path(body.path).expanduser()
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="path 必须是绝对路径")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法创建目录: {e}") from e

    s = set_data_root(target)
    return {
        "ok": True,
        "data_root": str(s.data_root),
        "monitor_dir": str(s.monitor_dir),
        "is_default_root": _is_default_root(s.data_root),
    }


@router.post("/monitor-dir")
def update_monitor_dir(body: MonitorDirUpdate) -> dict:
    s = get_settings()
    target = Path(body.path).expanduser()
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="path 必须是绝对路径")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法创建目录: {e}") from e

    upsert_row(
        s.app_config_csv,
        APP_CONFIG_HEADERS,
        {"key": "monitor_dir", "value": str(target)},
        primary_key="key",
    )
    s.monitor_dir = target
    return {"ok": True, "monitor_dir": str(target)}


@router.get("/api-config")
def list_api_config() -> dict:
    return {"items": _read_api_config_full()}


@router.post("/api-config")
def update_api_config(body: ApiConfigUpdate) -> dict:
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role 必须是 {sorted(_VALID_ROLES)} 之一",
        )
    s = get_settings()
    secrets_before = _read_secrets()
    row = {
        "role": body.role,
        "endpoint": body.endpoint.strip(),
        "model": body.model.strip(),
        "api_key_set": "true" if (body.api_key or secrets_before.get(body.role)) else "false",
        "timeout": str(body.timeout),
        "last_modified": _now(),
    }
    upsert_row(s.api_config_csv, API_CONFIG_HEADERS, row, primary_key="role")

    if body.api_key is not None:
        secrets = _read_secrets()
        if body.api_key:
            secrets[body.role] = body.api_key
        else:
            secrets.pop(body.role, None)
        _write_secrets(secrets)

    row["api_key_set"] = "true" if _read_secrets().get(body.role) else "false"
    upsert_row(s.api_config_csv, API_CONFIG_HEADERS, row, primary_key="role")

    return {"ok": True, "role": body.role, "api_key_set": row["api_key_set"] == "true"}


@router.get("/category-config")
def list_categories() -> dict:
    return {"items": read_rows(get_settings().category_config_csv)}


@router.post("/category-config")
def replace_categories(body: CategoryBatch) -> dict:
    s = get_settings()
    import csv as _csv
    with s.category_config_csv.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=CATEGORY_CONFIG_HEADERS)
        w.writeheader()
        for item in body.items:
            w.writerow({
                "perspective": item.perspective,
                "category": item.category,
                "subcategory": item.subcategory,
            })
    return {"ok": True, "count": len(body.items)}


@router.get("/custom-fields")
def list_custom_fields() -> dict:
    return {"items": read_rows(get_settings().custom_fields_csv)}


@router.post("/custom-fields")
def replace_custom_fields(body: CustomFieldsBatch) -> dict:
    s = get_settings()
    import csv as _csv
    with s.custom_fields_csv.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=CUSTOM_FIELDS_HEADERS)
        w.writeheader()
        for item in body.items:
            w.writerow({
                "field_name": item.field_name,
                "field_type": item.field_type,
                "description": item.description,
            })
    return {"ok": True, "count": len(body.items)}
