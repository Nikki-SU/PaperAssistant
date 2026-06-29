"""服务层：对四个外部 AI 接口位 + MinerU 的统一封装。"""
from .mineru_client import MineruClient, MineruResult
from .ai_orchestrator import (
    AIOrchestrator,
    AIRole,
    AIResult,
    AIRoleConfig,
    VerifyResult,
    AuditRejectedError,
    assert_verified_or_raise,
    get_orchestrator,
    reload_orchestrator,
    load_role_config,
)
from .memory_writer import (
    append_assistant_memory,
    append_secretary_memory,
)
from .pdf_splitter import (
    MAX_PAGES_PER_CHUNK,
    PdfChunk,
    SplitResult,
    count_pages,
    merge_markdowns,
    split_pdf,
)
from .file_watcher import (
    FileWatcher,
    ProcessRecord,
    get_watcher,
    start_watcher,
    stop_watcher,
)

__all__ = [
    "MineruClient",
    "MineruResult",
    "MAX_PAGES_PER_CHUNK",
    "PdfChunk",
    "SplitResult",
    "count_pages",
    "merge_markdowns",
    "split_pdf",
    "FileWatcher",
    "ProcessRecord",
    "get_watcher",
    "start_watcher",
    "stop_watcher",
    "AIOrchestrator",
    "AIRole",
    "AIResult",
    "AIRoleConfig",
    "VerifyResult",
    "AuditRejectedError",
    "assert_verified_or_raise",
    "get_orchestrator",
    "reload_orchestrator",
    "load_role_config",
    "append_assistant_memory",
    "append_secretary_memory",
]
