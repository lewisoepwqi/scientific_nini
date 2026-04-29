import { z } from "zod";

export const LongTermMemoryEntrySchema = z.object({
  id: z.string(),
  memory_type: z.string(),
  content: z.string(),
  summary: z.string().default(""),
  source_session_id: z.string().default(""),
  source_dataset: z.string().nullable().default(null),
  analysis_type: z.string().nullable().default(null),
  confidence: z.number().nullable().default(null),
  importance_score: z.number().default(0.5),
  tags: z.array(z.string()).default([]),
  metadata: z.record(z.string(), z.unknown()).default({}),
  created_at: z.union([z.string(), z.number()]).default(""),
  last_accessed_at: z.union([z.string(), z.number()]).nullable().default(null),
  access_count: z.number().default(0),
});

export const LongTermMemoryStatsSchema = z.object({
  total_memories: z.number().default(0),
  type_distribution: z.record(z.string(), z.number()).default({}),
  vector_store_available: z.boolean().default(false),
  last_updated_ts: z.number().nullable().default(null),
  storage: z.string().default("sqlite"),
});

export const LongTermMemoryListResponseSchema = z.object({
  memories: z.array(LongTermMemoryEntrySchema).default([]),
  total: z.number().default(0),
});

export type ValidatedLongTermMemoryEntry = z.infer<typeof LongTermMemoryEntrySchema>;
export type ValidatedLongTermMemoryStats = z.infer<typeof LongTermMemoryStatsSchema>;
