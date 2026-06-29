"""Markdown 读写工具。

所有非结构化/富文本数据（文献全文、卡片正文、记忆、临时知识、LaTeX 模板）都走这里。
卡片采用「YAML frontmatter + 正文」格式，结构化字段同时落 CSV，正文落 Markdown。
"""
from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str, *, header: Optional[str] = None) -> None:
    """追加文本；可选地在追加前插入 header 标题。"""
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if not path.exists():
            prefix = ""
        else:
            existing = path.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                prefix = "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(prefix)
            if header:
                f.write(f"\n## {header}\n\n")
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")


def read_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 YAML-like frontmatter；只支持顶层 ``key: value`` 行。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm_block = m.group(1)
    body = text[m.end():]
    data: dict[str, str] = {}
    for line in fm_block.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data, body


def render_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in meta.items():
        sv = "" if v is None else str(v)
        if any(c in sv for c in ":#"):
            sv = '"' + sv.replace('"', '\\"') + '"'
        lines.append(f"{k}: {sv}")
    lines.append("---\n")
    return "\n".join(lines)


# ---------- 文献卡片：CSV 字段对应的 Markdown 模板 ----------

# 来自 SPEC §八.1
LIT_CSV_HEADERS = [
    "doi", "title", "journal", "first_author", "corresponding_author",
    "keywords", "abstract", "category", "subcategory",
    "theory", "experiment_design", "data", "results", "policy_suggestions",
    "experiment", "characterization", "mechanism", "application",
    "custom_fields", "status", "last_modified",
]


def render_literature_card_md(meta: dict[str, Any]) -> str:
    """根据 CSV 行渲染 Markdown 卡片（前 matter + 八节正文）。"""
    fm = render_frontmatter(
        {k: meta.get(k, "") for k in
         ["doi", "title", "journal", "first_author", "corresponding_author",
          "category", "subcategory", "status", "last_modified"]}
    )
    body = f"""# {meta.get('title') or '(未命名)'}

> **DOI**：`{meta.get('doi', '')}`
> **期刊**：{meta.get('journal', '')}
> **第一作者**：{meta.get('first_author', '')}
> **通讯作者**：{meta.get('corresponding_author', '')}

## 关键词

{meta.get('keywords', '')}

## 摘要

{meta.get('abstract', '') or '_（未填写）_'}

## 分类

- 大类：{meta.get('category', '')}
- 子类：{meta.get('subcategory', '')}

## 社科视角

| 维度 | 内容 |
|------|------|
| 理论 | {meta.get('theory') or '-'} |
| 研究设计 | {meta.get('experiment_design') or '-'} |
| 数据 | {meta.get('data') or '-'} |
| 结果 | {meta.get('results') or '-'} |
| 政策建议 | {meta.get('policy_suggestions') or '-'} |

## 理科视角

| 维度 | 内容 |
|------|------|
| 实验 | {meta.get('experiment') or '-'} |
| 表征 | {meta.get('characterization') or '-'} |
| 机理 | {meta.get('mechanism') or '-'} |
| 应用 | {meta.get('application') or '-'} |

## 自定义字段

{meta.get('custom_fields') or '_（无）_'}

---

> 状态：{meta.get('status', 'draft')}  ·  最后修改：{meta.get('last_modified', '')}
"""
    return fm + body


# ---------- 知识库卡片：SPEC §八.2 ----------

def render_knowledge_card_md(meta: dict[str, Any]) -> str:
    """SPEC §8.2：知识库卡片 Markdown 渲染。

    结构：YAML frontmatter（card_id/subject/source/audited） + 提示词 + 摘要。
    """
    fm = render_frontmatter(
        {
            "card_id": meta.get("card_id", ""),
            "subject": meta.get("subject", ""),
            "title": meta.get("title", ""),
            "source_book": meta.get("source_book", ""),
            "source_section": meta.get("source_section", ""),
            "audited": str(meta.get("audited", "")).lower(),
            "last_modified": meta.get("last_modified", ""),
        }
    )
    audited_badge = "✅ 已通过事实核查" if str(meta.get("audited", "")).lower() == "true" else "⚠️ 未审"
    body = f"""# {meta.get('title') or '(未命名知识点)'}

> **学科**：{meta.get('subject', '')}
> **来源教材**：{meta.get('source_book') or '_（未填写）_'}
> **来源章节**：{meta.get('source_section') or '_（未填写）_'}
> **审阅状态**：{audited_badge}

## 用户提示词

{meta.get('prompt') or '_（无）_'}

## AI 提取摘要

{meta.get('summary') or '_（待生成）_'}

---

> 卡片 ID：`{meta.get('card_id', '')}`  ·  最后修改：{meta.get('last_modified', '')}
"""
    return fm + body


# ---------- 三角色记忆：SPEC §八.3 ----------

def append_role_memory_entry(
    path: Path,
    *,
    role_label: str,
    title: str,
    body: str,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """三角色记忆通用追加：助手/审阅/秘书。

    每条形如：
        ### {时间} · {标题}
        - 元信息字段...

        {正文}

    role_label 只用于在追加前确认文件是该角色的（不强校验）。
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n### {ts} · {title}\n"]
    if meta:
        for k, v in meta.items():
            sv = "" if v is None else str(v)
            if sv:
                lines.append(f"- **{k}**：{sv}\n")
    if body:
        lines.append("\n")
        lines.append(body.rstrip() + "\n")
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 文件不存在时种一个最小标头（避免 seed 漏掉时丢失记录）
        if not path.exists():
            path.write_text(
                f"# {role_label} 记忆\n\n_自动追加日志。_\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as f:
            f.write("".join(lines))


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
