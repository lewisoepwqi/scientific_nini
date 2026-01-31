import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { Task, SuggestionStatus } from '../types/task';

export interface TaskChartItem {
  id: string;
  taskId: string;
  configId?: string | null;
  renderLog?: Record<string, unknown> | null;
}

interface TaskState {
  currentTask: Task | null;
  tasks: Task[];
  taskCharts: Record<string, TaskChartItem[]>;
  suggestionStatusByTask: Record<string, SuggestionStatus>;

  setTasks: (tasks: Task[]) => void;
  setCurrentTask: (task: Task | null) => void;
  upsertTask: (task: Task) => void;
  setTaskCharts: (taskId: string, charts: TaskChartItem[]) => void;
  setSuggestionStatus: (taskId: string, status: SuggestionStatus) => void;
}

export const useTaskStore = create<TaskState>()(
  devtools(
    (set) => ({
      currentTask: null,
      tasks: [],
      taskCharts: {},
      suggestionStatusByTask: {},

      setTasks: (tasks) => {
        set({ tasks }, false, 'setTasks');
      },

      setCurrentTask: (task) => {
        set({ currentTask: task }, false, 'setCurrentTask');
      },

      upsertTask: (task) => {
        set(
          (state) => {
            const existing = state.tasks.find((item) => item.id === task.id);
            const tasks = existing
              ? state.tasks.map((item) => (item.id === task.id ? task : item))
              : [task, ...state.tasks];
            return { tasks, currentTask: state.currentTask?.id === task.id ? task : state.currentTask };
          },
          false,
          'upsertTask'
        );
      },

      setTaskCharts: (taskId, charts) => {
        set(
          (state) => ({
            taskCharts: { ...state.taskCharts, [taskId]: charts },
          }),
          false,
          'setTaskCharts'
        );
      },

      setSuggestionStatus: (taskId, status) => {
        set(
          (state) => ({
            suggestionStatusByTask: { ...state.suggestionStatusByTask, [taskId]: status },
          }),
          false,
          'setSuggestionStatus'
        );
      },
    }),
    { name: 'TaskStore' }
  )
);
