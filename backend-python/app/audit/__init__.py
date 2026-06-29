"""事实核查 / AI 边界审计层。

SPEC §四.2 + §六：
- 声称「来自某文献」的内容必须经过审阅 AI 核查
- 推断类内容必须标注「建议」
- 缺信息时告知用户补充，不得编造
- 单次任务最多 5 次审阅循环
"""
from .fact_checker import FactChecker, AuditFinding, AuditOutcome

__all__ = ["FactChecker", "AuditFinding", "AuditOutcome"]
