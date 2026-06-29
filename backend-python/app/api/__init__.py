"""HTTP API 路由。

- /api/project       项目 CRUD + 阶段
- /api/literature    文献上传 / 卡片 / 检索
- /api/citation      引用选择
- /api/typesetting   排版导出
- /api/health        健康检查
"""
from . import project, literature, citation, typesetting, health

__all__ = ["project", "literature", "citation", "typesetting", "health"]
