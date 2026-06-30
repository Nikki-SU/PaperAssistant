"""排版导出 API（SPEC §五 + §7.5 + §九 + H/ζ 阶段）。

四个端点：
1. POST /api/typesetting/{project}/export            合并 paper/*.md → manuscript.md
2. POST /api/typesetting/{project}/render_tex        基于 paper/template.tex 渲染变量 → paper/manuscript.tex
3. POST /api/typesetting/{project}/compile_pdf       调用指定 LaTeX 引擎编译 manuscript.tex → manuscript.pdf
4. GET  /api/typesetting/engines/detect              检测本机可用 LaTeX 引擎

ζ 阶段更新：LaTeX 引擎策略
- 主力：MiKTeX（xelatex）—— 本机 PATH 上的 xelatex.exe，化学论文中英混排首选
- 备选：pdflatex / lualatex（PATH 上的同名 exe，MiKTeX/TeX Live 安装后自带）
- 降级：Tectonic（单 exe，按需下载宏包，作为兜底）

compile_pdf 接受 query 参数 ``engine``：
- ``auto``（默认）：按 xelatex → pdflatex → lualatex → tectonic 顺序挑第一个可用
- ``xelatex`` / ``pdflatex`` / ``lualatex`` / ``tectonic``：强制指定

引擎路径解析：
- xelatex/pdflatex/lualatex：PATH 上同名 exe（MiKTeX/TeX Live 装好就在）
- tectonic：``PAPERASSISTANT_TECTONIC_BIN`` / ``TECTONIC_BIN`` / PATH

错误解析：编译失败时读取 paper/manuscript.log，提取 ``!`` 开头的错误段及 ``l.行号``。

多遍编译：检测到 latexmk 时优先用 ``latexmk -<engine> -interaction=nonstopmode``
自动处理引用 / 目录回填 / bibtex/biber 调度；找不到 latexmk 则直接调单遍引擎。
Tectonic 内部本就处理多遍，不走 latexmk。
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


# 引擎 id → PATH 上的 binary 名（不含 .exe）
ENGINE_BINS = {
    "xelatex": "xelatex",
    "pdflatex": "pdflatex",
    "lualatex": "lualatex",
    "tectonic": "tectonic",
}
# auto 模式优先级顺序
ENGINE_AUTO_ORDER = ["xelatex", "pdflatex", "lualatex", "tectonic"]


def _paper_dir(project: str) -> Path:
    return get_settings().projects_dir / project / "paper"


def _resolve_tectonic_bin() -> str | None:
    """Tectonic 专用解析（兼容旧的内嵌 sidecar 方案）。"""
    for env_key in ("PAPERASSISTANT_TECTONIC_BIN", "TECTONIC_BIN"):
        v = os.environ.get(env_key)
        if v and Path(v).exists():
            return v
    return shutil.which("tectonic") or shutil.which("tectonic.exe")


def _resolve_engine(engine_id: str) -> str | None:
    """根据 engine_id 返回可执行文件绝对路径；找不到返回 None。"""
    if engine_id == "tectonic":
        return _resolve_tectonic_bin()
    bin_name = ENGINE_BINS.get(engine_id)
    if not bin_name:
        return None
    return shutil.which(bin_name) or shutil.which(bin_name + ".exe")


def _resolve_latexmk() -> str | None:
    return shutil.which("latexmk") or shutil.which("latexmk.exe")


def _detect_engine_version(bin_path: str, engine_id: str) -> str | None:
    """跑 --version 取首行；超时/失败返回 None。"""
    try:
        flag = "-V" if engine_id == "tectonic" else "--version"
        proc = subprocess.run(
            [bin_path, flag],
            capture_output=True, text=True, timeout=10,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        first = out.split("\n", 1)[0].strip()
        return first[:140] if first else None
    except Exception:
        return None


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
        if "\\end{document}" in rendered:
            rendered = rendered.replace(
                "\\end{document}",
                body + "\n\\end{document}",
                1,
            )
        else:
            rendered = rendered + "\n" + body + "\n"
    return rendered


_LOG_LINE_NUM_RE = re.compile(r"^l\.(\d+)\s*(.*)?$")


def _parse_latex_log(log_path: Path, max_errors: int = 8) -> list[dict]:
    """从 LaTeX .log 文件提取错误段。

    返回 list of {
      "kind": "error",
      "message": str,    # ! 开头那行去掉前缀
      "line": int | None,
      "context": str,    # 紧跟错误的上下文（含 l.行号 行）
    }
    """
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    errors: list[dict] = []
    i = 0
    n = len(lines)
    while i < n and len(errors) < max_errors:
        raw = lines[i]
        if raw.startswith("!"):
            msg = raw.lstrip("! ").strip()
            line_num: int | None = None
            ctx: list[str] = []
            j = i + 1
            # 错误段最多看 12 行
            while j < n and j < i + 12:
                ln = lines[j]
                if line_num is None:
                    m = _LOG_LINE_NUM_RE.match(ln)
                    if m:
                        line_num = int(m.group(1))
                if ln.strip():
                    ctx.append(ln)
                if ln.startswith("?"):
                    break
                j += 1
            errors.append({
                "kind": "error",
                "message": msg,
                "line": line_num,
                "context": "\n".join(ctx[:6]).strip(),
            })
            i = j + 1
            continue
        i += 1
    return errors


def _needs_bibliography(tex_src: str) -> bool:
    """tex 源是否声明了参考文献（用于决定是否需要多遍编译）。"""
    return bool(
        re.search(r"\\bibliography\s*\{", tex_src)
        or re.search(r"\\addbibresource\s*\{", tex_src)
    )


# ============================================================
#  端点
# ============================================================


@router.get("/engines/detect")
def detect_engines() -> dict:
    """检测本机可用 LaTeX 引擎，前端用于决定下拉框可选项 + 是否显示安装引导。"""
    results: list[dict] = []
    for engine_id in ENGINE_AUTO_ORDER:
        bin_path = _resolve_engine(engine_id)
        if bin_path:
            version = _detect_engine_version(bin_path, engine_id)
            results.append({
                "id": engine_id,
                "available": True,
                "bin_path": bin_path,
                "version": version,
            })
        else:
            results.append({
                "id": engine_id,
                "available": False,
                "bin_path": None,
                "version": None,
            })
    has_any = any(r["available"] for r in results)
    latexmk = _resolve_latexmk()
    return {
        "engines": results,
        "has_any": has_any,
        "auto_pick": next((r["id"] for r in results if r["available"]), None),
        "latexmk_bin": latexmk,
        "install_hint": (
            "未检测到任何 LaTeX 引擎。推荐安装 MiKTeX Basic（约 200MB，含 xelatex/pdflatex/lualatex）。"
            "下载地址：https://miktex.org/download （选 Basic Installer for Windows），"
            "安装时把 \"Install missing packages on-the-fly\" 设为 Yes，即可零配置开箱使用。"
            "国内镜像（更快）：https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/setup/windows-x64/"
        ) if not has_any else None,
    }


@router.post("/{project}/export")
def export_manuscript(project: str) -> dict:
    """合并 paper/ 下所有 *.md 为 manuscript.md（保持文件名顺序）。"""
    paper_dir = _paper_dir(project)
    if not paper_dir.exists():
        raise HTTPException(status_code=404, detail="项目论文目录不存在")
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
def compile_pdf(project: str, engine: str = "auto") -> dict:
    """调用指定 LaTeX 引擎编译 paper/manuscript.tex → paper/manuscript.pdf。

    Query 参数：
    - ``engine``：``auto`` / ``xelatex`` / ``pdflatex`` / ``lualatex`` / ``tectonic``

    引擎不可用时返回 ``{compiled: false, reason: "no_engine"}`` 或 ``{reason: "engine_not_found"}``，
    不抛 500，由前端引导用户安装 MiKTeX 或切换引擎。
    """
    paper_dir = _paper_dir(project)
    tex = paper_dir / "manuscript.tex"
    if not tex.exists():
        raise HTTPException(status_code=404, detail="paper/manuscript.tex 不存在；先 POST /render_tex")

    # 1. 解析引擎
    engine_id = (engine or "auto").strip().lower()
    if engine_id == "auto":
        picked: str | None = None
        picked_bin: str | None = None
        for cand in ENGINE_AUTO_ORDER:
            b = _resolve_engine(cand)
            if b:
                picked, picked_bin = cand, b
                break
        if not picked:
            return {
                "project": project,
                "compiled": False,
                "reason": "no_engine",
                "engine_requested": "auto",
                "hint": (
                    "本机未检测到任何 LaTeX 引擎。请安装 MiKTeX Basic："
                    "https://miktex.org/download （含 xelatex/pdflatex/lualatex，约 200MB）。"
                    "安装时勾选 \"Install missing packages on-the-fly = Yes\"。"
                ),
            }
        engine_id = picked
        bin_path: str = picked_bin  # type: ignore[assignment]
    else:
        if engine_id not in ENGINE_BINS:
            return {
                "project": project,
                "compiled": False,
                "reason": "engine_not_found",
                "engine_requested": engine_id,
                "hint": f"不支持的引擎 '{engine_id}'。可选：auto / xelatex / pdflatex / lualatex / tectonic。",
            }
        resolved = _resolve_engine(engine_id)
        if not resolved:
            return {
                "project": project,
                "compiled": False,
                "reason": "engine_not_found",
                "engine_requested": engine_id,
                "hint": (
                    f"未在 PATH 中找到 {engine_id}。"
                    + ("请安装 MiKTeX 或 TeX Live；MiKTeX 安装后 xelatex/pdflatex/lualatex 会自动加入 PATH。"
                       if engine_id != "tectonic"
                       else "Tectonic 未配置；请设置 PAPERASSISTANT_TECTONIC_BIN 或把 tectonic.exe 加入 PATH。")
                ),
            }
        bin_path = resolved

    # 2. 构造编译命令
    tex_src = read_text(tex)
    needs_bib = _needs_bibliography(tex_src)
    latexmk_bin = _resolve_latexmk() if engine_id != "tectonic" else None
    used_latexmk = False

    if engine_id == "tectonic":
        # Tectonic 内部处理多遍 + 联网装包
        cmd = [bin_path, "--outdir", str(paper_dir), str(tex)]
    elif latexmk_bin:
        # latexmk 自动决定遍数 + 调度 bibtex/biber
        flag = f"-{engine_id}"  # -xelatex / -pdflatex / -lualatex
        cmd = [
            latexmk_bin,
            flag,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={paper_dir}",
            str(tex),
        ]
        used_latexmk = True
    else:
        # 单跑一遍；若声明了参考文献，跑两遍交叉引用
        cmd = [
            bin_path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={paper_dir}",
            str(tex),
        ]

    # 3. 执行（如果是 needs_bib 且没 latexmk 且非 tectonic，跑两遍）
    proc = None
    run_count = 0
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=240, cwd=str(paper_dir),
        )
        run_count = 1
        if (
            engine_id != "tectonic"
            and not used_latexmk
            and needs_bib
            and proc.returncode == 0
        ):
            # 跑第二遍以回填引用/目录（不跑 bibtex/biber，简化版）
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=240, cwd=str(paper_dir),
            )
            run_count = 2
    except subprocess.TimeoutExpired:
        return {
            "project": project,
            "compiled": False,
            "reason": "timeout",
            "engine_used": engine_id,
            "engine_bin": bin_path,
            "used_latexmk": used_latexmk,
            "hint": (
                "LaTeX 编译超过 240 秒，已中止。"
                + ("Tectonic 首次编译需联网下载约 30-50MB 宏包，网络慢时会超时；首次成功后会缓存。"
                   if engine_id == "tectonic"
                   else "若使用 MiKTeX 首次编译，缺包会自动下载，网络慢时会超时；先在网络好时手动跑一次预下载。")
            ),
        }
    except FileNotFoundError:
        return {
            "project": project,
            "compiled": False,
            "reason": "engine_not_found",
            "engine_requested": engine_id,
            "engine_bin": bin_path,
            "hint": f"{engine_id} 可执行路径已失效：{bin_path}",
        }

    # 4. 判断结果
    pdf = paper_dir / (tex.stem + ".pdf")
    log_path = paper_dir / (tex.stem + ".log")
    log_errors = _parse_latex_log(log_path)

    if proc.returncode != 0 or not pdf.exists():
        # 启发式：网络/下载相关
        combined = ((proc.stderr or "") + "\n" + (proc.stdout or "")).lower()
        net_kw = ("ctan", "download", "network", "timed out", "timeout", "connection", "resolve", "dns", "miktex-pk")
        looks_like_network = any(k in combined for k in net_kw)
        if looks_like_network:
            hint = (
                f"{engine_id} 编译失败，错误信息中含网络关键词。"
                + ("Tectonic 首次需联网从 CTAN 下载宏包；首次成功后可离线。"
                   if engine_id == "tectonic"
                   else "MiKTeX 首次遇到缺包会联网下载；若被防火墙拦截，请确认网络并重试。")
            )
        elif log_errors:
            hint = (
                f"{engine_id} 返回非零退出码。下方 errors 列出 LaTeX .log 中的错误段（含行号），"
                f"对照 manuscript.tex 定位即可。"
            )
        else:
            hint = (
                f"{engine_id} 返回非零退出码，但 .log 未能解析到结构化错误。"
                f"查看 stderr_tail / stdout_tail 定位问题。"
            )
        return {
            "project": project,
            "compiled": False,
            "reason": "compile_failed",
            "engine_used": engine_id,
            "engine_bin": bin_path,
            "used_latexmk": used_latexmk,
            "run_count": run_count,
            "returncode": proc.returncode,
            "hint": hint,
            "errors": log_errors,
            "log_path": str(log_path) if log_path.exists() else None,
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-1000:],
        }

    return {
        "project": project,
        "compiled": True,
        "pdf_path": str(pdf),
        "bytes": pdf.stat().st_size,
        "engine_used": engine_id,
        "engine_bin": bin_path,
        "used_latexmk": used_latexmk,
        "run_count": run_count,
        "warnings": [e for e in log_errors if e.get("kind") == "warning"],
        "log_path": str(log_path) if log_path.exists() else None,
    }
