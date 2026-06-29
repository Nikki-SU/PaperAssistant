"""文件监控服务（SPEC §九：监控目录 → 自动检测 → MinerU 转换）。

设计：
- 后台 daemon 线程，使用 watchdog 监听 settings.monitor_dir
- 检测到新 .pdf 文件 → 等待文件大小稳定（避免读到半写文件） → 调 MinerU 转换
- 输出 Markdown 放到 {data_root}/auto_imported/{stem}.md
- 在 {monitor_dir}/.processed_index.csv 记录已处理（hash + timestamp + result）
- 失败降级，写日志 + da.report，不影响主流程
- watchdog 不可用时，自动退回 polling 模式（30s 轮询一次）

启动/停止由 main.py lifespan 控制。
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Set

from ..config import get_settings
from ..lib import debug_assistant as da
from .mineru_client import MineruClient

logger = logging.getLogger(__name__)

PROCESSED_INDEX_NAME = ".processed_index.csv"
STABLE_WAIT_S = 2.0          # 文件大小连续两次相同视为稳定
STABLE_POLL_INTERVAL = 0.5
POLL_INTERVAL_S = 30         # watchdog 不可用时的轮询间隔


@dataclass
class ProcessRecord:
    file_name: str
    sha1: str
    processed_at: str
    success: str
    output_md: str
    message: str


def _sha1_of(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                buf = f.read(chunk)
                if not buf:
                    break
                h.update(buf)
    except Exception:  # noqa: BLE001
        return ""
    return h.hexdigest()


def _is_stable(path: Path) -> bool:
    """等待文件大小稳定 STABLE_WAIT_S（避免读到正在写入的不完整文件）。"""
    try:
        prev = path.stat().st_size
    except OSError:
        return False
    end = time.time() + STABLE_WAIT_S
    while time.time() < end:
        time.sleep(STABLE_POLL_INTERVAL)
        try:
            cur = path.stat().st_size
        except OSError:
            return False
        if cur != prev:
            prev = cur
            end = time.time() + STABLE_WAIT_S
    return True


def _read_processed_index(monitor_dir: Path) -> Set[str]:
    """读已处理 sha1 集合。"""
    idx = monitor_dir / PROCESSED_INDEX_NAME
    if not idx.exists():
        return set()
    out: Set[str] = set()
    try:
        with open(idx, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sha = (row.get("sha1") or "").strip()
                if sha:
                    out.add(sha)
    except Exception:  # noqa: BLE001
        return set()
    return out


def _append_processed_index(monitor_dir: Path, record: ProcessRecord) -> None:
    idx = monitor_dir / PROCESSED_INDEX_NAME
    is_new = not idx.exists()
    monitor_dir.mkdir(parents=True, exist_ok=True)
    with open(idx, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["file_name", "sha1", "processed_at", "success", "output_md", "message"])
        writer.writerow([
            record.file_name, record.sha1, record.processed_at,
            record.success, record.output_md, record.message,
        ])


def _process_one_pdf(
    pdf_path: Path,
    monitor_dir: Path,
    output_root: Path,
    mineru: MineruClient,
    processed_set: Set[str],
    on_done: Optional[Callable[[ProcessRecord], None]] = None,
) -> Optional[ProcessRecord]:
    """对单个 PDF 跑 MinerU。"""
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        return None
    if not _is_stable(pdf_path):
        logger.info("[file_watcher] %s 大小不稳定，跳过", pdf_path.name)
        return None

    sha = _sha1_of(pdf_path)
    if not sha:
        return None
    if sha in processed_set:
        logger.debug("[file_watcher] %s 已处理过（sha1=%s），跳过", pdf_path.name, sha[:8])
        return None

    output_md = output_root / f"{pdf_path.stem}.md"
    output_root.mkdir(parents=True, exist_ok=True)

    logger.info("[file_watcher] 开始处理 %s（sha1=%s）", pdf_path.name, sha[:8])
    try:
        result = mineru.parse(pdf_path, output_md)
        rec = ProcessRecord(
            file_name=pdf_path.name,
            sha1=sha,
            processed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            success=str(result.success).lower(),
            output_md=str(output_md),
            message=result.message or "",
        )
        _append_processed_index(monitor_dir, rec)
        processed_set.add(sha)
        if on_done:
            try:
                on_done(rec)
            except Exception:  # noqa: BLE001
                logger.exception("on_done 回调异常")
        logger.info(
            "[file_watcher] 完成 %s success=%s → %s",
            pdf_path.name, result.success, output_md,
        )
        return rec
    except Exception as e:  # noqa: BLE001
        logger.exception("[file_watcher] 处理 %s 异常", pdf_path.name)
        da.report(
            error=e, severity="error",
            stage="file-watcher",
            user_action=f"watch process {pdf_path.name}",
            context={"pdf": str(pdf_path), "monitor_dir": str(monitor_dir)},
        )
        rec = ProcessRecord(
            file_name=pdf_path.name, sha1=sha,
            processed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            success="false", output_md="",
            message=f"{type(e).__name__}: {e}",
        )
        _append_processed_index(monitor_dir, rec)
        processed_set.add(sha)
        return rec


class FileWatcher:
    """守护线程的 PDF 监控器。"""

    def __init__(
        self,
        monitor_dir: Optional[Path] = None,
        output_root: Optional[Path] = None,
        on_done: Optional[Callable[[ProcessRecord], None]] = None,
    ) -> None:
        s = get_settings()
        self.monitor_dir = Path(monitor_dir) if monitor_dir else s.monitor_dir
        # 默认输出到 data_root/auto_imported/
        self.output_root = Path(output_root) if output_root else (s.data_root / "auto_imported")
        self.mineru = MineruClient()
        self.on_done = on_done
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._processed: Set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.monitor_dir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._processed = _read_processed_index(self.monitor_dir)
        logger.info(
            "[file_watcher] 启动监控 %s（已记录 %d 个处理项），输出到 %s",
            self.monitor_dir, len(self._processed), self.output_root,
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="file-watcher")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=timeout)
        logger.info("[file_watcher] 已停止")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def trigger_scan(self) -> int:
        """手动触发一次扫描，返回处理数。"""
        return self._scan_once()

    # ---- 内部 ----

    def _run(self) -> None:
        # 先尝试 watchdog
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, outer: "FileWatcher"):
                    self.outer = outer

                def on_created(self, event):  # type: ignore[override]
                    if event.is_directory:
                        return
                    p = Path(event.src_path)
                    if p.suffix.lower() == ".pdf":
                        _process_one_pdf(
                            p, self.outer.monitor_dir, self.outer.output_root,
                            self.outer.mineru, self.outer._processed, self.outer.on_done,
                        )

                def on_moved(self, event):  # type: ignore[override]
                    if event.is_directory:
                        return
                    p = Path(event.dest_path)
                    if p.suffix.lower() == ".pdf":
                        _process_one_pdf(
                            p, self.outer.monitor_dir, self.outer.output_root,
                            self.outer.mineru, self.outer._processed, self.outer.on_done,
                        )

            observer = Observer()
            observer.schedule(_Handler(self), str(self.monitor_dir), recursive=False)
            observer.start()
            logger.info("[file_watcher] watchdog 模式已启动")

            # 立即做一次全量扫描（启动时已存在的文件）
            self._scan_once()

            while not self._stop.is_set():
                time.sleep(1.0)
            observer.stop()
            observer.join(timeout=5.0)
            return
        except ImportError:
            logger.info("[file_watcher] watchdog 不可用，退回 polling 模式（%ds）", POLL_INTERVAL_S)
        except Exception:  # noqa: BLE001
            logger.exception("[file_watcher] watchdog 异常，退回 polling")

        # Polling 兜底
        while not self._stop.is_set():
            self._scan_once()
            for _ in range(POLL_INTERVAL_S):
                if self._stop.is_set():
                    return
                time.sleep(1.0)

    def _scan_once(self) -> int:
        if not self.monitor_dir.exists():
            return 0
        count = 0
        try:
            for p in sorted(self.monitor_dir.iterdir()):
                if p.is_file() and p.suffix.lower() == ".pdf":
                    rec = _process_one_pdf(
                        p, self.monitor_dir, self.output_root,
                        self.mineru, self._processed, self.on_done,
                    )
                    if rec:
                        count += 1
        except Exception:  # noqa: BLE001
            logger.exception("[file_watcher] scan 异常")
        return count


# 全局单例
_watcher: Optional[FileWatcher] = None


def get_watcher() -> FileWatcher:
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher()
    return _watcher


def start_watcher() -> None:
    get_watcher().start()


def stop_watcher() -> None:
    if _watcher:
        _watcher.stop()
