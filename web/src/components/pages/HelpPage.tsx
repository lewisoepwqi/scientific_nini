/**
 * 帮助独立页面 —— 统一展示分析能力与工具清单。
 */
import PageHeader from "./PageHeader";
import { HelpContent } from "../HelpPanel";

interface Props {
  onBack: () => void;
}

export default function HelpPage({ onBack }: Props) {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="帮助与说明" onBack={onBack} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <HelpContent />
      </div>
    </div>
  );
}
