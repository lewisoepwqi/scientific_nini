import { describe, it, expect } from 'vitest'
import {
  createInitialPlanState,
  applyPlanStepUpdate,
  createPlanProgress,
  deriveNextHint,
  updateAnalysisTaskById,
  areAllPlanStepsDone,
  getPlanCompletionPercentage,
  findTaskByPlanStepId,
  getLatestAttempt,
  createDefaultPlanSteps,
} from './plan-state-machine'
import { applyPlanStepUpdateToProgress, makePlanProgressFromSteps } from './utils'
import type { AnalysisStep, AnalysisTaskItem, AnalysisTaskAttempt } from './types'

describe('plan-state-machine', () => {
  describe('createInitialPlanState', () => {
    it('should create initial state with correct number of steps', () => {
      const state = createInitialPlanState(3)
      expect(state.steps).toHaveLength(3)
      expect(state.currentStepIndex).toBe(1)
      expect(state.stepStatus).toBe('not_started')
    })

    it('should create empty state for zero steps', () => {
      const state = createInitialPlanState(0)
      expect(state.steps).toHaveLength(0)
    })
  })

  describe('applyPlanStepUpdate', () => {
    it('should update step status', () => {
      const state = createInitialPlanState(3)
      const newState = applyPlanStepUpdate(state, 1, 'in_progress')
      expect(newState.steps[0].status).toBe('in_progress')
    })

    it('should recalculate current step index', () => {
      const state = createInitialPlanState(3)
      let newState = applyPlanStepUpdate(state, 1, 'done')
      expect(newState.currentStepIndex).toBe(2) // Next pending step

      newState = applyPlanStepUpdate(newState, 2, 'in_progress')
      expect(newState.currentStepIndex).toBe(2)
    })

    it('should handle failed step', () => {
      const state = createInitialPlanState(3)
      const newState = applyPlanStepUpdate(state, 2, 'failed')
      expect(newState.currentStepIndex).toBe(2)
      expect(newState.steps[1].status).toBe('failed')
    })

    it('should not modify original state', () => {
      const state = createInitialPlanState(3)
      const newState = applyPlanStepUpdate(state, 1, 'in_progress')
      expect(state.steps[0].status).toBe('not_started')
      expect(newState.steps[0].status).toBe('in_progress')
    })
  })

  describe('createPlanProgress', () => {
    it('should create progress object', () => {
      const steps = createDefaultPlanSteps(3)
      const progress = createPlanProgress(steps, 1, 'in_progress')
      expect(progress.steps).toHaveLength(3)
      expect(progress.current_step_index).toBe(1)
      expect(progress.total_steps).toBe(3)
      expect(progress.step_status).toBe('in_progress')
    })

    it('should set step title correctly', () => {
      const steps = createDefaultPlanSteps(3)
      const progress = createPlanProgress(steps, 2, 'in_progress')
      expect(progress.step_title).toBe('步骤 2')
    })

    it('should handle blocked status', () => {
      const steps = createDefaultPlanSteps(3)
      const progress = createPlanProgress(steps, 2, 'blocked')
      expect(progress.block_reason).toBe('步骤被阻塞')
    })

    it('should keep current step on in-progress task when a later pending step is updated', () => {
      const steps: AnalysisStep[] = [
        { id: 1, title: '步骤 1', tool_hint: null, status: 'done' },
        { id: 2, title: '步骤 2', tool_hint: null, status: 'done' },
        { id: 3, title: '步骤 3', tool_hint: null, status: 'done' },
        { id: 4, title: '步骤 4', tool_hint: null, status: 'done' },
        { id: 5, title: '结果可视化', tool_hint: null, status: 'not_started' },
        { id: 6, title: '生成分析报告', tool_hint: null, status: 'not_started' },
      ]
      const initial = makePlanProgressFromSteps(steps, '')
      expect(initial).not.toBeNull()

      const afterStepFive = applyPlanStepUpdateToProgress(initial, 5, 'in_progress')
      expect(afterStepFive?.current_step_index).toBe(5)
      expect(afterStepFive?.step_status).toBe('in_progress')
      expect(afterStepFive?.step_title).toBe('结果可视化')

      const afterStepSixPending = applyPlanStepUpdateToProgress(afterStepFive, 6, 'pending')
      expect(afterStepSixPending?.current_step_index).toBe(5)
      expect(afterStepSixPending?.step_status).toBe('in_progress')
      expect(afterStepSixPending?.step_title).toBe('结果可视化')
      expect(afterStepSixPending?.steps[5]?.status).toBe('not_started')
    })
  })

  describe('deriveNextHint', () => {
    const steps: AnalysisStep[] = [
      { id: 1, title: '第一步', tool_hint: null, status: 'done' },
      { id: 2, title: '第二步', tool_hint: null, status: 'in_progress' },
      { id: 3, title: '第三步', tool_hint: null, status: 'not_started' },
    ]

    it('should return hint for in_progress status', () => {
      const hint = deriveNextHint(steps, 2, 'in_progress')
      expect(hint).toContain('完成后将进入')
      expect(hint).toContain('第三步')
    })

    it('should return hint for done status', () => {
      const hint = deriveNextHint(steps, 1, 'done')
      expect(hint).toContain('下一步')
      expect(hint).toContain('第二步')
    })

    it('should return completion message when all done', () => {
      const hint = deriveNextHint(steps, 3, 'done')
      expect(hint).toContain('全部步骤已完成')
    })

    it('should return retry hint for failed/blocked status', () => {
      expect(deriveNextHint(steps, 2, 'failed')).toContain('重试')
      expect(deriveNextHint(steps, 2, 'blocked')).toContain('重试')
    })

    it('should handle empty steps', () => {
      expect(deriveNextHint([], 1, 'in_progress')).toBeNull()
    })
  })

  describe('updateAnalysisTaskById', () => {
    const tasks: AnalysisTaskItem[] = [
      {
        id: 'task-1',
        plan_step_id: 1,
        action_id: 'action-1',
        title: 'Task 1',
        tool_hint: null,
        status: 'not_started',
        current_activity: null,
        last_error: null,
        attempts: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      },
      {
        id: 'task-2',
        plan_step_id: 2,
        action_id: 'action-2',
        title: 'Task 2',
        tool_hint: null,
        status: 'in_progress',
        current_activity: null,
        last_error: null,
        attempts: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      },
    ]

    it('should update task by id', () => {
      const updated = updateAnalysisTaskById(tasks, 'task-1', { status: 'done' })
      expect(updated[0].status).toBe('done')
      expect(updated[1].status).toBe('in_progress') // Unchanged
    })

    it('should return original array for null taskId', () => {
      const updated = updateAnalysisTaskById(tasks, null, { status: 'done' })
      expect(updated).toBe(tasks)
    })

    it('should update timestamp', () => {
      const before = Date.now()
      const updated = updateAnalysisTaskById(tasks, 'task-1', { status: 'done' })
      expect(updated[0].updated_at).toBeGreaterThanOrEqual(before)
    })
  })

  describe('areAllPlanStepsDone', () => {
    it('should return true when all steps are done', () => {
      const steps: AnalysisStep[] = [
        { id: 1, title: 'Step 1', tool_hint: null, status: 'done' },
        { id: 2, title: 'Step 2', tool_hint: null, status: 'skipped' },
      ]
      expect(areAllPlanStepsDone(steps)).toBe(true)
    })

    it('should return false when some steps not done', () => {
      const steps: AnalysisStep[] = [
        { id: 1, title: 'Step 1', tool_hint: null, status: 'done' },
        { id: 2, title: 'Step 2', tool_hint: null, status: 'in_progress' },
      ]
      expect(areAllPlanStepsDone(steps)).toBe(false)
    })

    it('should return false for empty steps', () => {
      expect(areAllPlanStepsDone([])).toBe(false)
    })
  })

  describe('getPlanCompletionPercentage', () => {
    it('should calculate correct percentage', () => {
      const steps: AnalysisStep[] = [
        { id: 1, title: 'Step 1', tool_hint: null, status: 'done' },
        { id: 2, title: 'Step 2', tool_hint: null, status: 'in_progress' },
        { id: 3, title: 'Step 3', tool_hint: null, status: 'not_started' },
        { id: 4, title: 'Step 4', tool_hint: null, status: 'skipped' },
      ]
      expect(getPlanCompletionPercentage(steps)).toBe(50) // 2 out of 4
    })

    it('should return 0 for empty steps', () => {
      expect(getPlanCompletionPercentage([])).toBe(0)
    })

    it('should return 100 when all done', () => {
      const steps: AnalysisStep[] = [
        { id: 1, title: 'Step 1', tool_hint: null, status: 'done' },
        { id: 2, title: 'Step 2', tool_hint: null, status: 'done' },
      ]
      expect(getPlanCompletionPercentage(steps)).toBe(100)
    })
  })

  describe('findTaskByPlanStepId', () => {
    const tasks: AnalysisTaskItem[] = [
      {
        id: 'task-1',
        plan_step_id: 1,
        action_id: 'action-1',
        title: 'Task 1',
        tool_hint: null,
        status: 'not_started',
        current_activity: null,
        last_error: null,
        attempts: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      },
      {
        id: 'task-2',
        plan_step_id: 2,
        action_id: 'action-2',
        title: 'Task 2',
        tool_hint: null,
        status: 'in_progress',
        current_activity: null,
        last_error: null,
        attempts: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      },
    ]

    it('should find task by plan step id', () => {
      const task = findTaskByPlanStepId(tasks, 2)
      expect(task?.id).toBe('task-2')
    })

    it('should return undefined for non-existent step', () => {
      const task = findTaskByPlanStepId(tasks, 999)
      expect(task).toBeUndefined()
    })
  })

  describe('getLatestAttempt', () => {
    const attempts: AnalysisTaskAttempt[] = [
      {
        id: 'attempt-1',
        tool_name: 't_test',
        attempt: 1,
        max_attempts: 3,
        status: 'failed',
        note: null,
        error: 'Error 1',
        created_at: Date.now(),
        updated_at: Date.now(),
      },
      {
        id: 'attempt-2',
        tool_name: 't_test',
        attempt: 2,
        max_attempts: 3,
        status: 'success',
        note: null,
        error: null,
        created_at: Date.now(),
        updated_at: Date.now(),
      },
    ]

    const task: AnalysisTaskItem = {
      id: 'task-1',
      plan_step_id: 1,
      action_id: 'action-1',
      title: 'Task 1',
      tool_hint: null,
      status: 'done',
      current_activity: null,
      last_error: null,
      attempts,
      created_at: Date.now(),
      updated_at: Date.now(),
    }

    it('should return latest attempt', () => {
      const latest = getLatestAttempt(task)
      expect(latest?.id).toBe('attempt-2')
      expect(latest?.status).toBe('success')
    })

    it('should return null for no attempts', () => {
      const taskNoAttempts = { ...task, attempts: [] }
      expect(getLatestAttempt(taskNoAttempts)).toBeNull()
    })
  })
})
