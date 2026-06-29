"""PaperAssistant backend 配置。

数据根目录默认：%USERPROFILE%/Documents/PaperAssistant（Windows）
                ~/Documents/PaperAssistant       （其他平台）
首次启动由 GUI 选择，写入 ~/.paperassistant_root 作为指针。
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

POINTER_FILE = Path.home() / ".paperassistant_root"


# 全局 config 目录下的 4 个 CSV（SPEC §5.1）
API_CONFIG_HEADERS = [
    "role", "endpoint", "model", "api_key_set", "timeout", "last_modified",
]
CATEGORY_CONFIG_HEADERS = ["perspective", "category", "subcategory"]
CUSTOM_FIELDS_HEADERS = ["field_name", "field_type", "description"]
APP_CONFIG_HEADERS = ["key", "value"]

# 默认的 4 个 AI 接口位（未配置）—— SPEC §4.5
DEFAULT_API_ROLES = [
    {"role": "mineru",    "endpoint": "", "model": "",  "api_key_set": "false", "timeout": "300", "last_modified": ""},
    {"role": "assistant", "endpoint": "", "model": "",  "api_key_set": "false", "timeout": "120", "last_modified": ""},
    {"role": "auditor",   "endpoint": "", "model": "",  "api_key_set": "false", "timeout": "120", "last_modified": ""},
    {"role": "secretary", "endpoint": "", "model": "",  "api_key_set": "false", "timeout": "60",  "last_modified": ""},
]

# 默认分类（SPEC §7.3）—— 社科 / 理科 默认子阶段
DEFAULT_CATEGORIES = [
    {"perspective": "social",  "category": "理论",      "subcategory": ""},
    {"perspective": "social",  "category": "研究设计",  "subcategory": ""},
    {"perspective": "social",  "category": "数据",      "subcategory": ""},
    {"perspective": "social",  "category": "结果和结论", "subcategory": ""},
    {"perspective": "science", "category": "实验",      "subcategory": ""},
    {"perspective": "science", "category": "表征",      "subcategory": ""},
    {"perspective": "science", "category": "机理",      "subcategory": ""},
    {"perspective": "science", "category": "结果和结论", "subcategory": ""},
]


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

    # 全局 config CSV 路径
    api_config_csv: Path = field(init=False)
    category_config_csv: Path = field(init=False)
    custom_fields_csv: Path = field(init=False)
    app_config_csv: Path = field(init=False)

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

        self.api_config_csv = self.config_dir / "api_config.csv"
        self.category_config_csv = self.config_dir / "category_config.csv"
        self.custom_fields_csv = self.config_dir / "custom_fields.csv"
        self.app_config_csv = self.config_dir / "app.csv"

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
        self._init_global_configs()

    def _init_global_configs(self) -> None:
        """首次启动时种下 4 个全局 config CSV。已存在的不动。"""
        _seed_csv(self.api_config_csv,      API_CONFIG_HEADERS,      DEFAULT_API_ROLES)
        _seed_csv(self.category_config_csv, CATEGORY_CONFIG_HEADERS, DEFAULT_CATEGORIES)
        _seed_csv(self.custom_fields_csv,   CUSTOM_FIELDS_HEADERS,   [])
        # app.csv：把当前关键路径登记一下，供前端读取
        _seed_csv(self.app_config_csv, APP_CONFIG_HEADERS, [
            {"key": "data_root",   "value": str(self.data_root)},
            {"key": "monitor_dir", "value": str(self.monitor_dir)},
        ])


def _seed_csv(path: Path, headers: list[str], default_rows: list[dict]) -> None:
    """如果文件不存在，写入 headers + default_rows；存在则一字不动。"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in default_rows:
            w.writerow({h: row.get(h, "") for h in headers})


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
    """切换数据根目录：写指针文件 + 重建 settings + 重新 ensure_dirs。"""
    global _settings
    _settings = load_settings(path)
    return _settings
