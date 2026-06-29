"""PDF 大文件切分（SPEC §九：大文件 自动切分）。

MinerU 单次上传限制 200 页 / 200MB；超出页数限制时，按 200 页一段切分为子 PDF，
分别送入 MinerU 转换，最后把多段 Markdown 按顺序拼接合并。

依赖：pypdf >= 4.0
失败必须降级：拿不到 pypdf / 切分异常时退回单次上传（由 MinerU 端硬限制兜底）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# SPEC §三：每段 ≤200 页
MAX_PAGES_PER_CHUNK = 200


@dataclass
class PdfChunk:
    """切分后的子 PDF。"""
    index: int                # 1-based
    total: int
    path: Path
    page_start: int           # 1-based, inclusive
    page_end: int             # 1-based, inclusive


@dataclass
class SplitResult:
    """整体切分结果。"""
    success: bool
    total_pages: int = 0
    chunks: List[PdfChunk] = field(default_factory=list)
    message: str = ""
    used_split: bool = False  # 是否实际进行了切分（False=未触发，原样使用）


def _get_pypdf():
    """延迟导入 pypdf。失败时返回 None。"""
    try:
        import pypdf  # type: ignore
        return pypdf
    except ImportError:
        try:
            import PyPDF2 as pypdf  # type: ignore
            return pypdf
        except ImportError:
            return None


def count_pages(pdf_path: Path) -> int:
    """读取 PDF 页数。读取失败返回 0。"""
    pypdf = _get_pypdf()
    if pypdf is None:
        logger.warning("pypdf 未安装，无法读取页数")
        return 0
    try:
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f, strict=False)
            return len(reader.pages)
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 PDF 页数失败：%s", e)
        return 0


def split_pdf(
    pdf_path: Path,
    output_dir: Path,
    max_pages: int = MAX_PAGES_PER_CHUNK,
) -> SplitResult:
    """把 pdf_path 按 max_pages 页一段切分到 output_dir/。

    若总页数 <= max_pages，不切分，返回 used_split=False 且 chunks 含原文件。
    若 pypdf 不可用或切分异常，返回 success=False（调用方应直接送原文件）。
    """
    if not pdf_path.exists():
        return SplitResult(success=False, message=f"PDF 不存在：{pdf_path}")

    pypdf = _get_pypdf()
    if pypdf is None:
        return SplitResult(success=False, message="pypdf 未安装")

    try:
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f, strict=False)
            total_pages = len(reader.pages)

            if total_pages <= 0:
                return SplitResult(success=False, message="PDF 页数为 0")

            # 不需要切分：返回单个 chunk 指向原文件
            if total_pages <= max_pages:
                return SplitResult(
                    success=True,
                    total_pages=total_pages,
                    used_split=False,
                    chunks=[PdfChunk(
                        index=1, total=1, path=pdf_path,
                        page_start=1, page_end=total_pages,
                    )],
                )

            # 切分
            output_dir.mkdir(parents=True, exist_ok=True)
            chunks: List[PdfChunk] = []
            num_chunks = (total_pages + max_pages - 1) // max_pages
            stem = pdf_path.stem

            for i in range(num_chunks):
                page_start = i * max_pages           # 0-based inclusive
                page_end = min(page_start + max_pages, total_pages)  # 0-based exclusive
                writer = pypdf.PdfWriter()
                for p in range(page_start, page_end):
                    writer.add_page(reader.pages[p])

                chunk_path = output_dir / f"{stem}__part{i+1:02d}of{num_chunks:02d}.pdf"
                with open(chunk_path, "wb") as out_f:
                    writer.write(out_f)
                chunks.append(PdfChunk(
                    index=i + 1, total=num_chunks, path=chunk_path,
                    page_start=page_start + 1, page_end=page_end,
                ))
                logger.info(
                    "PDF 切分 %d/%d：页 %d-%d → %s",
                    i + 1, num_chunks, page_start + 1, page_end, chunk_path.name,
                )

            return SplitResult(
                success=True,
                total_pages=total_pages,
                used_split=True,
                chunks=chunks,
                message=f"切分为 {num_chunks} 段（每段 ≤{max_pages} 页）",
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("PDF 切分失败")
        return SplitResult(success=False, message=f"切分失败：{type(e).__name__}: {e}")


def merge_markdowns(parts: List[str], chunks: Optional[List[PdfChunk]] = None) -> str:
    """合并多段 Markdown，按顺序拼接。

    chunks 可选，提供则在每段开头加 H2 分段标识（便于追溯哪段对应原 PDF 的哪些页）。
    """
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    out_lines: List[str] = []
    for i, md in enumerate(parts):
        if chunks and i < len(chunks):
            ch = chunks[i]
            out_lines.append(f"\n<!-- Part {ch.index}/{ch.total} · 原 PDF 页 {ch.page_start}-{ch.page_end} -->\n")
        elif i > 0:
            out_lines.append(f"\n<!-- Part {i + 1} -->\n")
        out_lines.append(md.rstrip())
        out_lines.append("\n")
    return "".join(out_lines)
