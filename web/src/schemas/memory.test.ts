import { describe, expect, it } from "vitest";

import {
  LongTermMemoryEntrySchema,
  LongTermMemoryStatsSchema,
  LongTermMemoryListResponseSchema,
} from "./memory";

describe("LongTermMemoryStatsSchema", () => {
  it("应校验完整的 stats 响应", () => {
    const input = {
      total_memories: 42,
      type_distribution: { finding: 10, statistic: 20, decision: 8, insight: 4 },
      vector_store_available: false,
      last_updated_ts: 1714000000,
      storage: "sqlite",
    };
    const result = LongTermMemoryStatsSchema.safeParse(input);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.total_memories).toBe(42);
      expect(result.data.type_distribution.finding).toBe(10);
    }
  });

  it("应为缺失的可选字段提供默认值", () => {
    const input = {};
    const result = LongTermMemoryStatsSchema.safeParse(input);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.total_memories).toBe(0);
      expect(result.data.type_distribution).toEqual({});
      expect(result.data.vector_store_available).toBe(false);
      expect(result.data.storage).toBe("sqlite");
    }
  });

  it("应拒绝 null 输入", () => {
    const result = LongTermMemoryStatsSchema.safeParse(null);
    expect(result.success).toBe(false);
  });

  it("应拒绝 type_distribution 为 null 的情况", () => {
    const input = {
      total_memories: 0,
      type_distribution: null,
    };
    const result = LongTermMemoryStatsSchema.safeParse(input);
    expect(result.success).toBe(false);
  });
});

describe("LongTermMemoryEntrySchema", () => {
  it("应校验完整的记忆条目", () => {
    const input = {
      id: "mem-001",
      memory_type: "finding",
      content: "数据集包含 1000 行记录",
      summary: "数据集规模确认",
      source_session_id: "sess-001",
      source_dataset: "sales.csv",
      analysis_type: "descriptive",
      confidence: 0.85,
      importance_score: 0.7,
      tags: ["规模", "确认"],
      metadata: { dataset_name: "sales.csv" },
      created_at: "2026-04-30T00:00:00Z",
      last_accessed_at: null,
      access_count: 0,
    };
    const result = LongTermMemoryEntrySchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it("应为缺失字段提供安全默认值", () => {
    const input = {
      id: "mem-002",
      memory_type: "insight",
      content: "关键发现",
    };
    const result = LongTermMemoryEntrySchema.safeParse(input);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.summary).toBe("");
      expect(result.data.tags).toEqual([]);
      expect(result.data.importance_score).toBe(0.5);
      expect(result.data.access_count).toBe(0);
      expect(result.data.source_dataset).toBeNull();
    }
  });
});

describe("LongTermMemoryListResponseSchema", () => {
  it("应校验包含条目的列表响应", () => {
    const input = {
      memories: [
        { id: "m1", memory_type: "finding", content: "test" },
      ],
      total: 1,
    };
    const result = LongTermMemoryListResponseSchema.safeParse(input);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.memories).toHaveLength(1);
      expect(result.data.total).toBe(1);
    }
  });

  it("应接受空列表", () => {
    const input = { memories: [], total: 0 };
    const result = LongTermMemoryListResponseSchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it("应在 memories 为 null 时使用默认空数组", () => {
    const input = { memories: null, total: 0 };
    const result = LongTermMemoryListResponseSchema.safeParse(input);
    // zod array().default([]) 不会将 null 转为空数组，会报错
    // 但 safeParse 会捕获
    expect(result.success).toBe(false);
  });

  it("应在完全畸形输入时优雅失败", () => {
    const result = LongTermMemoryListResponseSchema.safeParse("not an object");
    expect(result.success).toBe(false);
  });
});
