"""AI 调度：助手 / 审阅 / 秘书三角色协作。

对应 SPEC：项目二 §四.2 AI 职责边界 / §四.5 四个 API 接口位
"""
from __future__ import annotations
from enum import Enum
from typing import Any


class AIRole(str, Enum):
    ASSISTANT = "assistant"  # 主要输出
    REVIEWER = "reviewer"    # 事实核查
    SECRETARY = "secretary"  # 错别字 / 语法（可选，未配置则复用助手）


class AIOrchestrator:
    """三角色调度器，根据任务类型路由到对应 API。"""

    def __init__(self, api_config: dict[AIRole, dict]):
        self.api_config = api_config

    async def call(self, role: AIRole, prompt: str, **kwargs) -> str:
        """调用指定角色的 AI。"""
        # TODO: 根据 role 取出 API config → httpx 调用 OpenAI 兼容接口
        raise NotImplementedError

    async def review_with_loop(self, claim: str, source: str, max_retries: int = 5) -> tuple[bool, str]:
        """审阅闭环：助手生成 → 审阅核查 → 不通过则重新生成，最多 5 次。

        对应 SPEC：§四.3 事实核查规则 - 核查流程
        返回：(是否通过, 最终内容 or 失败原因)
        """
        # TODO: 实现 5 次循环 + 写审阅日志到 reviewer.md
        raise NotImplementedError
