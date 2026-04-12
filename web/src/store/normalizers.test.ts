import { describe, it, expect } from 'vitest'
import {
  normalizeIntentOption,
  normalizeIntentCandidate,
  normalizeIntentSkillCall,
  normalizeIntentSkillSummary,
  normalizePlanStepStatus,
  normalizeTaskAttemptStatus,
  stripReasoningMarkers,
  isTerminalPlanStepStatus,
  mergePlanStepStatus,
  truncatePlanText,
  createDefaultPlanSteps,
  normalizeAnalysisSteps,
} from './normalizers'

describe('normalizers', () => {
  describe('normalizeIntentOption', () => {
    it('should normalize valid option', () => {
      const result = normalizeIntentOption({ label: 'Test', description: 'A test option' })
      expect(result).toEqual({ label: 'Test', description: 'A test option' })
    })

    it('should return null for invalid input', () => {
      expect(normalizeIntentOption(null)).toBeNull()
      expect(normalizeIntentOption(undefined)).toBeNull()
      expect(normalizeIntentOption('string')).toBeNull()
      expect(normalizeIntentOption({})).toBeNull()
    })

    it('should return null when description is missing', () => {
      expect(normalizeIntentOption({ label: 'Test' })).toBeNull()
    })
  })

  describe('normalizeIntentCandidate', () => {
    it('should normalize valid candidate', () => {
      const result = normalizeIntentCandidate({
        name: 'correlation_analysis',
        score: 0.85,
        reason: 'High confidence match',
      })
      expect(result).toEqual({
        name: 'correlation_analysis',
        score: 0.85,
        reason: 'High confidence match',
      })
    })

    it('should use default values for missing fields', () => {
      const result = normalizeIntentCandidate({ name: 'test' })
      expect(result).toEqual({
        name: 'test',
        score: 0,
        reason: '',
      })
    })

    it('should return null for missing name', () => {
      expect(normalizeIntentCandidate({ score: 0.5 })).toBeNull()
    })
  })

  describe('normalizeIntentSkillCall', () => {
    it('should normalize valid skill call', () => {
      const result = normalizeIntentSkillCall({
        name: 't_test',
        arguments: '{"column": "value"}',
      })
      expect(result).toEqual({
        name: 't_test',
        arguments: '{"column": "value"}',
      })
    })

    it('should use empty string for missing arguments', () => {
      const result = normalizeIntentSkillCall({ name: 't_test' })
      expect(result).toEqual({
        name: 't_test',
        arguments: '',
      })
    })

    it('should return null for missing name', () => {
      expect(normalizeIntentSkillCall({ arguments: '{}' })).toBeNull()
    })
  })

  describe('normalizeIntentSkillSummary', () => {
    it('should normalize valid skill summary', () => {
      const result = normalizeIntentSkillSummary({
        name: 't_test',
        description: 'Perform t-test analysis',
        category: 'statistics',
        research_domain: 'general',
        difficulty_level: 'intermediate',
        location: '/skills/t_test.md',
        allowed_tools: ['t_test'],
      })
      expect(result).toEqual({
        name: 't_test',
        description: 'Perform t-test analysis',
        category: 'statistics',
        research_domain: 'general',
        difficulty_level: 'intermediate',
        location: '/skills/t_test.md',
        allowed_tools: ['t_test'],
      })
    })

    it('should use default values for missing fields', () => {
      const result = normalizeIntentSkillSummary({
        name: 't_test',
        description: 'Perform t-test analysis',
      })
      expect(result).toEqual({
        name: 't_test',
        description: 'Perform t-test analysis',
        category: 'other',
        research_domain: 'general',
        difficulty_level: 'intermediate',
        location: '',
        allowed_tools: [],
      })
    })

    it('should return null for missing name', () => {
      expect(normalizeIntentSkillSummary({ description: 'Test' })).toBeNull()
    })
  })

  describe('normalizePlanStepStatus', () => {
    it('should normalize various status strings', () => {
      expect(normalizePlanStepStatus('pending')).toBe('not_started')
      expect(normalizePlanStepStatus('not_started')).toBe('not_started')
      expect(normalizePlanStepStatus('in_progress')).toBe('in_progress')
      expect(normalizePlanStepStatus('completed')).toBe('done')
      expect(normalizePlanStepStatus('done')).toBe('done')
      expect(normalizePlanStepStatus('error')).toBe('failed')
      expect(normalizePlanStepStatus('failed')).toBe('failed')
      expect(normalizePlanStepStatus('blocked')).toBe('blocked')
      expect(normalizePlanStepStatus('skipped')).toBe('skipped')
    })

    it('should handle unknown status', () => {
      expect(normalizePlanStepStatus('unknown')).toBe('not_started')
      expect(normalizePlanStepStatus(null)).toBe('not_started')
      expect(normalizePlanStepStatus(123)).toBe('not_started')
    })
  })

  describe('normalizeTaskAttemptStatus', () => {
    it('should normalize attempt status', () => {
      expect(normalizeTaskAttemptStatus('retrying')).toBe('retrying')
      expect(normalizeTaskAttemptStatus('success')).toBe('success')
      expect(normalizeTaskAttemptStatus('done')).toBe('success')
      expect(normalizeTaskAttemptStatus('failed')).toBe('failed')
      expect(normalizeTaskAttemptStatus('error')).toBe('failed')
      expect(normalizeTaskAttemptStatus('in_progress')).toBe('in_progress')
    })
  })

  describe('stripReasoningMarkers', () => {
    it('should strip thinking markers', () => {
      expect(stripReasoningMarkers('<think>content</think>')).toBe('content')
      expect(stripReasoningMarkers('<thinking>content</thinking>')).toBe('content')
      expect(stripReasoningMarkers('◁think▷content◁/think▷')).toBe('content')
    })

    it('should handle text without markers', () => {
      expect(stripReasoningMarkers('plain text')).toBe('plain text')
    })

    it('should handle empty input', () => {
      expect(stripReasoningMarkers('')).toBe('')
      expect(stripReasoningMarkers(null as unknown as string)).toBe(null as unknown as string)
    })
  })

  describe('isTerminalPlanStepStatus', () => {
    it('should identify terminal statuses', () => {
      expect(isTerminalPlanStepStatus('done')).toBe(true)
      expect(isTerminalPlanStepStatus('skipped')).toBe(true)
      expect(isTerminalPlanStepStatus('not_started')).toBe(false)
      expect(isTerminalPlanStepStatus('in_progress')).toBe(false)
      expect(isTerminalPlanStepStatus('failed')).toBe(false)
      expect(isTerminalPlanStepStatus('blocked')).toBe(false)
    })
  })

  describe('mergePlanStepStatus', () => {
    it('should return same status when equal', () => {
      expect(mergePlanStepStatus('in_progress', 'in_progress')).toBe('in_progress')
    })

    it('should not overwrite terminal status', () => {
      expect(mergePlanStepStatus('done', 'in_progress')).toBe('done')
      expect(mergePlanStepStatus('skipped', 'failed')).toBe('skipped')
    })

    it('should upgrade to terminal status', () => {
      expect(mergePlanStepStatus('in_progress', 'done')).toBe('done')
      expect(mergePlanStepStatus('in_progress', 'skipped')).toBe('skipped')
    })

    it('should handle failed vs blocked', () => {
      expect(mergePlanStepStatus('failed', 'blocked')).toBe('failed')
      expect(mergePlanStepStatus('blocked', 'failed')).toBe('failed')
    })
  })

  describe('truncatePlanText', () => {
    it('should not truncate short text', () => {
      expect(truncatePlanText('short')).toBe('short')
    })

    it('should truncate long text', () => {
      const longText = 'a'.repeat(100)
      expect(truncatePlanText(longText)).toHaveLength(72)
      expect(truncatePlanText(longText).endsWith('…')).toBe(true)
    })

    it('should respect custom max length', () => {
      expect(truncatePlanText('hello world', 8)).toBe('hello w…')
    })
  })

  describe('createDefaultPlanSteps', () => {
    it('should create default steps', () => {
      const steps = createDefaultPlanSteps(3)
      expect(steps).toHaveLength(3)
      expect(steps[0]).toEqual({
        id: 1,
        title: '步骤 1',
        tool_hint: null,
        status: 'not_started',
      })
      expect(steps[1]).toEqual({
        id: 2,
        title: '步骤 2',
        tool_hint: null,
        status: 'not_started',
      })
    })

    it('should handle zero steps', () => {
      expect(createDefaultPlanSteps(0)).toHaveLength(0)
    })

    it('should handle negative input', () => {
      expect(createDefaultPlanSteps(-5)).toHaveLength(0)
    })
  })

  describe('normalizeAnalysisSteps', () => {
    it('should normalize valid steps', () => {
      const raw = [
        { id: 1, title: 'Step 1', tool_hint: 'tool1', status: 'pending' },
        { id: 2, title: 'Step 2', tool_hint: null, status: 'in_progress' },
      ]
      const result = normalizeAnalysisSteps(raw)
      expect(result).toHaveLength(2)
      expect(result[0].status).toBe('not_started')
      expect(result[1].status).toBe('in_progress')
    })

    it('should handle missing fields', () => {
      const raw = [{}]
      const result = normalizeAnalysisSteps(raw)
      expect(result[0]).toEqual({
        id: 1,
        title: '步骤 1',
        tool_hint: null,
        status: 'not_started',
        action_id: null,
        raw_status: undefined,
        depends_on: undefined,
        executor: null,
        owner: null,
        input_refs: [],
        output_refs: [],
        handoff_contract: null,
        tool_profile: null,
        failure_policy: null,
        acceptance_checks: [],
      })
    })

    it('should handle non-array input', () => {
      expect(normalizeAnalysisSteps(null)).toHaveLength(0)
      expect(normalizeAnalysisSteps('string')).toHaveLength(0)
      expect(normalizeAnalysisSteps({})).toHaveLength(0)
    })
  })
})
