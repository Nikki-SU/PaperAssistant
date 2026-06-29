"""文献管理 API：上传、PDF 转换、卡片、勾选。

对应 SPEC：项目二 §七.2 文献综述 / §九. MinerU 处理规则
"""
from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    """上传 PDF → 触发 MinerU 转换 → 落盘 library/fulltext/{doi}.md。"""
    # TODO: 1) 暂存到 temp/monitor/；2) 调 services.mineru_client；3) 生成文献卡片
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/library")
def list_library() -> dict:
    """列出文献库所有卡片（读 library/cards/cards.csv）。"""
    # TODO
    return {"cards": []}


@router.post("/{project}/select")
def select_for_citation(project: str, doi_list: list[str]) -> dict:
    """用户勾选某阶段实际引用的文献，写入 projects/{project}/citations/selected.csv。"""
    # TODO
    raise HTTPException(status_code=501, detail="Not implemented yet")
