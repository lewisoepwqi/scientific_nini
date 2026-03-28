/**
 * 可复用引导气泡 —— 在目标元素附近显示一次性提示。
 * 淡入动画，自动或手动关闭，暗色模式适配。
 */
import { useEffect, useState, type ReactNode } from "react";
import Button from "./ui/Button";

interface OnboardHintProps {
 /** 引导标题 */
 title: string;
 /** 引导内容 */
 children: ReactNode;
 /** 自动消失延迟（ms），0 = 不自动消失 */
 autoDismissMs?: number;
 /** 关闭回调 */
 onDismiss: () => void;
 /** 气泡位置，默认 bottom */
 anchor?: "top" | "bottom";
}

export default function OnboardHint({
 title,
 children,
 autoDismissMs = 0,
 onDismiss,
 anchor = "bottom",
}: OnboardHintProps) {
 const [visible, setVisible] = useState(true);

 useEffect(() => {
 if (autoDismissMs <= 0) return;
 const timer = window.setTimeout(() => {
 setVisible(false);
 }, autoDismissMs);
 return () => window.clearTimeout(timer);
 }, [autoDismissMs]);

 // 动画结束后真正卸载
 const handleAnimationEnd = () => {
 if (!visible) onDismiss();
 };

 if (!visible && autoDismissMs > 0) {
 // 等动画播完再调 onDismiss
 return (
 <div
 className="animate-out fade-out duration-300"
 onAnimationEnd={handleAnimationEnd}
 style={{ display: "none" }}
 />
 );
 }

 const arrowClass =
 anchor === "bottom"
 ? "absolute -top-1.5 left-4 w-3 h-3 rotate-45 border-l border-t border-[var(--border-default)] bg-[var(--bg-base)]"
 : "absolute -bottom-1.5 left-4 w-3 h-3 rotate-45 border-r border-b border-[var(--border-default)] bg-[var(--bg-base)]";

 return (
 <div
 className={`relative z-30 animate-in fade-in slide-in-from-${anchor === "bottom" ? "top-1" : "bottom-1"} duration-300`}
 role="status"
 >
 <div className="absolute left-0 right-0 top-0 h-1 -translate-y-full" />
 <div className="relative rounded-xl border border-[var(--border-default)] bg-[var(--bg-base)] px-4 py-3 shadow-lg dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)]">
 <div className={arrowClass} />
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0">
 <div className="text-sm font-semibold text-[var(--text-primary)]">
 {title}
 </div>
 <div className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
 {children}
 </div>
 </div>
 <Button
 type="button"
 variant="ghost"
 size="sm"
 onClick={() => {
 setVisible(false);
 onDismiss();
 }}
 >
 知道了
 </Button>
 </div>
 </div>
 </div>
 );
}
