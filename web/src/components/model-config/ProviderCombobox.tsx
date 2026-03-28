/**
 * 提供商搜索下拉框 —— 与模型下拉保持一致的输入与面板样式。
 */
import { useEffect, useState, useRef } from "react";
import { Search, ChevronDown } from "lucide-react";
import type { ProviderOption } from "./types";
import Button from "../ui/Button";

interface ProviderComboboxProps {
 value: string;
 onChange: (val: string) => void;
 options: ProviderOption[];
 placeholder?: string;
 disabled?: boolean;
}

export default function ProviderCombobox({
 value,
 onChange,
 options,
 placeholder = "搜索提供商...",
 disabled = false,
}: ProviderComboboxProps) {
 const [query, setQuery] = useState("");
 const [dropdownOpen, setDropdownOpen] = useState(false);
 const [activeIndex, setActiveIndex] = useState(0);
 const wrapperRef = useRef<HTMLDivElement>(null);
 const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

 const selected = value
 ? options.find((item) => item.id === value)
 : undefined;
 const selectedLabel = selected?.name || "";

 useEffect(() => {
 if (!dropdownOpen) {
 setQuery(selectedLabel);
 }
 }, [dropdownOpen, selectedLabel]);

 useEffect(() => {
 function handleClick(e: MouseEvent) {
 if (
 wrapperRef.current &&
 !wrapperRef.current.contains(e.target as Node)
 ) {
 setDropdownOpen(false);
 }
 }
 if (dropdownOpen) {
 document.addEventListener("mousedown", handleClick);
 return () => document.removeEventListener("mousedown", handleClick);
 }
 }, [dropdownOpen]);

 const queryText = query.trim().toLowerCase();
 const filtered = queryText
 ? options.filter(
 (item) =>
 item.name.toLowerCase().includes(queryText) ||
 item.id.toLowerCase().includes(queryText),
 )
 : options;
 const renderedItems = [
 { id: "", label: "自动（按优先级）", isAuto: true },
 ...filtered.map((item) => ({ id: item.id, label: item.name, isAuto: false })),
 ];

 useEffect(() => {
 if (!dropdownOpen) return;
 if (queryText) {
 const matchedIndex = filtered.findIndex((item) => item.id === value);
 setActiveIndex(filtered.length > 0 ? Math.max(matchedIndex + 1, 1) : 0);
 return;
 }
 const selectedIndex = filtered.findIndex((item) => item.id === value);
 setActiveIndex(selectedIndex >= 0 ? selectedIndex + 1 : 0);
 }, [dropdownOpen, filtered, queryText, value]);

 useEffect(() => {
 if (!dropdownOpen) return;
 optionRefs.current[activeIndex]?.scrollIntoView({ block: "nearest" });
 }, [activeIndex, dropdownOpen]);

 const pickProvider = (providerId: string) => {
 const picked = options.find((item) => item.id === providerId);
 setQuery(picked?.name || "");
 onChange(providerId);
 setDropdownOpen(false);
 };

 return (
 <div className="relative" ref={wrapperRef}>
 <div className="relative">
 <Search
 size={12}
 className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
 />
 <input
 type="text"
 value={query}
 onChange={(e) => {
 setQuery(e.target.value);
 if (!dropdownOpen) setDropdownOpen(true);
 }}
 onFocus={() => !disabled && setDropdownOpen(true)}
 onKeyDown={(e) => {
 if (e.key === "ArrowDown") {
 e.preventDefault();
 if (!dropdownOpen) {
 setDropdownOpen(true);
 setActiveIndex(queryText && filtered.length > 0 ? 1 : 0);
 return;
 }
 if (renderedItems.length > 0) {
 setActiveIndex((prev) => Math.min(prev + 1, renderedItems.length - 1));
 }
 return;
 }
 if (e.key === "ArrowUp") {
 e.preventDefault();
 if (!dropdownOpen) {
 setDropdownOpen(true);
 setActiveIndex(Math.max(renderedItems.length - 1, 0));
 return;
 }
 if (renderedItems.length > 0) {
 setActiveIndex((prev) => Math.max(prev - 1, 0));
 }
 return;
 }
 if (e.key === "Enter") {
 e.preventDefault();
 const activeItem = renderedItems[activeIndex];
 if (!queryText && activeItem?.isAuto) {
 pickProvider("");
 return;
 }
 if (activeItem && !activeItem.isAuto) {
 pickProvider(activeItem.id);
 }
 return;
 }
 if (e.key === "Escape") {
 setDropdownOpen(false);
 }
 }}
 placeholder={placeholder}
 disabled={disabled}
 className="w-full h-8 pl-7 pr-7 text-xs border rounded-lg dark:border-[var(--border-default)] dark:bg-[var(--bg-elevated)] dark:text-[var(--text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] disabled:opacity-60"
 />
 <Button
 variant="ghost"
 size="icon-sm"
 type="button"
 onClick={() => !disabled && setDropdownOpen(!dropdownOpen)}
 className="absolute right-1.5 top-1/2 -translate-y-1/2"
 disabled={disabled}
 >
 <ChevronDown
 size={12}
 className={`transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
 />
 </Button>
 </div>

 {dropdownOpen && (
 <div className="absolute z-10 w-full mt-1 bg-[var(--bg-base)] border border-[var(--border-default)] rounded-lg shadow-lg max-h-48 overflow-y-auto">
 <Button
 ref={(node) => {
 optionRefs.current[0] = node;
 }}
 variant="ghost"
 type="button"
 onClick={() => pickProvider("")}
 onMouseEnter={() => setActiveIndex(0)}
 className={`w-full text-left px-3 py-1.5 text-sm ${
 activeIndex === 0
 ? "bg-[var(--accent-subtle)] text-[var(--accent)] font-medium"
 : !value
 ? "bg-[var(--accent-subtle)]/70 text-[var(--accent)] font-medium"
 : ""
 }`}
 >
 自动（按优先级）
 </Button>
 {filtered.length === 0 ? (
 <div className="px-3 py-3 text-xs text-[var(--text-muted)]">无匹配提供商</div>
 ) : (
 filtered.map((item) => (
 <Button
 key={item.id}
 ref={(node) => {
 optionRefs.current[renderedItems.findIndex((entry) => entry.id === item.id)] = node;
 }}
 variant="ghost"
 type="button"
 onClick={() => pickProvider(item.id)}
 onMouseEnter={() => {
 const nextIndex = renderedItems.findIndex((entry) => entry.id === item.id);
 setActiveIndex(nextIndex >= 0 ? nextIndex : 0);
 }}
 className={`w-full text-left px-3 py-1.5 text-sm ${
 renderedItems[activeIndex]?.id === item.id
 ? "bg-[var(--accent-subtle)] text-[var(--accent)] font-medium"
 : item.id === value
 ? "bg-[var(--accent-subtle)]/70 text-[var(--accent)] font-medium"
 : ""
 }`}
 >
 {item.name}
 </Button>
 ))
 )}
 </div>
 )}
 </div>
 );
}
