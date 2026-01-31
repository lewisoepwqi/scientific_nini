import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  DatasetInfo,
  ChartConfig,
  ChartData,
  ChartLayer,
  SavedChart,
  StatisticalResult,
  AIMessage,
  AppPage,
  Notification,
  UploadProgress,
  AIAnalysisSuggestion,
} from '../types';
import { CHART_COMPATIBILITY, MAX_OVERLAY_LAYERS } from '../types';

// ==================== Dataset Store ====================

interface DatasetState {
  // 当前数据集
  currentDataset: DatasetInfo | null;
  datasets: DatasetInfo[];
  uploadProgress: UploadProgress | null;
  
  // 操作方法
  setCurrentDataset: (dataset: DatasetInfo | null) => void;
  addDataset: (dataset: DatasetInfo) => void;
  removeDataset: (id: string) => void;
  setUploadProgress: (progress: UploadProgress | null) => void;
  clearUploadProgress: () => void;
}

export const useDatasetStore = create<DatasetState>()(
  devtools(
    (set) => ({
      currentDataset: null,
      datasets: [],
      uploadProgress: null,

      setCurrentDataset: (dataset) => {
        set({ currentDataset: dataset }, false, 'setCurrentDataset');
      },

      addDataset: (dataset) => {
        set(
          (state) => ({
            datasets: [...state.datasets, dataset],
            currentDataset: dataset,
          }),
          false,
          'addDataset'
        );
      },

      removeDataset: (id) => {
        set(
          (state) => ({
            datasets: state.datasets.filter((d) => d.id !== id),
            currentDataset:
              state.currentDataset?.id === id
                ? null
                : state.currentDataset,
          }),
          false,
          'removeDataset'
        );
      },

      setUploadProgress: (progress) => {
        set({ uploadProgress: progress }, false, 'setUploadProgress');
      },

      clearUploadProgress: () => {
        set({ uploadProgress: null }, false, 'clearUploadProgress');
      },
    }),
    { name: 'DatasetStore' }
  )
);

// ==================== Chart Store ====================

interface ChartState {
  // 图表配置
  config: ChartConfig;
  chartData: ChartData | null;
  savedCharts: SavedChart[];
  currentChart: SavedChart | null;
  isGenerating: boolean;

  // 操作方法
  updateConfig: (config: Partial<ChartConfig>) => void;
  resetConfig: () => void;
  setChartData: (data: ChartData | null) => void;
  setCurrentChart: (chart: SavedChart | null) => void;
  saveChart: (chart: SavedChart) => void;
  deleteChart: (id: string) => void;
  setIsGenerating: (isGenerating: boolean) => void;

  // 图层管理方法
  addLayer: (layer: Omit<ChartLayer, 'id'>) => void;
  updateLayer: (id: string, updates: Partial<ChartLayer>) => void;
  removeLayer: (id: string) => void;
  clearLayers: () => void;
}

const defaultChartConfig: ChartConfig = {
  chartType: 'scatter',
  title: '未命名图表',
  xColumn: null,
  yColumn: null,
  groupColumn: null,
  colorColumn: null,
  journalStyle: 'default',
  colorPalette: [],
  showStatistics: true,
  showSignificance: false,
  significanceMethod: 't-test',
  width: 800,
  height: 600,
  fontSize: 14,
  showGrid: true,
  showLegend: true,
  layers: [],
};

export const useChartStore = create<ChartState>()(
  devtools(
    persist(
      (set) => ({
        config: { ...defaultChartConfig },
        chartData: null,
        savedCharts: [],
        currentChart: null,
        isGenerating: false,

        updateConfig: (config) => {
          set(
            (state) => ({
              config: { ...state.config, ...config },
            }),
            false,
            'updateConfig'
          );
        },

        resetConfig: () => {
          set({ config: { ...defaultChartConfig } }, false, 'resetConfig');
        },

        setChartData: (data) => {
          set({ chartData: data }, false, 'setChartData');
        },

        setCurrentChart: (chart) => {
          set({ currentChart: chart }, false, 'setCurrentChart');
        },

        saveChart: (chart) => {
          set(
            (state) => ({
              savedCharts: [...state.savedCharts, chart],
            }),
            false,
            'saveChart'
          );
        },

        deleteChart: (id) => {
          set(
            (state) => ({
              savedCharts: state.savedCharts.filter((c) => c.id !== id),
              currentChart:
                state.currentChart?.id === id ? null : state.currentChart,
            }),
            false,
            'deleteChart'
          );
        },

        setIsGenerating: (isGenerating) => {
          set({ isGenerating }, false, 'setIsGenerating');
        },

        addLayer: (layer) => {
          const id = Math.random().toString(36).substring(2, 9);
          set(
            (state) => {
              // 检查兼容性：如果已有图层，新图层必须兼容
              const existingLayers = state.config.layers || [];
              if (existingLayers.length > 0) {
                const primaryType = state.config.chartType;
                const allowed = CHART_COMPATIBILITY[primaryType] || [];
                if (!allowed.includes(layer.chartType)) {
                  // 兼容性检查由 UI 层处理，此处静默返回
                  return state;
                }
              }
              // 最多叠加层数限制
              if (existingLayers.length >= MAX_OVERLAY_LAYERS) {
                // 层数限制由 UI 层处理，此处静默返回
                return state;
              }
              return {
                config: {
                  ...state.config,
                  layers: [...existingLayers, { ...layer, id }],
                },
              };
            },
            false,
            'addLayer'
          );
        },

        updateLayer: (id, updates) => {
          set(
            (state) => ({
              config: {
                ...state.config,
                layers: (state.config.layers || []).map((layer) =>
                  layer.id === id ? { ...layer, ...updates } : layer
                ),
              },
            }),
            false,
            'updateLayer'
          );
        },

        removeLayer: (id) => {
          set(
            (state) => ({
              config: {
                ...state.config,
                layers: (state.config.layers || []).filter((layer) => layer.id !== id),
              },
            }),
            false,
            'removeLayer'
          );
        },

        clearLayers: () => {
          set(
            (state) => ({
              config: {
                ...state.config,
                layers: [],
              },
            }),
            false,
            'clearLayers'
          );
        },
      }),
      {
        name: 'ChartStore',
        partialize: (state) => ({ savedCharts: state.savedCharts }),
      }
    ),
    { name: 'ChartStore' }
  )
);

// ==================== Analysis Store ====================

interface AnalysisState {
  results: StatisticalResult[];
  isAnalyzing: boolean;
  selectedResult: StatisticalResult | null;
  
  // 操作方法
  addResult: (result: StatisticalResult) => void;
  removeResult: (id: string) => void;
  setSelectedResult: (result: StatisticalResult | null) => void;
  setIsAnalyzing: (isAnalyzing: boolean) => void;
  clearResults: () => void;
}

export const useAnalysisStore = create<AnalysisState>()(
  devtools(
    persist(
      (set) => ({
        results: [],
        isAnalyzing: false,
        selectedResult: null,

        addResult: (result) => {
          set(
            (state) => ({
              results: [result, ...state.results],
            }),
            false,
            'addResult'
          );
        },

        removeResult: (id) => {
          set(
            (state) => ({
              results: state.results.filter((r) => r.id !== id),
              selectedResult:
                state.selectedResult?.id === id ? null : state.selectedResult,
            }),
            false,
            'removeResult'
          );
        },

        setSelectedResult: (result) => {
          set({ selectedResult: result }, false, 'setSelectedResult');
        },

        setIsAnalyzing: (isAnalyzing) => {
          set({ isAnalyzing }, false, 'setIsAnalyzing');
        },

        clearResults: () => {
          set({ results: [], selectedResult: null }, false, 'clearResults');
        },
      }),
      {
        name: 'AnalysisStore',
        partialize: (state) => ({ results: state.results }),
      }
    ),
    { name: 'AnalysisStore' }
  )
);

// ==================== AI Chat Store ====================

interface AIChatState {
  messages: AIMessage[];
  isStreaming: boolean;
  suggestions: AIAnalysisSuggestion[];
  
  // 操作方法
  addMessage: (message: AIMessage) => void;
  updateMessage: (id: string, updates: Partial<AIMessage>) => void;
  clearMessages: () => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setSuggestions: (suggestions: AIAnalysisSuggestion[]) => void;
}

export const useAIChatStore = create<AIChatState>()(
  devtools(
    persist(
      (set) => ({
        messages: [
          {
            id: 'welcome',
            role: 'assistant',
            content: '你好！我是你的科研数据分析助手。我可以帮助你分析数据、生成图表、进行统计检验等。请问有什么可以帮助你的？',
            timestamp: new Date(),
          },
        ],
        isStreaming: false,
        suggestions: [],

        addMessage: (message) => {
          set(
            (state) => ({
              messages: [...state.messages, message],
            }),
            false,
            'addMessage'
          );
        },

        updateMessage: (id, updates) => {
          set(
            (state) => ({
              messages: state.messages.map((m) =>
                m.id === id ? { ...m, ...updates } : m
              ),
            }),
            false,
            'updateMessage'
          );
        },

        clearMessages: () => {
          set(
            {
              messages: [
                {
                  id: 'welcome',
                  role: 'assistant',
                  content: '你好！我是你的科研数据分析助手。我可以帮助你分析数据、生成图表、进行统计检验等。请问有什么可以帮助你的？',
                  timestamp: new Date(),
                },
              ],
            },
            false,
            'clearMessages'
          );
        },

        setIsStreaming: (isStreaming) => {
          set({ isStreaming }, false, 'setIsStreaming');
        },

        setSuggestions: (suggestions) => {
          set({ suggestions }, false, 'setSuggestions');
        },
      }),
      {
        name: 'AIChatStore',
        partialize: (state) => ({ messages: state.messages }),
      }
    ),
    { name: 'AIChatStore' }
  )
);

// ==================== UI Store ====================

interface UIState {
  currentPage: AppPage;
  sidebarCollapsed: boolean;
  notifications: Notification[];
  theme: 'light' | 'dark';
  
  // 操作方法
  setCurrentPage: (page: AppPage) => void;
  toggleSidebar: () => void;
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  setTheme: (theme: 'light' | 'dark') => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set, get) => ({
        currentPage: 'upload',
        sidebarCollapsed: false,
        notifications: [],
        theme: 'light',

        setCurrentPage: (page) => {
          set({ currentPage: page }, false, 'setCurrentPage');
        },

        toggleSidebar: () => {
          set(
            (state) => ({ sidebarCollapsed: !state.sidebarCollapsed }),
            false,
            'toggleSidebar'
          );
        },

        addNotification: (notification) => {
          const id = Math.random().toString(36).substring(7);
          set(
            (state) => ({
              notifications: [
                ...state.notifications,
                { ...notification, id },
              ],
            }),
            false,
            'addNotification'
          );

          // 自动移除通知
          const duration = notification.duration || 5000;
          setTimeout(() => {
            get().removeNotification(id);
          }, duration);
        },

        removeNotification: (id) => {
          set(
            (state) => ({
              notifications: state.notifications.filter((n) => n.id !== id),
            }),
            false,
            'removeNotification'
          );
        },

        setTheme: (theme) => {
          set({ theme }, false, 'setTheme');
        },
      }),
      {
        name: 'UIStore',
        partialize: (state) => ({
          sidebarCollapsed: state.sidebarCollapsed,
          theme: state.theme,
        }),
      }
    ),
    { name: 'UIStore' }
  )
);

// ==================== 导出组合 Hook ====================

export const useAppStore = () => ({
  dataset: useDatasetStore(),
  chart: useChartStore(),
  analysis: useAnalysisStore(),
  aiChat: useAIChatStore(),
  ui: useUIStore(),
});
