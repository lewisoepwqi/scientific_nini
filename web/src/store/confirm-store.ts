/**
 * 确认对话框全局状态 —— 替代 window.confirm()，
 * 提供与应用设计系统一致的 UI 体验。
 */
import { create } from "zustand";

export interface ConfirmOptions {
  /** 标题（必填） */
  title: string;
  /** 正文说明 */
  message?: string;
  /** 确认按钮文字，默认"确认" */
  confirmText?: string;
  /** 取消按钮文字，默认"取消" */
  cancelText?: string;
  /** 是否为破坏性操作（红色确认按钮） */
  destructive?: boolean;
}

interface ConfirmState {
  open: boolean;
  options: ConfirmOptions | null;
  resolver: ((result: boolean) => void) | null;
}

interface ConfirmActions {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  resolve: (result: boolean) => void;
}

/**
 * useConfirm() hook —— 返回一个 async confirm(options) 函数。
 * 用法：
 *   const confirm = useConfirm();
 *   const ok = await confirm({ title: "删除文件", destructive: true });
 *   if (ok) { ... }
 */
export function useConfirm() {
  return useConfirmStore.getState().confirm;
}

export const useConfirmStore = create<ConfirmState & ConfirmActions>((set, get) => ({
  open: false,
  options: null,
  resolver: null,

  confirm: (options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      set({ open: true, options, resolver: resolve });
    });
  },

  resolve: (result: boolean) => {
    const { resolver } = get();
    resolver?.(result);
    set({ open: false, options: null, resolver: null });
  },
}));
