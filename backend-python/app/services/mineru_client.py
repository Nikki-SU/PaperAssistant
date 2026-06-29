"""MinerU 客户端：PDF → Markdown 转换。

对应 SPEC：项目二 §九. MinerU 处理规则
约束：200页 / 100MB；超限自动切分。
"""
from __future__ import annotations
from pathlib import Path
import httpx


class MinerUClient:
    def __init__(self, api_key: str, base_url: str = "https://mineru.net/api", timeout: float = 600.0):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    async def convert(self, pdf_path: Path) -> Path:
        """转换单个 PDF → Markdown，返回输出文件路径。"""
        # TODO: 1) 检查页数/大小；2) 超限切分；3) POST /convert；4) 落盘 library/fulltext/{doi}.md
        raise NotImplementedError

    async def _split_if_needed(self, pdf_path: Path) -> list[Path]:
        """若超过 200 页或 100MB，按页数切分为多个子文件。"""
        # TODO
        raise NotImplementedError
