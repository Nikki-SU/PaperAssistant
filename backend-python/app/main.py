"""PaperAssistant backend FastAPI 入口。

- 监听 127.0.0.1:8181
- 启动时初始化 debug-assistant SDK（连不上时静默降级）
- 所有路由前缀 /api
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    ai as ai_api,
    citation,
    file_watcher as file_watcher_api,
    health,
    knowledge as knowledge_api,
    literature,
    project,
    search_sources as search_sources_api,
    selections as selections_api,
    settings as settings_api,
    stages_auto as stages_auto_api,
    temp_knowledge as temp_knowledge_api,
    typesetting,
)
from .config import get_settings
from .lib import debug_assistant as da
from .services import start_watcher, stop_watcher

logger = logging.getLogger("paperassistant")


def _init_debug_assistant() -> None:
    """初始化内联 debug-assistant 客户端，连不上 server 时静默降级。"""
    settings = get_settings()
    da.init(
        project="PaperAssistant",
        module="backend",
        host=settings.debug_assistant_host,
        port=settings.debug_assistant_port,
        enabled=settings.debug_assistant_enabled,
    )
    if settings.debug_assistant_enabled:
        hc = da.health()
        if hc is None:
            logger.warning(
                "debug-assistant server 未在 %s:%s 响应，运行时会静默降级",
                settings.debug_assistant_host,
                settings.debug_assistant_port,
            )
        else:
            logger.info("debug-assistant 已就绪：%s", hc)
    else:
        logger.info("debug-assistant: 已通过配置禁用")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    settings.ensure_dirs()

    app = FastAPI(
        title="PaperAssistant Backend",
        version="0.4.0",
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
    app.include_router(ai_api.router)
    app.include_router(knowledge_api.router)
    app.include_router(temp_knowledge_api.router)
    app.include_router(file_watcher_api.router)
    app.include_router(search_sources_api.router)
    app.include_router(selections_api.router)
    app.include_router(stages_auto_api.router)

    @app.on_event("startup")
    def _on_startup() -> None:
        _init_debug_assistant()
        logger.info("PaperAssistant data_root = %s", settings.data_root)
        # SPEC §九：启动文件监控
        try:
            start_watcher()
            logger.info("file_watcher 已启动：%s", settings.monitor_dir)
        except Exception:  # noqa: BLE001
            logger.exception("file_watcher 启动失败（不阻塞主流程）")

    @app.on_event("shutdown")
    def _on_shutdown() -> None:
        try:
            stop_watcher()
        except Exception:  # noqa: BLE001
            logger.exception("file_watcher 停止失败")

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
