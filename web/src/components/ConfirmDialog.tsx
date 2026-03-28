/**
 * ConfirmDialog —— 全局确认对话框渲染器。
 *
 * 在 App 顶层挂载一次即可，通过 useConfirm() hook 触发。
 * 继承 BaseModal 的 ARIA、焦点捕获和 Escape 关闭能力。
 */
import { useCallback, useEffect, useRef } from "react";
import BaseModal from "./BaseModal";
import { useConfirmStore } from "../store/confirm-store";
import { AlertTriangle } from "lucide-react";

export default function ConfirmDialog() {
  const { open, options, resolve } = useConfirmStore();
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // 打开时自动聚焦确认按钮
  useEffect(() => {
    if (open) {
      // 延迟一帧确保 DOM 已渲染
      requestAnimationFrame(() => {
        confirmButtonRef.current?.focus();
      });
    }
  }, [open]);

  const handleClose = useCallback(
    (result: boolean) => {
      resolve(result);
    },
    [resolve],
  );

  if (!open || !options) return null;

  const {
    title,
    message,
    confirmText = "确认",
    cancelText = "取消",
    destructive = false,
  } = options;

  return (
    <BaseModal
      open={open}
      onClose={() => handleClose(false)}
      title={title}
      maxWidthClass="max-w-sm"
    >
      <div className="p-5">
        {/* 标题区 */}
        <div className="flex items-start gap-3">
          {destructive && (
            <div className="flex-shrink-0 mt-0.5">
              <AlertTriangle
                size={20}
                className="text-red-500"
                aria-hidden="true"
              />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {title}
            </h3>
            {message && (
              <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                {message}
              </p>
            )}
          </div>
        </div>

        {/* 按钮区 */}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => handleClose(false)}
            className="px-3.5 py-1.5 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            {cancelText}
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            onClick={() => handleClose(true)}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium text-white transition-colors ${
              destructive
                ? "bg-red-600 hover:bg-red-700"
                : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </BaseModal>
  );
}
