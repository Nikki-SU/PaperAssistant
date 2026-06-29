"""PaperAssistant FastAPI 入口。

由 Tauri sidecar 启动并管理生命周期。
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import SETTINGS
from .api import project, literature, citation, typesetting

app = FastAPI(
    title="PaperAssistant",
    version="0.1.0",
    description="Local-first academic writing assistant backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router, prefix="/api/project", tags=["project"])
app.include_router(literature.router, prefix="/api/literature", tags=["literature"])
app.include_router(citation.router, prefix="/api/citation", tags=["citation"])
app.include_router(typesetting.router, prefix="/api/typesetting", tags=["typesetting"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


def run() -> None:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=SETTINGS.host,
        port=SETTINGS.port,
        log_level=SETTINGS.log_level.lower(),
    )


if __name__ == "__main__":
    run()
