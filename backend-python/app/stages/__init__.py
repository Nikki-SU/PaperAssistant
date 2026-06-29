"""五阶段业务逻辑（SPEC §二）。

- topic         选题
- review        文献综述
- writing       正文撰写（社科 4 节 / 理科 4 节，由用户选择视角）
- citation      引用
- typesetting   排版

当前为骨架：每个阶段保留入口函数 + TODO 注释，便于后续填充。
"""
from . import topic, review, writing, citation, typesetting

__all__ = ["topic", "review", "writing", "citation", "typesetting"]
