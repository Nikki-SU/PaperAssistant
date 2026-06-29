"""历史命名模块：转发到 review.py。"""
from __future__ import annotations

from . import review

STAGE_NAME = review.STAGE_NAME
STAGE_LABEL = review.STAGE_LABEL
describe = review.describe
on_enter = review.on_enter
on_exit = review.on_exit
