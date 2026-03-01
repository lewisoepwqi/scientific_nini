"""API 路由模块。

重构后的路由结构：
- session_routes: 会话管理 (/sessions)
- workspace_routes: 工作区和数据集 (/workspace, /datasets, /upload)
- skill_routes: 技能和工具 (/skills, /capabilities, /tools)
- profile_routes: 用户画像和报告 (/research-profile, /report)
- models_routes: 模型配置 (/models)
- intent_routes: 意图分析 (/intent)
- routes: 保留原有路由并 include 新路由
"""

from .routes import router

__all__ = ["router"]
