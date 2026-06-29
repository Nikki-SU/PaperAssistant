"""MinerU 客户端（PDF → Markdown）—— 真实 API 接入。

接入逻辑（参考 https://mineru.net/doc/docs/）：
1. POST /api/v4/file-urls/batch  →  拿到 N 个 presigned upload URL 与 batch_id
2. PUT 文件到 presigned URL（不带 Content-Type 头，直接二进制）
3. 任务由服务端在上传完成后自动开始
4. 轮询 GET /api/v4/extract-results/batch/{batch_id} 直到 state == "done" 或失败
5. 拉取每个文件的 full_zip_url，解压取 full.md（兼容 .mdmd 等命名）

铁律：
- key 未配置 / 网络失败 / 服务端报错时，自动降级为占位 Markdown（不阻塞业务）
- 任何异常都通过 lib.debug_assistant.report 上报
- SPEC §三 限制：单文件 ≤200 页 / ≤200MB（接口侧硬限制）
"""
from __future__ import annotations

import io
import json
import logging
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import get_settings
from ..lib import debug_assistant as da

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mineru.net/api/v4"
DEFAULT_MODEL_VERSION = "vlm"  # MinerU 官方推荐的多模态模型
MAX_BYTES = 200 * 1024 * 1024  # 200MB
POLL_INTERVAL_S = 4
POLL_MAX_ROUNDS = 60  # 4 分钟（4s * 60）足够多数 PDF


@dataclass
class MineruResult:
    success: bool
    markdown_path: Path
    page_count: int = 0
    truncated: bool = False
    message: str = ""


class MineruClient:
    """SPEC §四.1 的 MinerU 接口位。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 30.0,
        poll_interval: float = POLL_INTERVAL_S,
        max_poll_rounds: int = POLL_MAX_ROUNDS,
    ) -> None:
        # 优先级：构造参数 > settings.secret > 环境变量
        cfg_key, cfg_endpoint = _read_role_config("mineru")
        self.api_key = api_key or cfg_key or ""
        self.endpoint = (endpoint or cfg_endpoint or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_rounds = max_poll_rounds

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # ---------------- 主入口 ----------------

    def parse(self, pdf_path: Path, output_md: Path) -> MineruResult:
        """将本地 PDF 解析为 Markdown 并写入 output_md。

        失败必须降级；不抛异常给业务。
        """
        if not pdf_path.exists():
            return MineruResult(False, output_md, message=f"PDF 不存在：{pdf_path}")

        size = pdf_path.stat().st_size
        if size > MAX_BYTES:
            msg = f"PDF 超过 MinerU 限制：{size} bytes（max={MAX_BYTES}）。"
            logger.warning(msg)
            self._write_placeholder(output_md, pdf_path, size, msg)
            return MineruResult(False, output_md, page_count=0, truncated=True, message=msg)

        if not self.enabled:
            self._write_placeholder(
                output_md, pdf_path, size,
                "MinerU 未配置 API Key，已生成占位 Markdown。请到「设置 → MinerU」配置。",
            )
            return MineruResult(
                success=True, markdown_path=output_md,
                message="MinerU 未配置 API Key，已降级为占位 Markdown。",
            )

        try:
            return self._call_real(pdf_path, output_md, size)
        except Exception as e:  # noqa: BLE001
            logger.exception("MinerU 实接入失败，已降级")
            da.report(
                error=e,
                severity="error",
                stage="literature-upload",
                user_action="MinerU parse",
                context={"pdf": pdf_path.name, "size": size, "endpoint": self.endpoint},
            )
            self._write_placeholder(
                output_md, pdf_path, size,
                f"MinerU 调用失败（已降级）：{type(e).__name__}: {e}",
            )
            return MineruResult(
                success=False, markdown_path=output_md, message=f"{type(e).__name__}: {e}",
            )

    # ---------------- 真实 HTTP 流程 ----------------

    def _call_real(self, pdf_path: Path, output_md: Path, size: int) -> MineruResult:
        # Step 1: 申请 presigned upload URL
        batch_id, upload_url = self._request_upload_url(pdf_path.name)
        logger.info("MinerU batch_id=%s upload_url 已签发", batch_id)

        # Step 2: PUT 文件
        self._put_file(upload_url, pdf_path)
        logger.info("MinerU 文件已上传：%s", pdf_path.name)

        # Step 3: 轮询任务状态
        result_entry = self._poll_batch(batch_id, target_name=pdf_path.name)
        if not result_entry:
            raise RuntimeError(f"MinerU 任务超时未完成 (batch={batch_id})")

        state = (result_entry.get("state") or "").lower()
        if state not in ("done", "success"):
            err_msg = result_entry.get("err_msg") or result_entry.get("error") or "unknown"
            raise RuntimeError(f"MinerU 任务失败 state={state}, err={err_msg}")

        # Step 4: 取 markdown
        zip_url = result_entry.get("full_zip_url") or ""
        if not zip_url:
            raise RuntimeError("MinerU 任务完成但缺少 full_zip_url")

        md_text = self._download_and_extract_md(zip_url)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")

        # 提取页数（MinerU 返回里通常带 extract_progress 或 page_count）
        pages = int(result_entry.get("page_count") or 0)
        return MineruResult(
            success=True,
            markdown_path=output_md,
            page_count=pages,
            truncated=False,
            message=f"MinerU 解析成功，页数 ≈ {pages}",
        )

    def _request_upload_url(self, file_name: str) -> tuple[str, str]:
        payload = {
            "files": [{"name": file_name, "is_ocr": True}],
            "model_version": DEFAULT_MODEL_VERSION,
            "enable_formula": True,
            "enable_table": True,
            "language": "auto",
        }
        resp = self._http_post_json("/file-urls/batch", payload)
        if int(resp.get("code", -1)) != 0:
            raise RuntimeError(f"申请上传 URL 失败：{resp.get('msg')}")
        data = resp.get("data", {})
        batch_id = data.get("batch_id") or ""
        urls = data.get("file_urls") or data.get("files") or []
        if not batch_id or not urls:
            raise RuntimeError(f"MinerU 响应缺 batch_id 或 file_urls: {resp}")
        first = urls[0]
        upload_url = first if isinstance(first, str) else first.get("url", "")
        if not upload_url:
            raise RuntimeError(f"MinerU 未返回 upload URL: {resp}")
        return batch_id, upload_url

    def _put_file(self, upload_url: str, pdf_path: Path) -> None:
        with pdf_path.open("rb") as f:
            body = f.read()
        req = urllib.request.Request(upload_url, data=body, method="PUT")
        with urllib.request.urlopen(req, timeout=self.timeout * 4) as resp:
            _ = resp.read()

    def _poll_batch(self, batch_id: str, target_name: str) -> Optional[dict]:
        url = f"/extract-results/batch/{batch_id}"
        for round_idx in range(self.max_poll_rounds):
            time.sleep(self.poll_interval if round_idx > 0 else 1.0)
            resp = self._http_get_json(url)
            if int(resp.get("code", -1)) != 0:
                logger.warning("MinerU 轮询返回 code=%s msg=%s", resp.get("code"), resp.get("msg"))
                continue
            extract_result = (resp.get("data") or {}).get("extract_result") or []
            for entry in extract_result:
                if (entry.get("file_name") or "").strip() == target_name:
                    state = (entry.get("state") or "").lower()
                    if state in ("done", "failed", "error", "success"):
                        return entry
                    # 进行中：继续轮询
                    break
        return None

    def _download_and_extract_md(self, zip_url: str) -> str:
        with urllib.request.urlopen(zip_url, timeout=self.timeout * 4) as resp:
            raw = resp.read()
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"MinerU 返回的 zip 解压失败：{e}") from e

        # 优先找 full.md / *.md
        candidates: list[str] = []
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".md"):
                candidates.append(name)
        if not candidates:
            raise RuntimeError(f"MinerU zip 内未找到 .md 文件：{zf.namelist()[:8]}")
        # 偏好 full.md
        candidates.sort(key=lambda n: (0 if "full" in n.lower() else 1, len(n)))
        with zf.open(candidates[0]) as f:
            return f.read().decode("utf-8", errors="replace")

    # ---------------- HTTP 底座 ----------------

    def _http_post_json(self, path: str, payload: dict) -> dict:
        url = self.endpoint + path
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500] if e.fp else ""
            raise RuntimeError(f"HTTP {e.code} {detail}") from e

    def _http_get_json(self, path: str) -> dict:
        url = self.endpoint + path
        req = urllib.request.Request(
            url, method="GET",
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "*/*"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---------------- 占位回退 ----------------

    @staticmethod
    def _write_placeholder(output_md: Path, pdf_path: Path, size: int, note: str) -> None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(
            (
                f"# {pdf_path.stem}\n\n"
                f"> 来源 PDF：`{pdf_path.name}`  大小：{size} bytes\n\n"
                f"> ⚠️ {note}\n\n"
                f"## 占位摘要\n\n_（待 MinerU 解析或人工补充）_\n"
            ),
            encoding="utf-8",
        )


# ---------------- 从全局 config 读凭证 ----------------

def _read_role_config(role: str) -> tuple[str, str]:
    """读 api_config.csv 与 api_keys.secret 拿到指定 role 的 (key, endpoint)。
    任何异常都返回 ("","")，由调用方处理。
    """
    try:
        s = get_settings()
        endpoint = ""
        if s.api_config_csv.exists():
            import csv
            with s.api_config_csv.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if (row.get("role") or "").strip() == role:
                        endpoint = (row.get("endpoint") or "").strip()
                        break
        api_key = ""
        if s.api_keys_secret.exists():
            for line in s.api_keys_secret.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == role:
                    api_key = v.strip()
                    break
        return api_key, endpoint
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 %s 配置失败：%s", role, e)
        return "", ""
