"""配置加载。

来源：用户首次启动时在 GUI 设置的 data_root + api_config.csv
对应 SPEC：项目二 §五.1 运行时数据目录结构
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8181
    log_level: str = "INFO"
    # 用户数据根目录：%USERPROFILE%\Documents\PaperAssistant\
    data_root: Path = Path(os.path.expanduser("~/Documents/PaperAssistant"))


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("PAPER_HOST", "127.0.0.1"),
        port=int(os.getenv("PAPER_PORT", "8181")),
        log_level=os.getenv("PAPER_LOG_LEVEL", "INFO"),
        data_root=Path(os.getenv("PAPER_DATA_ROOT", os.path.expanduser("~/Documents/PaperAssistant"))),
    )


SETTINGS = load_settings()
