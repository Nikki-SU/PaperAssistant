"""AI 编排器（SPEC §四 4 个接口位的统一入口）。

四个接口位：
- ASSISTANT   助手：负责常规对话、思路探索、文献综述初稿、章节起草等
- AUDITOR     审阅：负责事实核查、引用验证、文献依据比对
- SECRETARY   秘书：负责调度、节奏控制、产物清单管理
- MINERU      已在 MineruClient 中实现

铁律：当 API key 未配置或网络失败时，必须降级返回结构化错误，不能让业务侧崩溃。
本文件目前是「接口位骨架」：保留 prompt / payload / retry 钩子，TODO 接真实模型。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

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


@dataclass
class AIRoleConfig:
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    timeout: float = 60.0


class AIOrchestrator:
    """SPEC §四 的统一编排：根据 role 路由到对应接口位。"""

    def __init__(self, configs: Optional[dict[AIRole, AIRoleConfig]] = None) -> None:
        self.configs: dict[AIRole, AIRoleConfig] = configs or {}
        for role in AIRole:
            self.configs.setdefault(role, self._from_env(role))

    @staticmethod
    def _from_env(role: AIRole) -> AIRoleConfig:
        prefix = f"PA_{role.value.upper()}_"
        return AIRoleConfig(
            api_key=os.environ.get(f"{prefix}API_KEY", ""),
            endpoint=os.environ.get(f"{prefix}ENDPOINT", ""),
            model=os.environ.get(f"{prefix}MODEL", ""),
            timeout=float(os.environ.get(f"{prefix}TIMEOUT", "60")),
        )

    def is_configured(self, role: AIRole) -> bool:
        cfg = self.configs[role]
        return bool(cfg.api_key and cfg.endpoint)

    def chat(
        self,
        role: AIRole,
        system: str,
        user: str,
        *,
        extra: Optional[dict[str, Any]] = None,
    ) -> AIResult:
        """统一 chat 调用，失败时降级返回 success=False。"""
        cfg = self.configs[role]
        if not self.is_configured(role):
            return AIResult(
                success=False,
                role=role,
                error=f"[{role.value}] 未配置 API key / endpoint，已降级。",
            )
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if extra:
            payload.update(extra)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            cfg.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            logger.warning("[%s] AI 接口失败：%s", role.value, e)
            return AIResult(success=False, role=role, error=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("[%s] AI 接口异常", role.value)
            return AIResult(success=False, role=role, error=str(e))

        output = self._extract_text(raw)
        return AIResult(success=True, role=role, output=output, raw=raw)

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        # 兼容 OpenAI 风格 + 简易直返字段
        if "choices" in raw and raw["choices"]:
            msg = raw["choices"][0].get("message") or {}
            if isinstance(msg, dict) and "content" in msg:
                return str(msg["content"])
        if "output" in raw:
            return str(raw["output"])
        if "text" in raw:
            return str(raw["text"])
        return ""

    # --------- 语义包装：给上层用 ----------

    def assistant_draft(self, system: str, user: str) -> AIResult:
        return self.chat(AIRole.ASSISTANT, system, user)

    def auditor_check(self, system: str, user: str) -> AIResult:
        return self.chat(AIRole.AUDITOR, system, user)

    def secretary_plan(self, system: str, user: str) -> AIResult:
        return self.chat(AIRole.SECRETARY, system, user)
