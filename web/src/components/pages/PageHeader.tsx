/**
 * PageHeader —— 独立页面的通用顶栏组件
 *
 * 左侧：返回按钮（ArrowLeft）+ 页面标题
 * 右侧：操作区域（actions 插槽）
 * 支持 ESC 键返回
 */
import { useEffect, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import Button from "../ui/Button";

interface PageHeaderProps {
  title: string;
  onBack: () => void;
  actions?: ReactNode;
  backButtonClassName?: string;
  actionsClassName?: string;
}

export default function PageHeader({
  title,
  onBack,
  actions,
  backButtonClassName,
  actionsClassName,
}: PageHeaderProps) {
  // ESC 键返回
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onBack();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onBack]);

  return (
    <header className="h-12 border-b border-[var(--border-subtle)] flex items-center px-4 bg-[var(--bg-base)] flex-shrink-0">
      {/* 左侧：返回按钮 + 标题 */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <Button
          variant="ghost"
          size="icon-sm"
          className={backButtonClassName}
          onClick={onBack}
          aria-label="返回"
          title="返回"
        >
          <ArrowLeft size={16} />
        </Button>
        <h1 className="text-sm font-semibold text-[var(--text-primary)] truncate m-0">
          {title}
        </h1>
      </div>

      {/* 右侧：操作区域 */}
      {actions && (
        <div className={`flex items-center gap-1.5 flex-shrink-0 ${actionsClassName ?? ""}`}>
          {actions}
        </div>
      )}
    </header>
  );
}
