import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { ColumnType, ColumnInfo, SupportedFileType } from '../types';

/**
 * 合并 Tailwind 类名
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 格式化数字
 */
export function formatNumber(num: number, decimals: number = 2): string {
  if (isNaN(num)) return '-';
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * 格式化日期
 */
export function formatDate(date: Date | string, format: 'short' | 'long' = 'short'): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  if (format === 'short') {
    return d.toLocaleDateString('zh-CN');
  }
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * 生成唯一 ID
 */
export function generateId(): string {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

/**
 * 获取文件扩展名
 */
export function getFileExtension(filename: string): string {
  return filename.slice(((filename.lastIndexOf('.') - 1) >>> 0) + 2).toLowerCase();
}

/**
 * 检查是否为支持的文件类型
 */
export function isSupportedFileType(filename: string): boolean {
  const ext = getFileExtension(filename) as SupportedFileType;
  return ['csv', 'xlsx', 'xls', 'txt', 'tsv'].includes(ext);
}

/**
 * 获取文件类型
 */
export function getFileType(filename: string): SupportedFileType | null {
  const ext = getFileExtension(filename) as SupportedFileType;
  if (['csv', 'xlsx', 'xls', 'txt', 'tsv'].includes(ext)) {
    return ext;
  }
  return null;
}

/**
 * 推断列类型
 */
export function inferColumnType(values: unknown[]): ColumnType {
  if (values.length === 0) return 'text';

  // 过滤掉 null 和 undefined
  const nonNullValues = values.filter((v) => v !== null && v !== undefined && v !== '');
  if (nonNullValues.length === 0) return 'text';

  // 检查是否为日期
  const datePattern = /^\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}/;
  const dateCount = nonNullValues.filter((v) => {
    if (typeof v === 'string') {
      return datePattern.test(v) || !isNaN(Date.parse(v));
    }
    return false;
  }).length;
  if (dateCount / nonNullValues.length > 0.8) return 'datetime';

  // 检查是否为数值
  const numericCount = nonNullValues.filter((v) => {
    if (typeof v === 'number') return true;
    if (typeof v === 'string') {
      const num = parseFloat(v.replace(/,/g, ''));
      return !isNaN(num) && isFinite(num);
    }
    return false;
  }).length;
  if (numericCount / nonNullValues.length > 0.8) return 'numeric';

  // 检查是否为类别（唯一值较少）
  const uniqueValues = new Set(nonNullValues.map((v) => String(v)));
  if (uniqueValues.size <= Math.min(20, nonNullValues.length * 0.1)) {
    return 'categorical';
  }

  return 'text';
}

/**
 * 计算列统计信息
 */
export function calculateColumnStats(values: unknown[], type: ColumnType): Partial<ColumnInfo> {
  const nonNullValues = values.filter((v) => v !== null && v !== undefined && v !== '');
  const uniqueValues = new Set(nonNullValues.map((v) => String(v)));

  const stats: Partial<ColumnInfo> = {
    uniqueCount: uniqueValues.size,
    sample: nonNullValues.slice(0, 5),
  };

  if (type === 'numeric') {
    const numbers = nonNullValues
      .map((v) => {
        if (typeof v === 'number') return v;
        if (typeof v === 'string') {
          const num = parseFloat(v.replace(/,/g, ''));
          return isNaN(num) ? null : num;
        }
        return null;
      })
      .filter((v): v is number => v !== null);

    if (numbers.length > 0) {
      numbers.sort((a, b) => a - b);
      const sum = numbers.reduce((a, b) => a + b, 0);
      const mean = sum / numbers.length;
      const variance = numbers.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / numbers.length;
      
      stats.min = numbers[0];
      stats.max = numbers[numbers.length - 1];
      stats.mean = mean;
      stats.median = numbers[Math.floor(numbers.length / 2)];
      stats.std = Math.sqrt(variance);
    }
  } else if (type === 'categorical') {
    const counts: Record<string, number> = {};
    nonNullValues.forEach((v) => {
      const key = String(v);
      counts[key] = (counts[key] || 0) + 1;
    });
    stats.categories = Object.keys(counts);
    stats.categoryCounts = counts;
  }

  return stats;
}

/**
 * 截断文本
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * 下载文件
 */
export function downloadFile(content: Blob | string, filename: string, type?: string) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: type || 'text/plain' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

/**
 * 防抖函数
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

/**
 * 节流函数
 */
export function throttle<T extends (...args: unknown[]) => unknown>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * 深拷贝
 */
export function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj;
  if (obj instanceof Date) return new Date(obj.getTime()) as unknown as T;
  if (Array.isArray(obj)) return obj.map((item) => deepClone(item)) as unknown as T;
  const cloned = {} as T;
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      cloned[key] = deepClone(obj[key]);
    }
  }
  return cloned;
}

/**
 * 期刊颜色方案
 */
export const journalColorPalettes = {
  nature: ['#E31837', '#4a90a4', '#2E8B57', '#FF8C00', '#8B4513', '#4B0082'],
  science: ['#8B0000', '#4169E1', '#228B22', '#FF6347', '#9932CC', '#FF8C00'],
  cell: ['#008080', '#FF6B35', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7'],
  default: [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
  ],
};

/**
 * 获取期刊样式配置
 */
export function getJournalStyle(style: keyof typeof journalColorPalettes) {
  const palettes = {
    nature: {
      font: 'Arial, sans-serif',
      fontSize: 12,
      colors: journalColorPalettes.nature,
      layout: {
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        font: { family: 'Arial, sans-serif', size: 12 },
        margin: { l: 60, r: 20, t: 40, b: 50 },
      },
    },
    science: {
      font: 'Helvetica, Arial, sans-serif',
      fontSize: 11,
      colors: journalColorPalettes.science,
      layout: {
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        font: { family: 'Helvetica, Arial, sans-serif', size: 11 },
        margin: { l: 60, r: 20, t: 40, b: 50 },
      },
    },
    cell: {
      font: 'Verdana, Arial, sans-serif',
      fontSize: 10,
      colors: journalColorPalettes.cell,
      layout: {
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        font: { family: 'Verdana, Arial, sans-serif', size: 10 },
        margin: { l: 60, r: 20, t: 40, b: 50 },
      },
    },
    default: {
      font: 'Inter, system-ui, sans-serif',
      fontSize: 14,
      colors: journalColorPalettes.default,
      layout: {
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        font: { family: 'Inter, system-ui, sans-serif', size: 14 },
        margin: { l: 60, r: 20, t: 40, b: 50 },
      },
    },
  };

  return palettes[style] || palettes.default;
}

/**
 * 将数据转换为 CSV
 */
export function convertToCSV(data: Record<string, unknown>[]): string {
  if (data.length === 0) return '';
  
  const headers = Object.keys(data[0]);
  const csvRows = [headers.join(',')];
  
  for (const row of data) {
    const values = headers.map((header) => {
      const value = row[header];
      if (value === null || value === undefined) return '';
      const stringValue = String(value);
      // 如果值包含逗号、引号或换行符，需要用引号包裹
      if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
        return `"${stringValue.replace(/"/g, '""')}"`;
      }
      return stringValue;
    });
    csvRows.push(values.join(','));
  }
  
  return csvRows.join('\n');
}

/**
 * 睡眠函数
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 检查是否为深色模式
 */
export function isDarkMode(): boolean {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/**
 * 监听深色模式变化
 */
export function watchDarkMode(callback: (isDark: boolean) => void): () => void {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = (e: MediaQueryListEvent) => callback(e.matches);
  mediaQuery.addEventListener('change', handler);
  return () => mediaQuery.removeEventListener('change', handler);
}
