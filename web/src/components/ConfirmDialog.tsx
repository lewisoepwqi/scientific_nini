/**
 * ConfirmDialog —— 全局确认对话框渲染器。
 *
 * 在 App 顶层挂载一次即可，通过 useConfirm() hook 触发。
 * 底层使用 ui/ConfirmDialog 基础组件，遵循 .impeccable.md 规范。
 */
import { useCallback } from "react";
import { useConfirmStore } from "../store/confirm-store";
import { ConfirmDialog as ConfirmDialogUI } from "./ui";

export default function ConfirmDialog() {
 const { open, options, resolve } = useConfirmStore();

 const handleCancel = useCallback(() => {
 resolve(false);
 }, [resolve]);

 const handleConfirm = useCallback(() => {
 resolve(true);
 }, [resolve]);

 if (!options) return null;

 return (
 <ConfirmDialogUI
 isOpen={open}
 onCancel={handleCancel}
 onConfirm={handleConfirm}
 title={options.title}
 description={options.message}
 confirmLabel={options.confirmText ?? "确认"}
 cancelLabel={options.cancelText ?? "取消"}
 destructive={options.destructive}
 />
 );
}
