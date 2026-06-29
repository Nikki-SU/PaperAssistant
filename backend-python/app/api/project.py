"""项目管理 API：创建/切换/列表/阶段切换。

对应 SPEC：项目二 §六. UI/UX 布局（左栏 - 项目列表 + 阶段导航）
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/list")
def list_projects() -> dict:
    """列出所有项目（读取 data_root/projects/ 下所有目录）。"""
    # TODO
    return {"projects": []}


@router.post("/create")
def create_project(name: str) -> dict:
    """创建新项目。"""
    # TODO: mkdir data_root/projects/{name}/{memories,paper/images,citations}
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/{name}/stage")
def get_stage(name: str) -> dict:
    """获取项目当前阶段：选题/综述/撰写/引用/排版。"""
    # TODO
    raise HTTPException(status_code=501, detail="Not implemented yet")
