import React from 'react';
import {
  Upload,
  Table,
  BarChart3,
  Calculator,
  MessageSquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  Heart,
} from 'lucide-react';
import { useUIStore } from '@store/index';
import { cn } from '@utils/helpers';
import type { AppPage } from '../../types';

interface NavItem {
  id: AppPage;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const navItems: NavItem[] = [
  {
    id: 'upload',
    label: '文件上传',
    icon: <Upload className="w-5 h-5" />,
    description: '上传 CSV/Excel 文件',
  },
  {
    id: 'preview',
    label: '数据预览',
    icon: <Table className="w-5 h-5" />,
    description: '查看和探索数据',
  },
  {
    id: 'chart',
    label: '图表生成',
    icon: <BarChart3 className="w-5 h-5" />,
    description: '创建可视化图表',
  },
  {
    id: 'analysis',
    label: '统计分析',
    icon: <Calculator className="w-5 h-5" />,
    description: '执行统计检验',
  },
  {
    id: 'chat',
    label: 'AI 助手',
    icon: <MessageSquare className="w-5 h-5" />,
    description: '智能数据分析',
  },
];

export const Sidebar: React.FC = () => {
  const { currentPage, setCurrentPage, sidebarCollapsed, toggleSidebar } = useUIStore();

  return (
    <aside
      className={cn(
        'h-screen bg-white border-r border-gray-200 flex flex-col transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        {!sidebarCollapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-primary-400 to-primary-600 rounded-lg flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-gray-900">DataLab</span>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <ChevronLeft className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* 导航 */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setCurrentPage(item.id)}
            className={cn(
              'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all',
              currentPage === item.id
                ? 'bg-primary-50 text-primary-700'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
              sidebarCollapsed && 'justify-center'
            )}
            title={sidebarCollapsed ? item.label : undefined}
          >
            <span
              className={cn(
                'flex-shrink-0',
                currentPage === item.id ? 'text-primary-600' : 'text-gray-400'
              )}
            >
              {item.icon}
            </span>
            {!sidebarCollapsed && (
              <div className="text-left">
                <p className="text-sm font-medium">{item.label}</p>
                <p className="text-xs text-gray-400">{item.description}</p>
              </div>
            )}
          </button>
        ))}
      </nav>

      {/* 底部 */}
      <div className="p-4 border-t border-gray-100">
        {!sidebarCollapsed ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Heart className="w-3 h-3 text-red-400 fill-red-400" />
              <span>Made with love</span>
            </div>
            <button className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <Settings className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button className="w-full flex justify-center p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
            <Settings className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
