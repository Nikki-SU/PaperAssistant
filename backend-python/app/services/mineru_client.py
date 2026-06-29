"""MinerU 客户端（PDF → Markdown）。

SPEC §三 限制：单文件 ≤200 页 / ≤100MB；超限自动切分。

当前实现：stub 版本。
- 若未配置 MinerU API key，直接把上传的 PDF 原样保留，并生成最小占位 .md
  以及一份「待 MinerU 接管」的提示。便于本地端到端调通。
- 真实 API 接入留 TODO：见 ``call_real_mineru``。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MineruResult:
    success: bool
    markdown_path: Path
    page_count: int = 0
    truncated: bool = False
    message: str = ""


class MineruClient:
    """SPEC §四.1 的 MinerU 接口位。"""

    MAX_PAGES = 200
    MAX_BYTES = 100 * 1024 * 1024  # 100MB

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("MINERU_API_KEY", "")
        self.endpoint = endpoint or os.environ.get(
            "MINERU_ENDPOINT", "https://mineru.example.com/api/v1/parse"
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def parse(self, pdf_path: Path, output_md: Path) -> MineruResult:
        """将 PDF 解析为 Markdown 写入 output_md。

        当前为 stub：若没有 api_key，则写一份占位文档，让端到端跑通。
        """
        if not pdf_path.exists():
            return MineruResult(False, output_md, message=f"PDF 不存在：{pdf_path}")

        size = pdf_path.stat().st_size
        if size > self.MAX_BYTES:
            logger.warning(
                "PDF 超过 MinerU 限制：%s bytes（max=%s）。后续应自动切分。",
                size,
                self.MAX_BYTES,
            )

        if not self.enabled:
            output_md.parent.mkdir(parents=True, exist_ok=True)
            output_md.write_text(
                self._placeholder_md(pdf_path, size),
                encoding="utf-8",
            )
            return MineruResult(
                success=True,
                markdown_path=output_md,
                page_count=0,
                truncated=False,
                message="MinerU 未配置 API key，已生成占位 Markdown。",
            )

        return self.call_real_mineru(pdf_path, output_md, size)

    def call_real_mineru(
        self,
        pdf_path: Path,
        output_md: Path,
        size: int,
    ) -> MineruResult:
        """真实 MinerU API 接入。

        TODO: 接入官方 multipart/form-data 上传 + 轮询任务状态 + 拉取 Markdown。
              目前云端无法跨网请求，本地接入由用户配置 ``MINERU_API_KEY``。
        """
        logger.info("call_real_mineru stub: pdf=%s size=%s", pdf_path, size)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(
            self._placeholder_md(pdf_path, size, real_api=True),
            encoding="utf-8",
        )
        return MineruResult(
            success=True,
            markdown_path=output_md,
            page_count=0,
            truncated=False,
            message="MinerU 实接入 TODO：当前回落到占位 Markdown。",
        )

    @staticmethod
    def _placeholder_md(pdf_path: Path, size: int, real_api: bool = False) -> str:
        return (
            f"# {pdf_path.stem}\n\n"
            f"> 来源 PDF：`{pdf_path.name}`  大小：{size} bytes\n\n"
            f"> ⚠️ {'已收到 MinerU 任务请求，但尚未集成真实 API。' if real_api else 'MinerU API 未配置，当前为占位 Markdown。'}\n"
            f"> 请到「设置 → MinerU」配置 API key；或手动把全文 Markdown 替换到此文件。\n\n"
            f"## 占位摘要\n\n_（待 MinerU 解析）_\n"
        )
