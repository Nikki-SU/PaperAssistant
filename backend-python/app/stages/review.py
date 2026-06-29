"""stage: review

TODO: 实现 SPEC §二 中关于「review」阶段的具体业务。
当前仅提供占位入口，便于 main.py 引用与阶段切换。
"""
from __future__ import annotations

STAGE_NAME = "review"


def describe() -> dict:
    return {
        "stage": STAGE_NAME,
        "status": "skeleton",
        "todo": True,
    }
