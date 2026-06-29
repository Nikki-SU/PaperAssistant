"""AI 编排器（SPEC §四 4 个接口位的统一入口）。

四个接口位：
- ASSISTANT   助手：负责常规对话、思路探索、文献综述初稿、章节起草等
- AUDITOR     审阅：负责事实核查、引用验证、文献依据比对
- SECRETARY   秘书：调度、节奏控制；未配置时回退到 ASSISTANT
- MINERU      在 MineruClient 中实现（不在这里）

铁律：当 API key 未配置或网络失败时，必须降级返回结构化错误，不能让业务侧崩溃。
凭证来源（优先级由高到低）：
- 构造参数显式传入
- api_config.csv + api_keys.secret（用户在 GUI「设置」里配置的）
- 环境变量（PA_<ROLE>_API_KEY / _ENDPOINT / _MODEL / _TIMEOUT，方便 CLI 调试）

协议假设 OpenAI 兼容：POST {endpoint}/chat/completions，
Bearer 鉴权，请求体 `{model, messages, ...}`，响应 `choices[0].message.content`。
"""
from __future__ import annotations

import csv
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..config import get_settings
from ..lib import debug_assistant as da

logger = logging.getLogger(__name__)


class AIRole(str, Enum):
    ASSISTANT = "assistant"
    AUDITOR = "auditor"
    SECRETARY = "secretary"


@dataclass
class AIResult:
    success: bool
    role: AIRole
    output: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_code: str = ""  # not_configured / http_error / timeout / network / unknown


@dataclass
class AIRoleConfig:
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    timeout: float = 60.0


# ---------------- 配置读取 ----------------


def _read_secrets(secret_path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not secret_path.exists():
        return out
    try:
        for line in secret_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    except Exception:  # noqa: BLE001
        return out
    return out


def _read_api_config_rows(csv_path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not csv_path.exists():
        return rows
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                role = (row.get("role") or "").strip()
                if role:
                    rows[role] = row
    except Exception:  # noqa: BLE001
        return rows
    return rows


def _env_override(role: str) -> dict[str, str]:
    prefix = f"PA_{role.upper()}_"
    return {
        "api_key": os.environ.get(f"{prefix}API_KEY", ""),
        "endpoint": os.environ.get(f"{prefix}ENDPOINT", ""),
        "model": os.environ.get(f"{prefix}MODEL", ""),
        "timeout": os.environ.get(f"{prefix}TIMEOUT", ""),
    }


def load_role_config(role: str) -> AIRoleConfig:
    """合并三处来源拿到指定 role 的配置。"""
    s = get_settings()
    secrets = _read_secrets(s.api_keys_secret)
    rows = _read_api_config_rows(s.api_config_csv)
    env = _env_override(role)

    csv_row = rows.get(role, {})
    api_key = env["api_key"] or secrets.get(role, "") or ""
    endpoint = (env["endpoint"] or csv_row.get("endpoint", "") or "").rstrip("/")
    model = env["model"] or csv_row.get("model", "") or ""
    timeout_str = env["timeout"] or csv_row.get("timeout", "") or "60"
    try:
        timeout = float(timeout_str)
    except (TypeError, ValueError):
        timeout = 60.0
    return AIRoleConfig(api_key=api_key, endpoint=endpoint, model=model, timeout=timeout)


# ---------------- 编排器 ----------------


class AIOrchestrator:
    """SPEC §四 的统一编排：根据 role 路由到对应接口位。"""

    def __init__(self, configs: Optional[dict[AIRole, AIRoleConfig]] = None) -> None:
        self.configs: dict[AIRole, AIRoleConfig] = configs or {}
        for role in AIRole:
            self.configs.setdefault(role, load_role_config(role.value))

    def refresh(self) -> None:
        """从配置源重新加载（设置面板改完后调）。"""
        for role in AIRole:
            self.configs[role] = load_role_config(role.value)

    def effective_role(self, role: AIRole) -> AIRole:
        """secretary 未配置时复用 assistant（SPEC §4.5 行尾备注）。"""
        if role is AIRole.SECRETARY and not self.is_configured(AIRole.SECRETARY):
            return AIRole.ASSISTANT
        return role

    def is_configured(self, role: AIRole) -> bool:
        cfg = self.configs[role]
        return bool(cfg.api_key and cfg.endpoint)

    # ---- 真正的 chat 调用 ----

    def chat(
        self,
        role: AIRole,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> AIResult:
        """OpenAI 兼容协议 chat 调用。失败时降级返回 success=False + error_code。"""
        target = self.effective_role(role)
        cfg = self.configs[target]
        if not self.is_configured(target):
            return AIResult(
                success=False,
                role=target,
                error=f"[{target.value}] 未配置 endpoint/api_key，请到「设置 → AI 接口位」填写。",
                error_code="not_configured",
            )

        chosen_model = (model or cfg.model or "").strip()
        if not chosen_model:
            return AIResult(
                success=False,
                role=target,
                error=f"[{target.value}] 未指定 model 字段。请到「设置 → AI 接口位 → {target.value} → Model」填写模型名（如 deepseek-chat）。",
                error_code="not_configured",
            )

        url = cfg.endpoint.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "stream": False,
        }
        if extra:
            payload.update(extra)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            logger.warning("[%s] AI HTTP %s: %s", target.value, e.code, detail)
            da.report(
                error=e, severity="warning", stage="ai-chat",
                user_action=f"chat[{target.value}]",
                context={"http_status": e.code, "endpoint": url, "detail": detail[:200]},
            )
            return AIResult(
                success=False, role=target,
                error=f"AI 服务返回 HTTP {e.code}: {detail[:200] or e.reason}",
                error_code="http_error",
            )
        except urllib.error.URLError as e:
            logger.warning("[%s] AI 连接失败：%s", target.value, e)
            da.report(error=e, severity="warning", stage="ai-chat",
                      user_action=f"chat[{target.value}]", context={"endpoint": url})
            return AIResult(success=False, role=target,
                            error=f"AI 服务连接失败：{e.reason}", error_code="network")
        except Exception as e:  # noqa: BLE001
            logger.exception("[%s] AI 接口异常", target.value)
            da.report(error=e, severity="error", stage="ai-chat",
                      user_action=f"chat[{target.value}]", context={"endpoint": url})
            return AIResult(success=False, role=target, error=str(e), error_code="unknown")

        output = _extract_text(raw)
        return AIResult(success=True, role=target, output=output, raw=raw)

    # ---- 语义包装：给上层用 ----

    def assistant_chat(self, messages: list[dict], **kw: Any) -> AIResult:
        return self.chat(AIRole.ASSISTANT, messages, **kw)

    def auditor_check(self, messages: list[dict], **kw: Any) -> AIResult:
        return self.chat(AIRole.AUDITOR, messages, **kw)

    def secretary_plan(self, messages: list[dict], **kw: Any) -> AIResult:
        return self.chat(AIRole.SECRETARY, messages, **kw)


def _extract_text(raw: dict[str, Any]) -> str:
    # OpenAI 兼容 + 简易直返字段兜底
    if "choices" in raw and raw["choices"]:
        choice = raw["choices"][0]
        msg = choice.get("message") or {}
        if isinstance(msg, dict) and "content" in msg:
            return str(msg["content"])
        if "text" in choice:
            return str(choice["text"])
    if "output" in raw:
        return str(raw["output"])
    if "text" in raw:
        return str(raw["text"])
    return ""


# 单例（FastAPI 启动时初始化）
_orchestrator: Optional[AIOrchestrator] = None


def get_orchestrator() -> AIOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIOrchestrator()
    return _orchestrator


def reload_orchestrator() -> AIOrchestrator:
    """配置面板保存后调一下，让 orchestrator 重新读取最新 key/endpoint。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIOrchestrator()
    else:
        _orchestrator.refresh()
    return _orchestrator
