/**
 * API Actions
 *
 * 所有异步 API 调用函数，从 store.ts 提取
 * 每个函数都是独立的，接受必要参数并返回结果，不调用 set()
 */

import type {
  SessionItem,
  DatasetItem,
  WorkspaceFile,
  WorkspaceFolder,
  SkillItem,
  SkillDetail,
  SkillPathEntry,
  SkillFileContent,
  CapabilityItem,
  CodeExecution,
  MemoryFile,
  ActiveModelInfo,
  ModelProviderInfo,
  ResearchProfile,
  TokenUsage,
  SessionCostSummary,
  AggregateCostSummary,
  PricingConfig,
  IntentAnalysisView,
  RawSessionMessage,
  Message,
  AnalysisTaskItem,
  AnalysisPlanProgress,
  AnalysisStep,
} from "./types";

import { isRecord, nextId, makePlanProgressFromSteps } from "./utils";
import { normalizePlanStepStatus } from "./normalizers";
import {
  normalizeMessageTimestamp,
  upsertAssistantTextMessage,
  upsertReasoningMessage,
  upsertToolCallMessage,
  upsertToolResultMessage,
} from "./message-normalizer";
import { normalizeToolResult } from "./tool-result";

// ---- 会话相关 API ----

export async function fetchSessions(): Promise<SessionItem[]> {
  try {
    const resp = await fetch("/api/sessions");
    const payload = await resp.json();
    if (payload.success && Array.isArray(payload.data)) {
      return payload.data as SessionItem[];
    }
    return [];
  } catch (e) {
    console.error("获取会话列表失败:", e);
    return [];
  }
}

export async function createNewSession(): Promise<string | null> {
  try {
    const resp = await fetch("/api/sessions", { method: "POST" });
    const payload = await resp.json();
    const data = isRecord(payload) ? payload.data : null;
    const newSessionId = isRecord(data) ? data.session_id : null;
    if (typeof newSessionId === "string" && newSessionId) {
      return newSessionId;
    }
    return null;
  } catch (e) {
    console.error("创建新会话失败:", e);
    return null;
  }
}

export async function switchSession(
  targetSessionId: string,
): Promise<{ success: boolean; messages?: unknown[] }> {
  try {
    const resp = await fetch(`/api/sessions/${targetSessionId}/messages`);
    const payload = await resp.json();
    if (!payload.success) {
      return { success: true, messages: [] };
    }
    const data = isRecord(payload.data) ? payload.data : null;
    const rawMessages =
      isRecord(data) && Array.isArray(data.messages) ? data.messages : [];
    return { success: true, messages: rawMessages as unknown[] };
  } catch (e) {
    console.error("切换会话失败:", e);
    return { success: false };
  }
}

export async function deleteSession(targetSessionId: string): Promise<boolean> {
  try {
    await fetch(`/api/sessions/${targetSessionId}`, { method: "DELETE" });
    return true;
  } catch (e) {
    console.error("删除会话失败:", e);
    return false;
  }
}

export async function updateSessionTitle(
  targetSessionId: string,
  title: string,
): Promise<boolean> {
  try {
    await fetch(`/api/sessions/${targetSessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    return true;
  } catch (e) {
    console.error("更新会话标题失败:", e);
    return false;
  }
}

export interface RestoredSessionState {
  messages: Message[];
  analysisTasks: AnalysisTaskItem[];
  analysisPlanProgress: AnalysisPlanProgress | null;
}

export async function compressCurrentSession(
  sessionId: string,
): Promise<{ success: boolean; message: string; archivedCount?: number; remainingCount?: number }> {
  if (!sessionId) {
    return { success: false, message: "请先选择会话" };
  }
  try {
    const resp = await fetch(`/api/sessions/${sessionId}/compress`, {
      method: "POST",
    });
    const payload = await resp.json();
    if (!payload.success) {
      return {
        success: false,
        message:
          typeof payload.error === "string" ? payload.error : "会话压缩失败",
      };
    }
    const data = isRecord(payload.data) ? payload.data : null;
    const archivedCount =
      typeof data?.archived_count === "number" ? data.archived_count : 0;
    const remainingCount =
      typeof data?.remaining_count === "number" ? data.remaining_count : 0;
    const message = `会话压缩完成：归档 ${archivedCount} 条，剩余 ${remainingCount} 条`;
    return { success: true, message, archivedCount, remainingCount };
  } catch (e) {
    console.error("压缩会话失败:", e);
    return { success: false, message: "压缩会话失败，请稍后重试" };
  }
}

// ---- 数据集相关 API ----

export async function fetchDatasets(sessionId: string): Promise<DatasetItem[]> {
  if (!sessionId) {
    return [];
  }
  try {
    const resp = await fetch(`/api/datasets/${sessionId}`);
    const payload = await resp.json();
    const data = isRecord(payload.data) ? payload.data : null;
    const datasets =
      data && Array.isArray(data.datasets) ? data.datasets : [];
    return datasets as DatasetItem[];
  } catch (e) {
    console.error("获取数据集列表失败:", e);
    return [];
  }
}

export async function loadDataset(
  sessionId: string,
  datasetId: string,
): Promise<boolean> {
  if (!sessionId || !datasetId) return false;
  try {
    await fetch(`/api/datasets/${sessionId}/${datasetId}/load`, {
      method: "POST",
    });
    return true;
  } catch (e) {
    console.error("加载数据集失败:", e);
    return false;
  }
}

// ---- 工作区文件相关 API ----

export async function fetchWorkspaceFiles(
  sessionId: string,
): Promise<WorkspaceFile[]> {
  if (!sessionId) {
    return [];
  }
  try {
    const resp = await fetch(`/api/workspace/${sessionId}/files`);
    const payload = await resp.json();
    const data = isRecord(payload.data) ? payload.data : null;
    const files = data && Array.isArray(data.files) ? data.files : [];
    return files as WorkspaceFile[];
  } catch (e) {
    console.error("获取工作空间文件失败:", e);
    return [];
  }
}

export async function deleteWorkspaceFile(
  sessionId: string,
  filePath: string,
): Promise<boolean> {
  if (!sessionId || !filePath) return false;
  try {
    const resp = await fetch(
      `/api/workspace/${sessionId}/files/${filePath}`,
      {
        method: "DELETE",
      },
    );
    const payload = await resp.json();
    return payload.success === true;
  } catch (e) {
    console.error("删除文件失败:", e);
    return false;
  }
}

export async function renameWorkspaceFile(
  sessionId: string,
  filePath: string,
  newName: string,
): Promise<boolean> {
  if (!sessionId || !filePath || !newName.trim()) return false;
  try {
    const resp = await fetch(
      `/api/workspace/${sessionId}/files/${filePath}/rename`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName }),
      },
    );
    const payload = await resp.json();
    return payload.success === true;
  } catch (e) {
    console.error("重命名文件失败:", e);
    return false;
  }
}

export async function createWorkspaceFile(
  sessionId: string,
  filename: string,
  content?: string,
): Promise<boolean> {
  if (!sessionId || !filename.trim()) return false;
  const path = `notes/${filename.trim()}`;
  try {
    await fetch(`/api/workspace/${sessionId}/files/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content ?? "" }),
    });
    return true;
  } catch (e) {
    console.error("创建文件失败:", e);
    return false;
  }
}

// ---- 文件夹相关 API ----

export async function fetchFolders(
  sessionId: string,
): Promise<WorkspaceFolder[]> {
  if (!sessionId) {
    return [];
  }
  try {
    const resp = await fetch(`/api/workspace/${sessionId}/folders`);
    const payload = await resp.json();
    const data = isRecord(payload.data) ? payload.data : null;
    const folders = data && Array.isArray(data.folders) ? data.folders : [];
    return folders as WorkspaceFolder[];
  } catch (e) {
    console.error("获取文件夹失败:", e);
    return [];
  }
}

export async function createFolder(
  sessionId: string,
  name: string,
  parent?: string | null,
): Promise<boolean> {
  if (!sessionId || !name.trim()) return false;
  try {
    await fetch(`/api/workspace/${sessionId}/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent: parent ?? null }),
    });
    return true;
  } catch (e) {
    console.error("创建文件夹失败:", e);
    return false;
  }
}

export async function moveFileToFolder(
  sessionId: string,
  filePath: string,
  folderId: string | null,
): Promise<boolean> {
  if (!sessionId || !filePath) return false;
  try {
    await fetch(`/api/workspace/${sessionId}/files/${filePath}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
    });
    return true;
  } catch (e) {
    console.error("移动文件失败:", e);
    return false;
  }
}

// ---- 代码执行相关 API ----

export async function fetchCodeExecutions(
  sessionId: string,
): Promise<CodeExecution[]> {
  if (!sessionId) {
    return [];
  }
  try {
    const resp = await fetch(`/api/workspace/${sessionId}/executions`);
    const payload = await resp.json();
    const data = isRecord(payload.data) ? payload.data : null;
    const executions =
      data && Array.isArray(data.executions) ? data.executions : [];
    return executions as CodeExecution[];
  } catch (e) {
    console.error("获取执行历史失败:", e);
    return [];
  }
}

// ---- 技能相关 API ----

export async function fetchSkills(): Promise<SkillItem[]> {
  try {
    const [skillsResp, toolsResp] = await Promise.all([
      fetch("/api/skills"),
      fetch("/api/tools"),
    ]);
    const [skillsPayload, toolsPayload] = await Promise.all([
      skillsResp.json(),
      toolsResp.json(),
    ]);

    const skillsData = isRecord(skillsPayload.data)
      ? skillsPayload.data
      : null;
    const toolsData = isRecord(toolsPayload.data) ? toolsPayload.data : null;

    const markdownSkills =
      skillsData && Array.isArray(skillsData.skills) ? skillsData.skills : [];
    const functionTools =
      toolsData && Array.isArray(toolsData.tools) ? toolsData.tools : [];

    return [
      ...(functionTools as SkillItem[]),
      ...(markdownSkills as SkillItem[]),
    ];
  } catch (e) {
    console.error("获取技能列表失败:", e);
    return [];
  }
}

export async function uploadSkillFile(
  file: File,
): Promise<{ success: boolean; message: string }> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    const resp = await fetch("/api/skills/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `上传失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "上传成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "上传失败";
    console.error("上传技能失败:", e);
    return { success: false, message };
  }
}

export async function getSkillDetail(
  skillName: string,
): Promise<{ success: boolean; skill?: SkillDetail; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}`,
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `获取技能详情失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }

    const data = isRecord(payload.data) ? payload.data : null;
    const rawSkill = data && isRecord(data.skill) ? data.skill : null;
    if (!rawSkill) {
      throw new Error("技能详情响应格式错误");
    }
    return {
      success: true,
      message: "ok",
      skill: rawSkill as unknown as SkillDetail,
    };
  } catch (e) {
    const message = e instanceof Error ? e.message : "获取技能详情失败";
    console.error("获取技能详情失败:", e);
    return { success: false, message };
  }
}

export async function updateSkill(
  skillName: string,
  payload: { description: string; category: string; content: string },
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const result = await resp.json();
    if (!resp.ok || !result.success) {
      const err =
        typeof result.error === "string"
          ? result.error
          : `保存失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "保存成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "保存失败";
    console.error("更新技能失败:", e);
    return { success: false, message };
  }
}

export async function toggleSkillEnabled(
  skillName: string,
  enabled: boolean,
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/enabled`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `更新启用状态失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "更新成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "更新启用状态失败";
    console.error("更新启用状态失败:", e);
    return { success: false, message };
  }
}

export async function deleteSkill(
  skillName: string,
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}`,
      {
        method: "DELETE",
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `删除技能失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "删除成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "删除技能失败";
    console.error("删除技能失败:", e);
    return { success: false, message };
  }
}

export async function listSkillFiles(
  skillName: string,
): Promise<{ success: boolean; files?: SkillPathEntry[]; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/files`,
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `获取技能文件失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    const data = isRecord(payload.data) ? payload.data : null;
    const files = data && Array.isArray(data.files) ? data.files : [];
    return {
      success: true,
      message: "ok",
      files: files as SkillPathEntry[],
    };
  } catch (e) {
    const message = e instanceof Error ? e.message : "获取技能文件失败";
    console.error("获取技能文件失败:", e);
    return { success: false, message };
  }
}

export async function getSkillFileContent(
  skillName: string,
  path: string,
): Promise<{ success: boolean; file?: SkillFileContent; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/files/content?path=${encodeURIComponent(path)}`,
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `读取技能文件失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    const data = isRecord(payload.data) ? payload.data : null;
    if (!data) {
      throw new Error("技能文件响应格式错误");
    }
    return {
      success: true,
      message: "ok",
      file: data as unknown as SkillFileContent,
    };
  } catch (e) {
    const message = e instanceof Error ? e.message : "读取技能文件失败";
    console.error("读取技能文件失败:", e);
    return { success: false, message };
  }
}

export async function saveSkillFileContent(
  skillName: string,
  path: string,
  content: string,
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/files/content`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, content }),
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `保存技能文件失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "保存成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "保存技能文件失败";
    console.error("保存技能文件失败:", e);
    return { success: false, message };
  }
}

export async function uploadSkillAttachment(
  skillName: string,
  file: File,
  dirPath = "",
  overwrite = false,
): Promise<{ success: boolean; message: string }> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("dir_path", dirPath);
    formData.append("overwrite", String(overwrite));

    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/files/upload`,
      {
        method: "POST",
        body: formData,
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `上传附件失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "上传成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "上传附件失败";
    console.error("上传技能附件失败:", e);
    return { success: false, message };
  }
}

export async function createSkillDir(
  skillName: string,
  path: string,
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/directories`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `创建目录失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "创建成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "创建目录失败";
    console.error("创建技能目录失败:", e);
    return { success: false, message };
  }
}

export async function deleteSkillPath(
  skillName: string,
  path: string,
): Promise<{ success: boolean; message: string }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/paths`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      },
    );
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      const err =
        typeof payload.error === "string"
          ? payload.error
          : `删除路径失败（HTTP ${resp.status}）`;
      throw new Error(err);
    }
    return { success: true, message: "删除成功" };
  } catch (e) {
    const message = e instanceof Error ? e.message : "删除路径失败";
    console.error("删除技能路径失败:", e);
    return { success: false, message };
  }
}

export async function downloadSkillBundle(
  skillName: string,
): Promise<{ success: boolean; message: string; filename?: string; blob?: Blob }> {
  try {
    const resp = await fetch(
      `/api/skills/markdown/${encodeURIComponent(skillName)}/bundle`,
    );
    if (!resp.ok) {
      throw new Error(`下载失败（HTTP ${resp.status}）`);
    }
    const blob = await resp.blob();
    const contentDisposition = resp.headers.get("Content-Disposition") || "";
    const filenameMatch = contentDisposition.match(/filename=\"(.+?)\"/i);
    const filename = filenameMatch?.[1] || `${skillName}.zip`;
    return { success: true, message: "下载成功", filename, blob };
  } catch (e) {
    const message = e instanceof Error ? e.message : "下载技能包失败";
    console.error("下载技能包失败:", e);
    return { success: false, message };
  }
}

// ---- 能力相关 API ----

export async function fetchCapabilities(): Promise<CapabilityItem[]> {
  try {
    const resp = await fetch("/api/capabilities");
    const payload = await resp.json();
    if (!resp.ok || !payload.success) {
      throw new Error("获取能力列表失败");
    }
    const data = isRecord(payload.data) ? payload.data : null;
    const caps =
      data && Array.isArray(data.capabilities) ? data.capabilities : [];
    return caps as CapabilityItem[];
  } catch (e) {
    console.error("获取能力列表失败:", e);
    return [];
  }
}

// ---- 意图分析相关 API ----

export async function analyzeIntent(
  content: string,
): Promise<IntentAnalysisView | null> {
  const query = content.trim();
  if (!query) {
    return null;
  }

  try {
    const url = new URL("/api/intent/analyze", window.location.origin);
    url.searchParams.set("user_message", query);
    const resp = await fetch(url.toString(), { method: "POST" });
    const payload = await resp.json();
    if (!resp.ok || payload.success !== true) {
      throw new Error("意图分析失败");
    }
    const data = isRecord(payload.data) ? payload.data : null;
    return data as unknown as IntentAnalysisView;
  } catch (e) {
    console.error("获取意图分析失败:", e);
    return null;
  }
}

// ---- 记忆文件相关 API ----

export async function fetchMemoryFiles(
  sessionId: string,
): Promise<MemoryFile[]> {
  if (!sessionId) {
    return [];
  }
  try {
    const resp = await fetch(`/api/sessions/${sessionId}/memory-files`);
    const payload = await resp.json();
    const rawData = isRecord(payload.data) ? payload.data : null;
    const rawFiles: unknown[] = Array.isArray(payload.data)
      ? payload.data
      : rawData && Array.isArray(rawData.files)
        ? rawData.files
        : [];

    if (payload.success) {
      return rawFiles
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => {
          const name =
            typeof item.name === "string" ? item.name : "unknown";
          const size =
            typeof item.size === "number" && Number.isFinite(item.size)
              ? item.size
              : 0;
          const modifiedAt =
            typeof item.modified_at === "string" && item.modified_at.trim()
              ? item.modified_at
              : new Date().toISOString();
          const type: MemoryFile["type"] =
            name === "memory.jsonl"
              ? "memory"
              : name === "knowledge.md"
                ? "knowledge"
                : name.startsWith("archive/")
                  ? "archive"
                  : "meta";
          return {
            name,
            size,
            modified_at: modifiedAt,
            type,
          };
        });
    }
    return [];
  } catch (e) {
    console.error("获取记忆文件失败:", e);
    return [];
  }
}

// ---- 模型相关 API ----

export async function fetchActiveModel(): Promise<ActiveModelInfo | null> {
  try {
    const resp = await fetch("/api/models/active");
    const payload = await resp.json();
    if (payload.success && isRecord(payload.data)) {
      return payload.data as ActiveModelInfo;
    }
    return null;
  } catch (e) {
    console.error("获取活跃模型失败:", e);
    return null;
  }
}

export async function setPreferredProvider(
  providerId: string,
): Promise<ActiveModelInfo | null> {
  try {
    const resp = await fetch("/api/models/preferred", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId }),
    });
    const payload = await resp.json();
    if (payload.success && isRecord(payload.data)) {
      return payload.data as ActiveModelInfo;
    }
    return null;
  } catch (e) {
    console.error("设置首选模型失败:", e);
    return null;
  }
}

export async function setChatRoute(
  providerId: string,
  model: string | null,
): Promise<boolean> {
  try {
    const isBuiltin = providerId === "builtin";
    const body: Record<string, unknown> = isBuiltin
      ? {
          preferred_provider: null,
          purpose_routes: {
            chat: {
              provider_id: "builtin",
              model: model,
              base_url: null,
            },
            image_analysis: {
              provider_id: "builtin",
              model: model,
              base_url: null,
            },
            title_generation: {
              provider_id: "builtin",
              model: "title",
              base_url: null,
            },
          },
        }
      : {
          preferred_provider: providerId || null,
          purpose_routes: {
            chat: {
              provider_id: providerId || null,
              model: model,
              base_url: null,
            },
          },
        };
    const resp = await fetch("/api/models/routing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await resp.json();
    if (!payload.success) {
      console.error("设置 chat 路由失败:", payload.error);
    }
    return payload.success === true;
  } catch (e) {
    console.error("设置 chat 路由失败:", e);
    return false;
  }
}

export async function deleteProviderConfig(providerId: string): Promise<boolean> {
  try {
    const resp = await fetch(`/api/models/${providerId}/config`, {
      method: "DELETE",
    });
    const payload = await resp.json();
    if (!payload.success) {
      console.error("删除供应商配置失败:", payload.error);
    }
    return payload.success === true;
  } catch (e) {
    console.error("删除供应商配置失败:", e);
    return false;
  }
}

export async function fetchModelProviders(): Promise<ModelProviderInfo[]> {
  try {
    const resp = await fetch("/api/models");
    const data = await resp.json();
    if (data.success && Array.isArray(data.data)) {
      return data.data as ModelProviderInfo[];
    }
    return [];
  } catch (e) {
    console.error("获取模型提供商列表失败:", e);
    return [];
  }
}

// ---- 研究画像相关 API ----

export async function fetchResearchProfile(): Promise<ResearchProfile | null> {
  try {
    const resp = await fetch("/api/research-profile?profile_id=default");
    const payload = await resp.json();
    if (payload.success) {
      return payload.data as ResearchProfile;
    }
    return null;
  } catch (e) {
    console.error("获取研究画像失败:", e);
    return null;
  }
}

export async function updateResearchProfile(
  updates: Partial<ResearchProfile>,
): Promise<ResearchProfile | null> {
  try {
    const resp = await fetch("/api/research-profile?profile_id=default", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    const payload = await resp.json();
    if (payload.success) {
      return payload.data as ResearchProfile;
    }
    return null;
  } catch (e) {
    console.error("更新研究画像失败:", e);
    return null;
  }
}

// ---- 成本透明化相关 API ----

export async function fetchTokenUsage(
  sessionId: string,
): Promise<TokenUsage | null> {
  try {
    const resp = await fetch(`/api/cost/session/${sessionId}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    return data as TokenUsage;
  } catch (e) {
    console.error("获取 Token 使用统计失败:", e);
    return null;
  }
}

export async function fetchCostHistory(): Promise<{
  sessions: SessionCostSummary[];
  aggregate: AggregateCostSummary | null;
}> {
  try {
    const resp = await fetch("/api/cost/sessions");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    return {
      sessions: (data.sessions as SessionCostSummary[]) || [],
      aggregate: (data.aggregate as AggregateCostSummary) || null,
    };
  } catch (e) {
    console.error("获取成本历史失败:", e);
    return { sessions: [], aggregate: null };
  }
}

export async function fetchPricingConfig(): Promise<PricingConfig | null> {
  try {
    const resp = await fetch("/api/cost/pricing");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    return data as PricingConfig;
  } catch (e) {
    console.error("获取定价配置失败:", e);
    return null;
  }
}

// ---- Helper Functions for Message Processing ----

function stripReasoningMarkers(text: string): string {
  const REASONING_MARKER_PATTERN = /<\/?think>|<\/?thinking>|◁think▷|◁\/think▷/gi;
  if (!text) return text;
  return text.replace(REASONING_MARKER_PATTERN, "");
}

function parseToolArgs(argsRaw: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(argsRaw);
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function normalizeRunCodeIntent(
  name: string,
  args: Record<string, unknown>,
): Record<string, unknown> {
  if (name !== "run_code") return args;
  const code = typeof args.code === "string" ? args.code : "";
  const intent = typeof args.intent === "string" ? args.intent : "";
  if (intent) return args;
  // Infer intent from code comments
  const lines = code.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("#")) {
      const comment = trimmed.slice(1).trim();
      if (comment) {
        return { ...args, intent: comment };
      }
    }
  }
  return args;
}

function buildErrorMeta(content: string): {
  isError?: boolean;
  errorKind?: Message["errorKind"];
  errorHint?: string;
} {
  const errorPatterns: Array<{
    pattern: RegExp;
    kind: Message["errorKind"];
    hint: string;
  }> = [
    {
      pattern: /quota|额度|余额不足/i,
      kind: "quota",
      hint: "API 额度不足，请检查模型配置",
    },
    {
      pattern: /rate.?limit|请求过于频繁/i,
      kind: "rate_limit",
      hint: "请求过于频繁，请稍后再试",
    },
    {
      pattern: /context.?limit|token|上下文过长/i,
      kind: "context_limit",
      hint: "上下文过长，请尝试压缩会话或新建会话",
    },
  ];
  for (const { pattern, kind, hint } of errorPatterns) {
    if (pattern.test(content)) {
      return { isError: true, errorKind: kind, errorHint: hint };
    }
  }
  return { isError: true, errorKind: "unknown", errorHint: "发生错误，请重试" };
}

export function buildMessagesFromHistory(rawMessages: RawSessionMessage[]): Message[] {
  const messages: Message[] = [];
  const toolCallMap = new Map<
    string,
    { name?: string; input?: Record<string, unknown> }
  >();

  for (const raw of rawMessages) {
    const role = raw.role;
    const timestamp = normalizeMessageTimestamp(raw._ts);
    const turnId =
      typeof raw.turn_id === "string" && raw.turn_id.trim()
        ? raw.turn_id.trim()
        : undefined;
    const messageId =
      typeof raw.message_id === "string" && raw.message_id.trim()
        ? raw.message_id.trim()
        : undefined;
    const operation =
      raw.operation === "append" ||
      raw.operation === "replace" ||
      raw.operation === "complete"
        ? raw.operation
        : "complete";

    if (role === "user" && typeof raw.content === "string" && raw.content) {
      messages.push({
        id: nextId(),
        role: "user",
        content: raw.content,
        turnId,
        timestamp,
      });
      continue;
    }

    if (role === "assistant") {
      const eventType =
        typeof raw.event_type === "string" ? raw.event_type : "";
      if (eventType === "chart") {
        const nextMessages = upsertAssistantTextMessage(messages, {
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图表已生成",
          timestamp,
          messageId,
          turnId,
          operation,
          chartData: raw.chart_data,
        });
        messages.splice(0, messages.length, ...nextMessages);
        continue;
      }
      if (eventType === "data") {
        const nextMessages = upsertAssistantTextMessage(messages, {
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "数据预览如下",
          timestamp,
          messageId,
          turnId,
          operation,
          dataPreview: raw.data_preview,
        });
        messages.splice(0, messages.length, ...nextMessages);
        continue;
      }
      if (eventType === "artifact") {
        const nextMessages = upsertAssistantTextMessage(messages, {
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "产物已生成",
          timestamp,
          messageId,
          turnId,
          operation,
          artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : [],
        });
        messages.splice(0, messages.length, ...nextMessages);
        continue;
      }
      if (eventType === "image") {
        const nextMessages = upsertAssistantTextMessage(messages, {
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图片已生成",
          timestamp,
          messageId,
          turnId,
          operation,
          images: Array.isArray(raw.images) ? raw.images : [],
        });
        messages.splice(0, messages.length, ...nextMessages);
        continue;
      }
      if (eventType === "reasoning") {
        const reasoningLive =
          typeof raw.reasoning_live === "boolean"
            ? raw.reasoning_live
            : typeof raw.reasoningLive === "boolean"
              ? raw.reasoningLive
              : false;
        const nextMessages = upsertReasoningMessage(messages, {
          content: typeof raw.content === "string" ? raw.content : "",
          reasoningLive,
          reasoningId:
            typeof raw.reasoning_id === "string" ? raw.reasoning_id : undefined,
          turnId,
          timestamp,
        });
        messages.splice(0, messages.length, ...nextMessages);
        continue;
      }

      if (typeof raw.content === "string" && raw.content) {
        const cleanedContent = stripReasoningMarkers(raw.content);
        if (!cleanedContent.trim()) {
          continue;
        }
        const isErrorText = /^错误[:：]\s*/u.test(cleanedContent);
        const nextMessages = upsertAssistantTextMessage(messages, {
          content: cleanedContent,
          timestamp,
          messageId,
          turnId,
          operation,
          errorMeta: isErrorText ? buildErrorMeta(cleanedContent) : undefined,
        });
        messages.splice(0, messages.length, ...nextMessages);
      }

      const toolCalls = Array.isArray(raw.tool_calls) ? raw.tool_calls : [];
      for (const tc of toolCalls) {
        const name = tc.function?.name || "工具调用";
        const argsRaw = tc.function?.arguments || "";
        const toolArgs = normalizeRunCodeIntent(name, parseToolArgs(argsRaw));
        const toolCallId = tc.id;
        const toolIntent =
          name === "run_code" && typeof toolArgs.intent === "string"
            ? toolArgs.intent
            : undefined;
        const nextMessages = upsertToolCallMessage(messages, {
          content: toolIntent
            ? `🔧 ${name}: ${toolIntent}`
            : `调用工具: **${name}**`,
          toolName: name,
          toolCallId: toolCallId || undefined,
          toolInput: toolArgs,
          toolIntent,
          turnId,
          timestamp,
        });
        messages.splice(0, messages.length, ...nextMessages);
        if (toolCallId) {
          toolCallMap.set(toolCallId, { name, input: toolArgs });
        }
      }
      continue;
    }

    if (role === "tool") {
      const toolCallId =
        typeof raw.tool_call_id === "string" ? raw.tool_call_id : undefined;
      const normalized = normalizeToolResult(raw.content);
      const meta = toolCallId ? toolCallMap.get(toolCallId) : undefined;
      const nextMessages = upsertToolResultMessage(messages, {
        content: normalized.message,
        toolName:
          typeof raw.tool_name === "string" && raw.tool_name
            ? raw.tool_name
            : meta?.name,
        toolInput: meta?.input,
        toolCallId,
        toolResult: normalized.message,
        toolStatus:
          raw.status === "error" || normalized.status === "error"
            ? "error"
            : "success",
        toolIntent:
          typeof raw.intent === "string" ? raw.intent : undefined,
        turnId,
        timestamp,
      });
      messages.splice(0, messages.length, ...nextMessages);
    }
  }

  return messages;
}

function taskActivityByStatus(status: AnalysisTaskItem["status"]): string | null {
  switch (status) {
    case "done":
      return null;
    case "failed":
      return "步骤执行失败";
    case "blocked":
      return "步骤已阻塞";
    case "in_progress":
      return "步骤执行中";
    default:
      return "等待执行";
  }
}

function parseTaskPlannerPayload(
  rawArguments: string | undefined,
): { mode: string; tasks: Array<Record<string, unknown>> } | null {
  if (typeof rawArguments !== "string" || !rawArguments.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(rawArguments);
    if (!isRecord(parsed) || !Array.isArray(parsed.tasks)) {
      return null;
    }
    const rawMode =
      typeof parsed.mode === "string" && parsed.mode.trim()
        ? parsed.mode.trim()
        : typeof parsed.operation === "string" && parsed.operation.trim()
          ? parsed.operation.trim()
          : "init";
    return {
      mode: rawMode,
      tasks: parsed.tasks.filter((item): item is Record<string, unknown> => isRecord(item)),
    };
  } catch {
    return null;
  }
}

function buildTaskItem(
  rawTask: Record<string, unknown>,
  options: {
    turnId: string | null;
    createdAt: number;
    seed: string;
  },
): AnalysisTaskItem | null {
  const { turnId, createdAt, seed } = options;
  const rawId = rawTask.id;
  const planStepId =
    typeof rawId === "number" && Number.isFinite(rawId) && rawId > 0
      ? Math.floor(rawId)
      : null;
  if (!planStepId) return null;

  const title =
    typeof rawTask.title === "string" && rawTask.title.trim()
      ? rawTask.title.trim()
      : `步骤 ${planStepId}`;
  const statusRaw =
    typeof rawTask.status === "string" && rawTask.status.trim()
      ? rawTask.status.trim()
      : "pending";
  const status = normalizePlanStepStatus(statusRaw);
  const toolHint =
    typeof rawTask.tool_hint === "string" && rawTask.tool_hint.trim()
      ? rawTask.tool_hint.trim()
      : null;
  const actionId =
    typeof rawTask.action_id === "string" && rawTask.action_id.trim()
      ? rawTask.action_id.trim()
      : null;

  return {
    id: `restored-task-${seed}-${planStepId}`,
    plan_step_id: planStepId,
    action_id: actionId,
    title,
    tool_hint: toolHint,
    status,
    raw_status: statusRaw,
    current_activity: taskActivityByStatus(status),
    last_error: status === "failed" ? "历史任务执行失败" : null,
    attempts: [],
    created_at: createdAt,
    updated_at: createdAt,
    turn_id: turnId,
  };
}

function toPlanStep(task: AnalysisTaskItem): AnalysisStep {
  return {
    id: task.plan_step_id,
    title: task.title,
    tool_hint: task.tool_hint,
    status: task.status,
    raw_status: task.raw_status,
    action_id: task.action_id,
  };
}

function isPlanTerminal(steps: AnalysisStep[]): boolean {
  return steps.every((step) => step.status === "done" || step.status === "skipped");
}

export function buildSessionRestoreState(
  rawMessages: RawSessionMessage[],
): RestoredSessionState {
  const messages = buildMessagesFromHistory(rawMessages);
  const plans = new Map<
    string,
    {
      turnId: string | null;
      seed: string;
      createdAt: number;
      updatedAt: number;
      tasks: Map<number, AnalysisTaskItem>;
    }
  >();
  let unnamedPlanCounter = 0;

  for (const raw of rawMessages) {
    if (!Array.isArray(raw.tool_calls) || raw.tool_calls.length === 0) {
      continue;
    }
    const createdAt = normalizeMessageTimestamp(raw._ts);
    const turnId =
      typeof raw.turn_id === "string" && raw.turn_id.trim()
        ? raw.turn_id.trim()
        : null;
    const planKey = turnId ?? `turnless-${++unnamedPlanCounter}`;

    for (const toolCall of raw.tool_calls) {
      const func = isRecord(toolCall.function) ? toolCall.function : null;
      if (
        !func ||
        (func.name !== "task_write" && func.name !== "task_state")
      ) {
        continue;
      }
      const payload = parseTaskPlannerPayload(
        typeof func.arguments === "string" ? func.arguments : undefined,
      );
      if (!payload) {
        continue;
      }

      const currentPlan = plans.get(planKey);
      const seed = turnId ?? planKey;
      const nextPlan =
        payload.mode === "init" || !currentPlan
          ? {
              turnId,
              seed,
              createdAt,
              updatedAt: createdAt,
              tasks: new Map<number, AnalysisTaskItem>(),
            }
          : currentPlan;

      if (payload.mode === "init") {
        nextPlan.tasks.clear();
      }

      for (const rawTask of payload.tasks) {
        const nextTask = buildTaskItem(rawTask, {
          turnId,
          createdAt,
          seed,
        });
        if (!nextTask) continue;

        const existing = nextPlan.tasks.get(nextTask.plan_step_id);
        const hasExplicitTitle =
          typeof rawTask.title === "string" && rawTask.title.trim().length > 0;
        const hasExplicitToolHint =
          typeof rawTask.tool_hint === "string" && rawTask.tool_hint.trim().length > 0;
        const hasExplicitActionId =
          typeof rawTask.action_id === "string" && rawTask.action_id.trim().length > 0;
        nextPlan.tasks.set(nextTask.plan_step_id, {
          ...(existing ?? nextTask),
          ...nextTask,
          title:
            hasExplicitTitle || !existing
              ? nextTask.title
              : existing.title,
          tool_hint:
            hasExplicitToolHint || !existing
              ? nextTask.tool_hint
              : existing.tool_hint,
          action_id:
            hasExplicitActionId || !existing
              ? nextTask.action_id
              : existing.action_id,
          attempts: existing?.attempts ?? [],
          created_at: existing?.created_at ?? nextTask.created_at,
          updated_at: createdAt,
          last_error:
            nextTask.status === "failed"
              ? existing?.last_error ?? "历史任务执行失败"
              : nextTask.status === "done"
                ? null
                : existing?.last_error ?? null,
        });
      }

      nextPlan.updatedAt = createdAt;
      plans.set(planKey, nextPlan);
    }
  }

  const sortedPlans = [...plans.values()].sort((a, b) => a.createdAt - b.createdAt);
  const analysisTasks = sortedPlans.flatMap((plan) =>
    [...plan.tasks.values()].sort((a, b) => a.plan_step_id - b.plan_step_id),
  );

  const latestPlan = sortedPlans[sortedPlans.length - 1];
  const latestSteps = latestPlan
    ? [...latestPlan.tasks.values()]
        .sort((a, b) => a.plan_step_id - b.plan_step_id)
        .map(toPlanStep)
    : [];
  const analysisPlanProgress =
    latestSteps.length > 0 && !isPlanTerminal(latestSteps)
      ? makePlanProgressFromSteps(latestSteps, "")
      : null;

  return {
    messages,
    analysisTasks,
    analysisPlanProgress,
  };
}
