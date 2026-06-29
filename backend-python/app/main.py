"""PaperAssistant backend FastAPI 入口。

- 监听 127.0.0.1:8181
- 启动时初始化 debug-assistant SDK（连不上时静默降级）
- 所有路由前缀 /api
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import citation, health, literature, project, settings as settings_api, typesetting
from .config import get_settings

logger = logging.getLogger("paperassistant")


def _init_debug_assistant() -> None:
    """尝试加载 debug-assistant Python SDK。

    SDK 默认存在两条路径：
    1. pip install debug-assistant 后通过 ``debug_assistant`` 包导入；
    2. 如果开发态没装包，从环境变量 DA_SDK_PATH 加载源码。
    任何失败都静默降级，不能阻塞 PaperAssistant 启动。
    """
    settings = get_settings()
    if not settings.debug_assistant_enabled:
        logger.info("debug-assistant: 已通过配置禁用")
        return

    sdk_path = os.environ.get("DA_SDK_PATH")
    if sdk_path and Path(sdk_path).exists():
        sys.path.insert(0, sdk_path)

    try:
        from debug_assistant import Debugger, set_default  # type: ignore
    except Exception as e:  # noqa: BLE001
        logger.warning("debug-assistant SDK 不可用，已降级：%s", e)
        return

    try:
        dbg = Debugger(
            host=settings.debug_assistant_host,
            port=settings.debug_assistant_port,
            project="PaperAssistant",
        )
        set_default(dbg)
        logger.info(
            "debug-assistant 已接入：http://%s:%s",
            settings.debug_assistant_host,
            settings.debug_assistant_port,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("debug-assistant 初始化失败，已降级：%s", e)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    settings.ensure_dirs()

    app = FastAPI(
        title="PaperAssistant Backend",
        version="0.1.0",
        description="本地优先的学术写作辅助后端（SPEC v0.1）",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1421", "http://127.0.0.1:1421",
                       "tauri://localhost", "https://tauri.localhost"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(project.router)
    app.include_router(literature.router)
    app.include_router(citation.router)
    app.include_router(typesetting.router)
    app.include_router(settings_api.router)

    @app.on_event("startup")
    def _on_startup() -> None:
        _init_debug_assistant()
        logger.info("PaperAssistant data_root = %s", settings.data_root)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
