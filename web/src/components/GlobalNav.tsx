/**
 * GlobalNav —— 全局导航栏，支持折叠/展开
 *
 * 折叠态宽度 52px，展开态宽度 176px
 * 所有颜色使用 CSS token
 */
import { useCallback, useState, useId } from "react";
import {
	MessageSquare,
	Library,
	Zap,
	User,
	Sun,
	Moon,
	HelpCircle,
	Settings,
	Sparkles,
	FileText,
	Coins,
	Wrench,
} from "lucide-react";
import { getResolvedTheme, type ThemeMode } from "../theme";

/** 导航分组 */
export const NAV_GROUPS = [
	{
		key: "core",
		items: [
			{ icon: MessageSquare, label: "会话", id: "chat" },
			{ icon: Library, label: "知识库", id: "knowledge" },
			{ icon: Zap, label: "技能", id: "skills" },
			{ icon: User, label: "研究画像", id: "profile" },
		],
	},
	{
		key: "features",
		items: [
			{ icon: Sparkles, label: "分析能力", id: "capabilities" },
			{ icon: FileText, label: "文章初稿", id: "report" },
			{ icon: Coins, label: "成本统计", id: "cost" },
			{ icon: Wrench, label: "工具清单", id: "tools" },
		],
	},
] as const;

export interface GlobalNavProps {
	themeMode: ThemeMode;
	onToggleTheme: () => void;
	onNavigate: (id: string) => void;
	activeNav: string;
}

/**
 * NiniLogo — 渐变 teal 节点风格
 *
 * N 字母线条 + 4 个白色节点圆点（暗示神经网络/数据图）
 * 渐变: #1FD8C3 → #0A8B7E
 */
export function NiniLogo({ size = 32 }: { size?: number }) {
	const uid = useId();
	const id = `nini-grad-${uid}`;
	return (
		<svg width={size} height={size} viewBox="0 0 32 32" fill="none" className="flex-shrink-0">
			<defs>
				<linearGradient id={id} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
					<stop offset="0%" stopColor="#1FD8C3" />
					<stop offset="100%" stopColor="#0A8B7E" />
				</linearGradient>
			</defs>
			{/* 容器 */}
			<rect width="32" height="32" rx="9" fill={`url(#${id})`} />
			{/* N — 左竖线 */}
			<line x1="8.5" y1="8.5" x2="8.5" y2="23.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
			{/* N — 对角线 */}
			<line x1="8.5" y1="8.5" x2="23.5" y2="23.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
			{/* N — 右竖线 */}
			<line x1="23.5" y1="8.5" x2="23.5" y2="23.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
			{/* 节点圆点 */}
			<circle cx="8.5" cy="8.5" r="2.2" fill="white" fillOpacity="0.95" />
			<circle cx="23.5" cy="8.5" r="2.2" fill="white" fillOpacity="0.95" />
			<circle cx="8.5" cy="23.5" r="2.2" fill="white" fillOpacity="0.95" />
			<circle cx="23.5" cy="23.5" r="2.2" fill="white" fillOpacity="0.95" />
		</svg>
	);
}

/** 导航按钮统一样式 */
function NavButton({
	icon: Icon,
	label,
	isActive,
	expanded,
	onClick,
}: {
	icon: React.ComponentType<React.SVGProps<SVGSVGElement> & { size?: number | string }>;
	label: string;
	isActive: boolean;
	expanded: boolean;
	onClick: () => void;
}) {
	return (
		<button
			onClick={onClick}
			className={[
				"group relative flex items-center gap-2.5 h-9 px-2 rounded-md transition-colors w-full",
				expanded ? "justify-start" : "justify-center",
				isActive
					? "bg-[var(--accent-subtle)] text-[var(--accent)]"
					: "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]",
			].join(" ")}
			title={label}
		>
			{isActive && (
				<span
					className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-r"
					style={{ background: "var(--accent)" }}
				/>
			)}
			<Icon size={16} className="flex-shrink-0" />
			{expanded && (
				<span className="text-sm whitespace-nowrap">{label}</span>
			)}
		</button>
	);
}

export default function GlobalNav({
	themeMode,
	onToggleTheme,
	onNavigate,
	activeNav,
}: GlobalNavProps) {
	const [expanded, setExpanded] = useState(false);
	const toggleExpand = useCallback(() => setExpanded((v) => !v), []);

	return (
		<nav
			aria-label="全局导航"
			className="flex-shrink-0 hidden md:flex flex-col h-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden"
			style={{
				width: expanded ? 176 : 52,
				transition: "width 200ms ease",
			}}
		>
			{/* Logo — 点击切换展开/收起 */}
			<div className="flex items-center gap-2.5 px-2 h-12 border-b border-[var(--border-subtle)] shrink-0 mb-1">
				<button
					onClick={toggleExpand}
					className="flex-shrink-0 flex items-center justify-center w-8 h-8 hover:opacity-90 transition-opacity ml-0.5"
					aria-label={expanded ? "折叠导航" : "展开导航"}
				>
					<NiniLogo size={expanded ? 24 : 24} />
				</button>
				{expanded && (
					<div className="flex flex-col justify-center">
						<span className="text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap leading-none">
							Nini
						</span>
						<span className="text-[10px] text-[var(--text-muted)] whitespace-nowrap leading-none mt-1">
							AI Assistant
						</span>
					</div>
				)}
			</div>

			{/* 主导航分组 */}
			<div className="flex flex-col gap-0.5 px-2 mt-1">
				{NAV_GROUPS.map((group, gi) => (
					<div key={group.key}>
						{gi > 0 && (
							<div
								className="h-px mx-1 my-1"
								style={{ background: "var(--border-subtle)" }}
							/>
						)}
						{group.items.map((item) => (
							<NavButton
								key={item.id}
								icon={item.icon}
								label={item.label}
								isActive={activeNav === item.id}
								expanded={expanded}
								onClick={() => onNavigate(item.id)}
							/>
						))}
					</div>
				))}
			</div>

			{/* 底部工具栏 */}
			<div className="mt-auto flex flex-col gap-0.5 px-2 pb-2">
				{/* 分隔线 */}
				<div
					className="h-px mx-1 mb-1"
					style={{ background: "var(--border-subtle)" }}
				/>

				{/* 主题切换 */}
				<NavButton
					icon={getResolvedTheme() === "dark" ? Moon : Sun}
					label={`主题：${themeMode === "system" ? "跟随系统" : themeMode === "dark" ? "深色" : "浅色"}`}
					isActive={false}
					expanded={expanded}
					onClick={onToggleTheme}
				/>

				{/* 帮助 */}
				<NavButton
					icon={HelpCircle}
					label="帮助"
					isActive={false}
					expanded={expanded}
					onClick={() => {}}
				/>

				{/* 设置 */}
				<NavButton
					icon={Settings}
					label="设置"
					isActive={activeNav === "settings"}
					expanded={expanded}
					onClick={() => onNavigate("settings")}
				/>
			</div>
		</nav>
	);
}
