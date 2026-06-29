"""PaperAssistant backend 配置。

数据根目录默认：%USERPROFILE%/Documents/PaperAssistant（Windows）
                ~/Documents/PaperAssistant       （其他平台）
首次启动由 GUI 选择，写入 ~/.paperassistant_root 作为指针。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

POINTER_FILE = Path.home() / ".paperassistant_root"


@dataclass
class Settings:
    data_root: Path
    host: str = "127.0.0.1"
    port: int = 8181
    log_level: str = "INFO"

    # debug-assistant 接入
    debug_assistant_enabled: bool = True
    debug_assistant_host: str = "127.0.0.1"
    debug_assistant_port: int = 8765

    # 派生
    config_dir: Path = field(init=False)
    knowledge_dir: Path = field(init=False)
    library_dir: Path = field(init=False)
    library_fulltext_dir: Path = field(init=False)
    library_cards_dir: Path = field(init=False)
    library_cards_csv: Path = field(init=False)
    projects_dir: Path = field(init=False)
    temp_dir: Path = field(init=False)
    monitor_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data_root = Path(self.data_root).expanduser().resolve()
        self.config_dir = self.data_root / "config"
        self.knowledge_dir = self.data_root / "knowledge"
        self.library_dir = self.data_root / "library"
        self.library_fulltext_dir = self.library_dir / "fulltext"
        self.library_cards_dir = self.library_dir / "cards"
        self.library_cards_csv = self.library_cards_dir / "cards.csv"
        self.projects_dir = self.data_root / "projects"
        self.temp_dir = self.data_root / "temp"
        self.monitor_dir = self.temp_dir / "monitor"

    def ensure_dirs(self) -> None:
        for d in (
            self.config_dir,
            self.knowledge_dir,
            self.library_fulltext_dir,
            self.library_cards_dir,
            self.projects_dir,
            self.temp_dir,
            self.monitor_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def _read_pointer() -> Optional[Path]:
    if POINTER_FILE.exists():
        s = POINTER_FILE.read_text(encoding="utf-8").strip()
        if s:
            return Path(s)
    return None


def _default_root() -> Path:
    docs = Path.home() / "Documents"
    if docs.exists():
        return docs / "PaperAssistant"
    return Path.home() / "PaperAssistant"


def load_settings(data_root: Optional[str | os.PathLike] = None) -> Settings:
    chosen: Optional[Path] = None
    if data_root:
        chosen = Path(data_root)
    elif os.environ.get("PAPERASSISTANT_DATA_ROOT"):
        chosen = Path(os.environ["PAPERASSISTANT_DATA_ROOT"])
    else:
        chosen = _read_pointer()
    if chosen is None:
        chosen = _default_root()
    chosen = chosen.expanduser().resolve()
    POINTER_FILE.write_text(str(chosen), encoding="utf-8")

    s = Settings(
        data_root=chosen,
        host=os.environ.get("PAPERASSISTANT_HOST", "127.0.0.1"),
        port=int(os.environ.get("PAPERASSISTANT_PORT", "8181")),
        log_level=os.environ.get("PAPERASSISTANT_LOG_LEVEL", "INFO"),
        debug_assistant_enabled=(
            os.environ.get("DEBUG_ASSISTANT_ENABLED", "true").lower()
            not in ("false", "0", "no", "off")
        ),
        debug_assistant_host=os.environ.get("DEBUG_ASSISTANT_HOST", "127.0.0.1"),
        debug_assistant_port=int(os.environ.get("DEBUG_ASSISTANT_PORT", "8765")),
    )
    s.ensure_dirs()
    return s


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_data_root(path: str | os.PathLike) -> Settings:
    global _settings
    _settings = load_settings(path)
    return _settings
