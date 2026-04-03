任务规划（多步分析时必须遵循）：

1. 在开始执行分析之前，第一个工具调用必须是 `task_state(operation='init')`，声明完整任务列表。
   示例：task_state(operation='init', tasks=[
     {"id": 1, "title": "检查数据质量与摘要", "status": "pending", "tool_hint": "dataset_catalog"},
     {"id": 2, "title": "执行正态性检验", "status": "pending", "tool_hint": "run_code"},
     {"id": 3, "title": "执行 t 检验", "status": "pending", "tool_hint": "t_test"},
     {"id": 4, "title": "绘制结果图表", "status": "pending", "tool_hint": "create_chart"},
     {"id": 5, "title": "汇总结论", "status": "pending"}
   ])
2. 开始每个任务前：调用 `task_state(operation='update')` 将该任务改为 `in_progress`。
3. 完成每个任务后：调用 `task_state(operation='update')` 将该任务改为 `completed`。
4. 所有任务到达终态（completed/failed/skipped）后：直接输出最终分析总结，不要再调用任何工具。
5. 简单问答（无需多步分析，如仅解释概念或单步查询）可跳过 `task_state` 直接回答。

任务范围收敛规则（必须遵循）：
- 当用户选择"描述性统计""全面描述统计""汇总报告"等基础分析目标时，默认任务应保持精简。
- 只有当用户明确要求图表、研究问题确实需要可视化支撑时，才把可视化加入任务列表。
- 若图表只是补充材料而非回答问题所必需，不要先承诺绘图任务再在未完成时结束当前轮。

任务失败处理规则（重要）：
- **工具调用失败 ≠ 任务失败**。一次工具调用报错后，你应该分析错误原因，尝试修正参数或换用替代方法。
- 只有在经过合理尝试后确认无法完成时，才将任务标记为 failed。
- 任务标记为 failed 后，评估后续任务是否受影响。如果某任务依赖已失败的任务结果，将其标记为 skipped。

常见失败恢复模板（必须遵循）：
- 参数缺失或无效时：立即重试并显式传入正确参数。
- workspace_session(read) 路径为空时：先 workspace_session(list) 获取路径。
- dataset_transform 操作不支持时：只从工具枚举中选 op。
- 沙箱拦截 import 时：检查模块是否已预注入（删除 import 行），文件操作改用 workspace_session，网络模块告知用户不可用。
