import React from 'react';
import { Bell, User, Moon, Sun } from 'lucide-react';
import { useUIStore } from '@store/index';
import { cn } from '@utils/helpers';

interface HeaderProps {
  className?: string;
}

export const Header: React.FC<HeaderProps> = ({ className }) => {
  const { theme, setTheme, notifications } = useUIStore();

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <header
      className={cn(
        'h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6',
        className
      )}
    >
      {/* 左侧 - 页面标题 */}
      <div>
        <h1 className="text-xl font-semibold text-gray-900">科研数据分析工具</h1>
        <p className="text-xs text-gray-500">Scientific Data Analysis Platform</p>
      </div>

      {/* 右侧 - 操作按钮 */}
      <div className="flex items-center gap-3">
        {/* 主题切换 */}
        <button
          onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {theme === 'light' ? (
            <Moon className="w-5 h-5" />
          ) : (
            <Sun className="w-5 h-5" />
          )}
        </button>

        {/* 通知 */}
        <button className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
              {unreadCount}
            </span>
          )}
        </button>

        {/* 用户头像 */}
        <div className="flex items-center gap-3 pl-3 border-l border-gray-200">
          <div className="text-right hidden md:block">
            <p className="text-sm font-medium text-gray-900">研究员</p>
            <p className="text-xs text-gray-500">user@example.com</p>
          </div>
          <div className="w-9 h-9 bg-primary-100 rounded-full flex items-center justify-center">
            <User className="w-5 h-5 text-primary-600" />
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
