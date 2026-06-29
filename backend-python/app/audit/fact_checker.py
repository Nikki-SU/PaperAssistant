"""事实核查框架。

负责把「助手 AI 的草稿」交给「审阅 AI」核对，最多 5 次循环；
核心是一个可被 AIOrchestrator 调用的 prompt 模板 + 输出解析。

实现要点：
1. 输入：草稿文本 + 一份「证据集合」（来自本地文献卡片 + 全文 Markdown）
2. 输出：findings 列表，每条 findings 标明 status=ok|inferred|unsupported|missing-info
3. 控制：最多 max_iterations 轮；每轮基于上一轮 findings 重新修订草稿
4. 边界：
   - status=ok：可放心引用
   - status=inferred：必须前缀「建议」
   - status=unsupported：必须删除或改写
   - status=missing-info：要求用户补充资料
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AuditOutcome(str, Enum):
    OK = "ok"
    INFERRED = "inferred"
    UNSUPPORTED = "unsupported"
    MISSING_INFO = "missing-info"


@dataclass
class AuditFinding:
    span: str            # 草稿中的相关句子
    outcome: AuditOutcome
    note: str = ""       # 审阅 AI 给的说明
    evidence: str = ""   # 来源（DOI / 卡片 id / 章节路径）


@dataclass
class AuditReport:
    iteration: int
    draft: str
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return any(
            f.outcome in (AuditOutcome.UNSUPPORTED, AuditOutcome.MISSING_INFO)
            for f in self.findings
        )


SYSTEM_PROMPT_AUDITOR = """你是审阅 AI（PaperAssistant）。你的唯一任务是审核「助手 AI」生成的论文段落。
规则：
1. 草稿中任何「来自某文献」的陈述都必须能在用户提供的「证据集合」中找到原文支撑；
2. 没有支撑的陈述按以下分类处理：
   - 属于合理推断 → 标注 inferred（要求作者改写为「建议……」）；
   - 与已知事实矛盾或无任何依据 → 标注 unsupported；
   - 因证据缺失无法判断 → 标注 missing-info，并写明缺什么；
3. 不要自己编造文献；不要给出新的研究结论。
输出格式（每条独立一行，制表符分隔）：
  span<TAB>outcome<TAB>evidence<TAB>note
其中 outcome ∈ {ok, inferred, unsupported, missing-info}。
"""


# AI 调用签名：input(system, user) -> output_text
AIChat = Callable[[str, str], str]


class FactChecker:
    """SPEC §六：最多 5 次循环的审稿器。"""

    def __init__(
        self,
        auditor_chat: Optional[AIChat] = None,
        assistant_chat: Optional[AIChat] = None,
        max_iterations: int = 5,
    ) -> None:
        self.auditor_chat = auditor_chat
        self.assistant_chat = assistant_chat
        self.max_iterations = max_iterations

    def review_once(self, draft: str, evidence: str) -> AuditReport:
        if self.auditor_chat is None:
            # 没接 AI 时降级：返回一份「全部 missing-info」的报告
            return AuditReport(
                iteration=0,
                draft=draft,
                findings=[
                    AuditFinding(
                        span="(整段)",
                        outcome=AuditOutcome.MISSING_INFO,
                        note="审阅 AI 未配置：本地无法验证；请在「设置」中配置审阅接口位。",
                    )
                ],
            )
        user = f"=== 证据集合 ===\n{evidence}\n\n=== 待审稿件 ===\n{draft}\n"
        text = self.auditor_chat(SYSTEM_PROMPT_AUDITOR, user)
        findings = self._parse_findings(text)
        return AuditReport(iteration=0, draft=draft, findings=findings)

    def review_loop(
        self,
        initial_draft: str,
        evidence: str,
        revise_prompt_builder: Optional[Callable[[AuditReport], tuple[str, str]]] = None,
    ) -> AuditReport:
        """循环审核 + 重写。最多 max_iterations 轮。

        revise_prompt_builder(report) -> (system, user) 用于让助手 AI 根据 findings 改稿。
        """
        report = self.review_once(initial_draft, evidence)
        report.iteration = 1
        for i in range(2, self.max_iterations + 1):
            if not report.has_blocking:
                return report
            if not (self.assistant_chat and revise_prompt_builder):
                return report
            system, user = revise_prompt_builder(report)
            new_draft = self.assistant_chat(system, user) or report.draft
            report = self.review_once(new_draft, evidence)
            report.iteration = i
        return report

    @staticmethod
    def _parse_findings(text: str) -> list[AuditFinding]:
        out: list[AuditFinding] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            span = parts[0].strip()
            try:
                outcome = AuditOutcome(parts[1].strip())
            except ValueError:
                continue
            evidence = parts[2].strip() if len(parts) >= 3 else ""
            note = parts[3].strip() if len(parts) >= 4 else ""
            out.append(AuditFinding(span=span, outcome=outcome, evidence=evidence, note=note))
        return out
