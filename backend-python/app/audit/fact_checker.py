"""事实核查器：审阅 AI 闭环。

判断标准：
1. 总结是否与原文一致（无矛盾）？
2. 总结是否有原文中不存在的新增信息？

两项都通过 → 接受；任一不通过 → 反馈助手 AI 重新生成（最多 5 次）。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AuditResult:
    passed: bool
    reason: str
    diff_with_source: str | None = None


def audit_summary(summary: str, source_excerpt: str) -> AuditResult:
    """核查 AI 总结是否符合原文。

    实际实现：调用审阅 AI（带特定 prompt） → 解析返回。
    所有审计记录追加到 projects/{project}/memories/reviewer.md。
    """
    # TODO
    raise NotImplementedError
