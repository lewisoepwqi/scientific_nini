/**
 * Markdown 懒加载包装组件 —— 将 react-markdown 链路延后到真正需要渲染时再加载。
 */
import { Suspense, lazy } from "react";

const MarkdownContent = lazy(() => import("./MarkdownContent"));

interface Props {
 content: string;
 className?: string;
}

export function contentNeedsMarkdownRenderer(content: string): boolean {
 if (!content) return false;
 if (content.includes("```")) return true;
 if (content.includes("|")) return true;
 if (/\[[^\]]+\]\([^)]+\)/.test(content)) return true;
 if (/!\[[^\]]*\]\([^)]+\)/.test(content)) return true;
 if (/^\s{0,3}(#{1,6}|\* |- |\d+\. |>)/m.test(content)) return true;
 if (/(^|\s)(\*\*|__|~~|`)[^`]+(\*\*|__|~~|`)/.test(content)) return true;
 if (/<[a-z][\s\S]*>/i.test(content)) return true;
 if (/\n\s*\n/.test(content)) return true;
 return false;
}

export function preloadMarkdownRenderer() {
 return import("./MarkdownContent");
}

function PlainTextContent({ content, className }: Props) {
 return (
 <div className={className ? className : "whitespace-pre-wrap break-words"}>
 {content}
 </div>
 );
}

function MarkdownFallback() {
 return (
 <div className="space-y-2 py-1">
 <div className="skeleton-line h-3 w-5/6 rounded-full animate-pulse" />
 <div className="skeleton-line-soft h-3 w-2/3 rounded-full animate-pulse" />
 <div className="skeleton-line-soft h-3 w-3/4 rounded-full animate-pulse" />
 </div>
 );
}

export default function LazyMarkdownContent({ content, className }: Props) {
 if (!contentNeedsMarkdownRenderer(content)) {
 return <PlainTextContent content={content} className={className} />;
 }

 return (
 <Suspense fallback={<MarkdownFallback />}>
 <MarkdownContent content={content} className={className} />
 </Suspense>
 );
}
