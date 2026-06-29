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
class VerifyResult:
    """SPEC §4.3 事实核查结果。

    status:
      - verified: 5 轮内通过
      - failed:   循环 5 次仍未通过（内容应丢弃）
      - not_configured: auditor 未配置
      - error:    审阅/重生成调用过程中出错
    """
    status: str
    final_content: str = ""
    rounds: int = 0
    last_feedback: str = ""
    log_path: str = ""


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

    # ---- SPEC §4.3 事实核查 5 轮循环 ----

    def verify_with_auditor(
        self,
        content: str,
        sources: list[dict],
        *,
        project: Optional[str] = None,
        max_rounds: int = 5,
    ) -> "VerifyResult":
        """事实核查 5 轮循环：助手生成 → 审阅检查 → 通过/反馈循环（≤5次）。

        Args:
            content: 助手 AI 已生成的待审内容
            sources: 原文引用片段列表，每条 dict 含 ``{title, snippet}`` 或 ``{text}``
            project: 当前项目名（用于日志路径）；None 时写入 _global
            max_rounds: 最多循环次数

        Returns:
            VerifyResult: ``status`` 取值 ``verified / failed / not_configured / error``
        """
        log_path = _resolve_reviewer_log_path(project)
        _append_reviewer_log(log_path, header=True, content=content, sources=sources)

        # 审阅 AI 没配置 → 直接退化为 suggestion，不走循环
        if not self.is_configured(AIRole.AUDITOR):
            _append_reviewer_log(
                log_path, round_idx=0, verdict="skipped",
                feedback="auditor 未配置，已跳过事实核查",
            )
            return VerifyResult(
                status="not_configured",
                final_content=content,
                rounds=0,
                last_feedback="auditor 未配置，请到「设置 → AI 接口位 → auditor」填写 endpoint/key/model。",
                log_path=str(log_path),
            )

        current = content
        last_feedback = ""

        for round_idx in range(1, max_rounds + 1):
            audit_messages = _build_auditor_prompt(current, sources)
            audit_result = self.chat(AIRole.AUDITOR, audit_messages)
            if not audit_result.success:
                _append_reviewer_log(
                    log_path, round_idx=round_idx, verdict="error",
                    feedback=f"audit call failed: {audit_result.error}",
                )
                return VerifyResult(
                    status="error", final_content=current, rounds=round_idx,
                    last_feedback=audit_result.error, log_path=str(log_path),
                )

            verdict = _parse_audit_verdict(audit_result.output)
            consistent = verdict.get("consistent", False)
            no_extra = verdict.get("no_extra", False)
            feedback = (verdict.get("feedback") or "").strip()
            last_feedback = feedback or audit_result.output[:200]

            _append_reviewer_log(
                log_path, round_idx=round_idx,
                verdict="pass" if (consistent and no_extra) else "fail",
                feedback=feedback or audit_result.output[:500],
                raw=audit_result.output,
            )

            if consistent and no_extra:
                return VerifyResult(
                    status="verified", final_content=current, rounds=round_idx,
                    last_feedback=feedback or "通过：与原文一致且无新增信息",
                    log_path=str(log_path),
                )

            # 不通过 → 反馈给助手重生成
            if round_idx >= max_rounds:
                break
            regen_messages = _build_regen_prompt(current, sources, feedback)
            regen = self.chat(AIRole.ASSISTANT, regen_messages)
            if not regen.success:
                _append_reviewer_log(
                    log_path, round_idx=round_idx, verdict="error",
                    feedback=f"regen call failed: {regen.error}",
                )
                return VerifyResult(
                    status="error", final_content=current, rounds=round_idx,
                    last_feedback=regen.error, log_path=str(log_path),
                )
            current = regen.output

        # 跑完 max_rounds 仍未通过 → failed
        # 硬丢弃：final_content 清空，禁止入库；用户只看到失败状态 + 兜底引导
        guide = (
            "事实核查 5 轮未通过，已自动丢弃内容、不会写入任何卡片/知识库/记忆。\n"
            "建议你：\n"
            "  1. 补充更具体的原文片段（当前引用可能太少或不够精确）\n"
            "  2. 缩小生成范围（让助手一次只总结一个论点而非多个）\n"
            "  3. 换个表述重新请求（避免让助手发挥/推断）\n"
            "  4. 若内容本就无法从原文得出，请放弃此次生成。"
        )
        composed_feedback = (last_feedback + "\n\n" + guide).strip() if last_feedback else guide
        _append_reviewer_log(
            log_path, round_idx=max_rounds, verdict="failed_max_rounds",
            feedback=f"已循环 {max_rounds} 次仍未通过，内容已丢弃（final_content 置空，禁止入库）",
        )
        _append_reviewer_log(
            log_path, round_idx=0, verdict="dropped",
            feedback="按用户铁律：未通过审阅的内容不得入库",
        )
        return VerifyResult(
            status="failed",
            final_content="",  # 硬丢弃，防止任何业务侧误用
            rounds=max_rounds,
            last_feedback=composed_feedback,
            log_path=str(log_path),
        )



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



# ---------------- SPEC §4.3 辅助函数 ----------------

_AUDITOR_SYSTEM_PROMPT = """你是严格的事实核查员。你的唯一职责是检查"助手内容"相对于"原文引用"是否：
1. consistent: 与原文无矛盾（不能有事实冲突）
2. no_extra:  没有引入原文中不存在的实质性新增信息（细微措辞调整不算新增）

你必须只输出一个 JSON 对象，不要任何解释/前后缀/Markdown 代码块包裹。格式：
{"consistent": true/false, "no_extra": true/false, "feedback": "如未通过，简要说明具体问题；通过时可留空"}
"""


def _build_auditor_prompt(content: str, sources: list[dict]) -> list[dict]:
    src_text = _format_sources(sources)
    user = (
        "【原文引用】\n" + (src_text or "(无)") +
        "\n\n【助手内容（待审）】\n" + content +
        "\n\n请严格按 JSON 格式输出审阅结果。"
    )
    return [
        {"role": "system", "content": _AUDITOR_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_regen_prompt(prev_content: str, sources: list[dict], feedback: str) -> list[dict]:
    src_text = _format_sources(sources)
    user = (
        "你之前的输出未通过事实核查。请基于以下原文片段重新生成内容，严格遵守：\n"
        "1. 不要引入原文中不存在的新增信息\n"
        "2. 不要与原文事实矛盾\n"
        "3. 用简明中文重写\n\n"
        f"【审阅反馈】\n{feedback or '(未提供具体反馈)'}\n\n"
        f"【原文引用】\n{src_text or '(无)'}\n\n"
        f"【你之前的输出】\n{prev_content}\n\n"
        "请输出修订后的内容（仅正文，不要解释你的修改）。"
    )
    return [
        {"role": "system", "content": "你是论文写作助手，遵守用户的事实核查约束，不编造来源。"},
        {"role": "user", "content": user},
    ]


def _format_sources(sources: list[dict]) -> str:
    lines = []
    for i, s in enumerate(sources or [], 1):
        title = (s.get("title") or s.get("name") or f"片段 {i}").strip()
        snippet = (s.get("snippet") or s.get("text") or s.get("content") or "").strip()
        if not snippet:
            continue
        lines.append(f"[{i}] {title}\n{snippet}")
    return "\n\n".join(lines)


def _parse_audit_verdict(text: str) -> dict[str, Any]:
    """从审阅 AI 的输出里抽 JSON。容忍前后多余文本和 ```json ``` 包裹。"""
    if not text:
        return {"consistent": False, "no_extra": False, "feedback": "审阅 AI 无输出"}
    s = text.strip()
    # 去掉 ```json ... ``` 包裹
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1:]
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    # 取第一个 { 到最后一个 }
    lb, rb = s.find("{"), s.rfind("}")
    if lb != -1 and rb > lb:
        s = s[lb : rb + 1]
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("not a dict")
        return {
            "consistent": bool(obj.get("consistent", False)),
            "no_extra": bool(obj.get("no_extra", False)),
            "feedback": str(obj.get("feedback", "") or ""),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("auditor verdict parse failed: %s, raw=%r", e, text[:200])
        return {
            "consistent": False, "no_extra": False,
            "feedback": f"审阅 AI 未返回合法 JSON：{text[:200]}",
        }


def _resolve_reviewer_log_path(project: Optional[str]):
    from pathlib import Path
    settings = get_settings()
    data_root = Path(settings.data_root)
    if project:
        safe = "".join(c for c in project if c not in '\\/:*?"<>|').strip() or "_unnamed"
        d = data_root / "projects" / safe / "memories"
    else:
        d = data_root / "projects" / "_global" / "memories"
    d.mkdir(parents=True, exist_ok=True)
    return d / "reviewer.md"


def _append_reviewer_log(
    path,
    *,
    header: bool = False,
    content: str = "",
    sources: Optional[list[dict]] = None,
    round_idx: int = 0,
    verdict: str = "",
    feedback: str = "",
    raw: str = "",
) -> None:
    """追加事实核查日志到 reviewer.md（仅 Markdown）。"""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    if header:
        lines.append(f"\n## 事实核查 {ts}\n")
        lines.append("### 待审内容\n")
        lines.append("```\n" + (content or "").strip() + "\n```\n")
        if sources:
            lines.append("### 原文引用\n")
            for i, s in enumerate(sources, 1):
                title = (s.get("title") or s.get("name") or f"片段 {i}").strip()
                snippet = (s.get("snippet") or s.get("text") or s.get("content") or "").strip()
                lines.append(f"- **[{i}] {title}**\n  > " + snippet.replace("\n", "\n  > ") + "\n")
    else:
        lines.append(f"- 第 {round_idx} 轮 @ {ts} → **{verdict}**\n")
        if feedback:
            lines.append(f"  - 反馈：{feedback}\n")
        if raw and verdict not in ("pass",):
            short = raw.strip().replace("\n", " ")[:200]
            lines.append(f"  - 原始输出：`{short}`\n")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception as e:  # noqa: BLE001
        logger.warning("append reviewer log failed: %s", e)



# ---------------- 入库守卫（SPEC §4.3 铁律 3） ----------------


class AuditRejectedError(Exception):
    """未通过事实核查的内容禁止写入下游（卡片/知识库/记忆）。"""

    def __init__(self, verify_result: "VerifyResult") -> None:
        self.verify_result = verify_result
        super().__init__(
            f"内容未通过事实核查（status={verify_result.status}, "
            f"rounds={verify_result.rounds}），按用户铁律禁止入库。"
        )


def assert_verified_or_raise(result: "VerifyResult") -> str:
    """卡片/知识库/记忆等下游写入前必须调用此函数。

    通过 → 返回经审阅的 final_content
    未通过 → 抛 AuditRejectedError，业务侧捕获后向前端返回友好错误

    用法：
        v = orch.verify_with_auditor(content, sources, project=p)
        try:
            safe = assert_verified_or_raise(v)
            write_card(safe)  # 只有 verified 才会到这一步
        except AuditRejectedError as e:
            return {"success": False, "error": str(e), "audit": e.verify_result}
    """
    if result.status != "verified":
        raise AuditRejectedError(result)
    return result.final_content
