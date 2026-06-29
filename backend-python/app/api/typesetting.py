"""排版导出 API（SPEC §五 + §7.5 + §九 + H 阶段）。

三个端点：
1. POST /api/typesetting/{project}/export        合并 paper/*.md → manuscript.md
2. POST /api/typesetting/{project}/render_tex    根据 paper/template.tex 渲染替换变量 → paper/manuscript.tex
3. POST /api/typesetting/{project}/compile_pdf   调用 Tectonic 编译 manuscript.tex → manuscript.pdf

Tectonic 路径解析顺序（H 阶段约定）：
- 环境变量 ``PAPERASSISTANT_TECTONIC_BIN``（由 Tauri 启动 sidecar 时注入）
- 环境变量 ``TECTONIC_BIN``
- PATH 中的 ``tectonic`` / ``tectonic.exe``

如果都找不到 → 返回 ``{compiled: false, reason: "tectonic_not_found"}``，
不抛 500，确保前端可以提示用户在设置面板补充路径。

render_tex 模板兼容性：
- 优先识别 ``{{title}}`` / ``{{body}}`` 占位符（推荐方式，G+H 种子模板）。
- 兜底：若模板既没 ``{{body}}`` 也没 ``{{title}}``，则在 ``\\end{document}`` 前
  注入 body（向后兼容老模板）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..storage import now_iso, read_text, write_text

router = APIRouter(prefix="/api/typesetting", tags=["typesetting"])


def _paper_dir(project: str) -> Path:
    return get_settings().projects_dir / project / "paper"


def _resolve_tectonic() -> str | None:
    for env_key in ("PAPERASSISTANT_TECTONIC_BIN", "TECTONIC_BIN"):
        v = os.environ.get(env_key)
        if v and Path(v).exists():
            return v
    which = shutil.which("tectonic") or shutil.which("tectonic.exe")
    return which


def _render_template(tex_src: str, title: str, body: str) -> str:
    """把 {{title}} / {{body}} 占位符替换为实际值。

    若模板既无 {{body}} 也无 {{title}}，则把 body 注入到 \\end{document} 前
    （向后兼容旧种子模板）。
    """
    has_body_var = "{{body}}" in tex_src
    has_title_var = "{{title}}" in tex_src

    rendered = tex_src
    if has_title_var:
        rendered = rendered.replace("{{title}}", title)
    if has_body_var:
        rendered = rendered.replace("{{body}}", body)

    if not has_body_var:
        # 兜底：把 body 注入到 \end{document} 之前
        if "\\end{document}" in rendered:
            rendered = rendered.replace(
                "\\end{document}",
                body + "\n\\end{document}",
                1,
            )
        else:
            rendered = rendered + "\n" + body + "\n"
    return rendered


@router.post("/{project}/export")
def export_manuscript(project: str) -> dict:
    """合并 paper/ 下所有 *.md 为 manuscript.md（保持文件名顺序）。"""
    paper_dir = _paper_dir(project)
    if not paper_dir.exists():
        raise HTTPException(status_code=404, detail="项目论文目录不存在")
    # 排除自动产物：manuscript.md / draft.md（draft 是预热文件，不参与拼装）
    excluded = {"manuscript.md", "draft.md"}
    mds = sorted(p for p in paper_dir.glob("*.md") if p.name not in excluded)
    if not mds:
        raise HTTPException(status_code=404, detail="paper/ 下没有任何可合并的章节 Markdown")

    parts: list[str] = [f"<!-- exported_at: {now_iso()} -->\n"]
    for md in mds:
        parts.append(f"\n\n<!-- file: {md.name} -->\n")
        parts.append(read_text(md))
    out = paper_dir / "manuscript.md"
    write_text(out, "\n".join(parts))

    return {
        "project": project,
        "manuscript_path": str(out),
        "chapters": [m.name for m in mds],
    }


@router.post("/{project}/render_tex")
def render_tex(project: str) -> dict:
    """根据 paper/template.tex 渲染 manuscript.tex。

    占位变量 ``{{title}}`` / ``{{body}}``（若缺失则兜底注入 body 到 ``\\end{document}`` 前）。
    body 来自 manuscript.md。高级 Markdown → LaTeX 转换留待后续；当前先做最小可用版本。
    """
    paper_dir = _paper_dir(project)
    template = paper_dir / "template.tex"
    md = paper_dir / "manuscript.md"
    if not template.exists():
        raise HTTPException(status_code=404, detail="paper/template.tex 不存在；先 PATCH stage=typesetting 触发种子")
    if not md.exists():
        raise HTTPException(status_code=404, detail="paper/manuscript.md 不存在；先 POST /export 合并章节")

    tex_src = read_text(template)
    body = read_text(md)
    rendered = _render_template(tex_src, project, body)
    out = paper_dir / "manuscript.tex"
    write_text(out, rendered)
    return {
        "project": project,
        "tex_path": str(out),
        "bytes": len(rendered.encode("utf-8")),
        "had_title_var": "{{title}}" in tex_src,
        "had_body_var": "{{body}}" in tex_src,
    }


@router.post("/{project}/compile_pdf")
def compile_pdf(project: str) -> dict:
    """调用 Tectonic 编译 paper/manuscript.tex → paper/manuscript.pdf。

    Tectonic 不存在时返回 ``{compiled: false, reason: "tectonic_not_found"}``，
    不抛 500，由前端提示用户在设置面板补路径或运行 fetch_tectonic.ps1。
    """
    paper_dir = _paper_dir(project)
    tex = paper_dir / "manuscript.tex"
    if not tex.exists():
        raise HTTPException(status_code=404, detail="paper/manuscript.tex 不存在；先 POST /render_tex")

    bin_path = _resolve_tectonic()
    if not bin_path:
        return {
            "project": project,
            "compiled": False,
            "reason": "tectonic_not_found",
            "hint": (
                "请在设置面板配置 Tectonic 路径，或运行 scripts/fetch_tectonic.ps1 "
                "下载 tectonic.exe 到 frontend/src-tauri/resources/tectonic/。"
            ),
        }

    try:
        proc = subprocess.run(
            [bin_path, "--outdir", str(paper_dir), str(tex)],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {
            "project": project,
            "compiled": False,
            "reason": "timeout",
            "hint": "Tectonic 编译超过 180 秒，请检查文档体量或依赖包下载情况。",
        }
    except FileNotFoundError:
        # 解析时拿到的路径在执行瞬间失效
        return {
            "project": project,
            "compiled": False,
            "reason": "tectonic_not_found",
            "hint": "Tectonic 路径已失效，请检查 PAPERASSISTANT_TECTONIC_BIN 或 PATH。",
        }

    pdf = paper_dir / (tex.stem + ".pdf")
    if proc.returncode != 0 or not pdf.exists():
        return {
            "project": project,
            "compiled": False,
            "reason": "tectonic_failed",
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-1000:],
        }

    return {
        "project": project,
        "compiled": True,
        "pdf_path": str(pdf),
        "bytes": pdf.stat().st_size,
        "tectonic_bin": bin_path,
    }
