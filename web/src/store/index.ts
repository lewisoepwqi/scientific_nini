/**
 * Store 模块
 *
 * Nini 2.0 架构迭代 - Phase 3.2 部分完成
 * - ✅ types.ts: 所有类型定义已提取
 * - ✅ utils.ts: 工具函数已提取
 * - ✅ normalizers.ts: 数据规范化函数（已存在）
 * - ⏳ 其他 slices: 后续迭代完成（涉及组件 import 同步调整）
 */

// 类型定义
export * from "./types";

// 规范化函数
export * from "./normalizers";

// 工具函数（utils 内部依赖 normalizers，但不 re-export 以避免重复）
export * from "./utils";

// 计划状态机
export * from "./plan-state-machine";

// API 动作
export * from "./api-actions";

// WebSocket 事件处理器
export * from "./event-handler";

// ⚠️ 原 store.ts 仍从根目录导出 useStore 以保持向后兼容
// 后续迭代将完整迁移到 slices 模式
// export { useStore } from "./store"; // TODO: 后续迭代启用
