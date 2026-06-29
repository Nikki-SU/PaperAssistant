"""存储层：CSV + Markdown。

严格铁律：所有落盘只能是 Markdown 或 CSV。JSON 只用于 HTTP 在途传输。
"""
from .csv_io import (
    ensure_csv,
    read_rows,
    append_row,
    upsert_row,
    delete_row,
    filter_rows,
)
from .markdown_io import (
    read_text,
    write_text,
    append_text,
    read_frontmatter,
    render_frontmatter,
    render_literature_card_md,
    now_iso,
    LIT_CSV_HEADERS,
)

__all__ = [
    "ensure_csv",
    "read_rows",
    "append_row",
    "upsert_row",
    "delete_row",
    "filter_rows",
    "read_text",
    "write_text",
    "append_text",
    "read_frontmatter",
    "render_frontmatter",
    "render_literature_card_md",
    "now_iso",
    "LIT_CSV_HEADERS",
]
