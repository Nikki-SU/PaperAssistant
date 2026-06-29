"""debug-assistant 内联精简版 Python 客户端。

设计纪律（与前端 ``frontend/src/lib/debugAssistant.ts`` 保持对称）：
- 不依赖外部包，仅标准库（urllib + json）
- 任何 HTTP 失败都静默降级（log.warning），绝不抛给业务
- 连不上 server / SDK 未初始化时，所有 API 都安全返回 None / False
- 业务代码统一用 ``from app.lib.debug_assistant import report, catch, context``

这里不 vendor 完整 SDK，目的：保持精简、不与上游 SDK 同步包冲突，
只覆盖 PaperAssistant 真正用到的子集（report / resolve / catch / context）。
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import threading
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

log = logging.getLogger("debug_assistant")

DEFAULT_TIMEOUT = 2.0


@dataclass
class _Config:
    project: str = "PaperAssistant"
    module: str = "backend"
    host: str = "127.0.0.1"
    port: int = 8765
    enabled: bool = True
    timeout: float = DEFAULT_TIMEOUT

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


_lock = threading.Lock()
_cfg: Optional[_Config] = None


def init(
    *,
    project: str = "PaperAssistant",
    module: str = "backend",
    host: str = "127.0.0.1",
    port: int = 8765,
    enabled: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """初始化默认 debugger。多次调用会覆盖。"""
    global _cfg
    with _lock:
        _cfg = _Config(
            project=project,
            module=module,
            host=host,
            port=port,
            enabled=enabled,
            timeout=timeout,
        )
    log.info(
        "debug-assistant init: project=%s module=%s base=%s enabled=%s",
        project, module, _cfg.base_url, enabled,
    )


def is_ready() -> bool:
    return _cfg is not None and _cfg.enabled


def _post(path: str, body: dict) -> Optional[dict]:
    if _cfg is None or not _cfg.enabled:
        return None
    url = _cfg.base_url + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_cfg.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        log.warning("debug-assistant POST %s HTTP %s %s", path, e.code, detail[:200])
        return None
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        log.warning("debug-assistant POST %s 连接失败：%s（已降级）", path, e)
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("debug-assistant POST %s 异常：%s（已降级）", path, e)
        return None


def health() -> Optional[dict]:
    if _cfg is None or not _cfg.enabled:
        return None
    url = _cfg.base_url + "/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_cfg.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except Exception:
        return None


def report(
    error: Optional[BaseException] = None,
    *,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    stack_trace: Optional[str] = None,
    severity: str = "error",
    context: Optional[dict[str, Any]] = None,
    user_action: Optional[str] = None,
    stage: Optional[str] = None,
    operation_path: Optional[str] = None,
    input_data: Optional[dict[str, Any]] = None,
    logs: Optional[list[str]] = None,
) -> Optional[str]:
    """新建错误报告，返回 error_id 或 None（失败已降级）。"""
    if _cfg is None or not _cfg.enabled:
        return None

    if error is not None:
        if error_type is None:
            error_type = type(error).__name__
        if error_message is None:
            error_message = str(error) or repr(error)
        if stack_trace is None:
            stack_trace = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
    if not error_type:
        error_type = "UnknownError"
    if error_message is None:
        error_message = ""

    env = {
        "Python": platform.python_version(),
        "OS": f"{platform.system()} {platform.release()}",
        "SDK": "PA-inline-da/0.1.0",
    }

    body = {
        "project": _cfg.project,
        "module": _cfg.module,
        "error_type": error_type,
        "error_message": error_message,
        "severity": severity,
        "user_action": user_action,
        "stage": stage,
        "extra_context_table": {str(k): str(v) for k, v in (context or {}).items()},
        "operation_path": operation_path,
        "input_data": input_data or {},
        "logs": logs or [],
        "stack_trace": stack_trace,
        "env": env,
    }
    body = {k: v for k, v in body.items() if v is not None}

    resp = _post("/api/report", body)
    if resp:
        return resp.get("error_id")
    return None


def resolve(error_id: str, solution: str, related_changes: Optional[str] = None) -> bool:
    resp = _post(
        "/api/resolve",
        {
            "error_id": error_id,
            "solution": solution,
            "related_changes": related_changes,
        },
    )
    return bool(resp and resp.get("status") == "resolved")


def catch(
    func: Optional[Callable[..., Any]] = None,
    *,
    reraise: bool = True,
    severity: str = "error",
    stage: Optional[str] = None,
) -> Callable[..., Any]:
    """装饰器：自动上报异常，默认仍重新抛出。"""

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        from functools import wraps

        @wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except BaseException as e:  # noqa: BLE001
                try:
                    report(error=e, severity=severity, stage=stage,
                           context={"function": fn.__qualname__})
                except Exception:
                    log.exception("debug-assistant catch 自身异常")
                if reraise:
                    raise
                return None
        return inner

    if func is None:
        return _wrap
    return _wrap(func)


@contextmanager
def context(
    *,
    reraise: bool = True,
    severity: str = "error",
    stage: Optional[str] = None,
    user_action: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Iterator[None]:
    """with debug_assistant.context(stage="文献综述"): ..."""
    try:
        yield
    except BaseException as e:  # noqa: BLE001
        try:
            report(error=e, severity=severity, stage=stage,
                   user_action=user_action, context=extra)
        except Exception:
            log.exception("debug-assistant context 自身异常")
        if reraise:
            raise


def init_from_env() -> None:
    """从环境变量初始化（PaperAssistant 启动时调用）。"""
    enabled = os.environ.get("DEBUG_ASSISTANT_ENABLED", "true").strip().lower()
    init(
        project=os.environ.get("DEBUG_ASSISTANT_PROJECT", "PaperAssistant"),
        module=os.environ.get("DEBUG_ASSISTANT_MODULE", "backend"),
        host=os.environ.get("DEBUG_ASSISTANT_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEBUG_ASSISTANT_PORT", "8765")),
        enabled=enabled not in ("0", "false", "no", "off"),
        timeout=float(os.environ.get("DEBUG_ASSISTANT_TIMEOUT", str(DEFAULT_TIMEOUT))),
    )
