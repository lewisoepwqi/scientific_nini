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
} from "./types";

import { isRecord, nextId } from "./utils";

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
    const body: Record<string, unknown> = {
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

function normalizeToolResult(content: unknown): {
  message: string;
  status: "success" | "error";
} {
  if (typeof content === "string") {
    const isError =
      content.startsWith("错误:") ||
      content.startsWith("Error:") ||
      content.toLowerCase().includes("exception");
    return { message: content, status: isError ? "error" : "success" };
  }
  if (content === null || content === undefined) {
    return { message: "", status: "success" };
  }
  return { message: JSON.stringify(content), status: "success" };
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

// 辅助函数：从原始消息中提取时间戳（毫秒）
function getRawMessageTimestamp(raw: RawSessionMessage): number {
  if (raw._ts && typeof raw._ts === "string") {
    const parsed = Date.parse(raw._ts);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return Date.now();
}

export function buildMessagesFromHistory(rawMessages: RawSessionMessage[]): Message[] {
  const messages: Message[] = [];
  const toolCallMap = new Map<
    string,
    { name?: string; input?: Record<string, unknown> }
  >();

  for (const raw of rawMessages) {
    const role = raw.role;
    // 使用原始时间戳，确保消息按正确顺序展示
    const timestamp = getRawMessageTimestamp(raw);

    if (role === "user" && typeof raw.content === "string" && raw.content) {
      messages.push({
        id: nextId(),
        role: "user",
        content: raw.content,
        timestamp,
      });
      continue;
    }

    if (role === "assistant") {
      const eventType =
        typeof raw.event_type === "string" ? raw.event_type : "";
      if (eventType === "chart") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图表已生成",
          chartData: raw.chart_data,
          timestamp,
        });
        continue;
      }
      if (eventType === "data") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "数据预览如下",
          dataPreview: raw.data_preview,
          timestamp,
        });
        continue;
      }
      if (eventType === "artifact") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "产物已生成",
          artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : [],
          timestamp,
        });
        continue;
      }
      if (eventType === "image") {
        messages.push({
          id: nextId(),
          role: "assistant",
          content:
            typeof raw.content === "string" && raw.content
              ? raw.content
              : "图片已生成",
          images: Array.isArray(raw.images) ? raw.images : [],
          timestamp,
        });
        continue;
      }

      if (typeof raw.content === "string" && raw.content) {
        const cleanedContent = stripReasoningMarkers(raw.content);
        if (!cleanedContent.trim()) {
          continue;
        }
        const isErrorText = /^错误[:：]\s*/u.test(cleanedContent);
        messages.push({
          id: nextId(),
          role: "assistant",
          content: cleanedContent,
          ...(isErrorText ? buildErrorMeta(cleanedContent) : {}),
          timestamp,
        });
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
        const msg: Message = {
          id: nextId(),
          role: "tool",
          content: toolIntent
            ? `🔧 ${name}: ${toolIntent}`
            : `调用工具: **${name}**`,
          toolName: name,
          toolCallId: toolCallId || undefined,
          toolInput: toolArgs,
          toolIntent,
          timestamp,
        };
        messages.push(msg);
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
      const existingIndex = toolCallId
        ? messages.findIndex(
            (m) =>
              m.role === "tool" && m.toolCallId === toolCallId && !m.toolResult,
          )
        : -1;

      if (existingIndex >= 0) {
        messages[existingIndex] = {
          ...messages[existingIndex],
          toolResult: normalized.message,
          toolStatus: normalized.status,
        };
      } else {
        const meta = toolCallId ? toolCallMap.get(toolCallId) : undefined;
        messages.push({
          id: nextId(),
          role: "tool",
          content: normalized.message,
          toolName: meta?.name,
          toolCallId: toolCallId,
          toolInput: meta?.input,
          toolResult: normalized.message,
          toolStatus: normalized.status,
          timestamp,
        });
      }
    }
  }

  return messages;
}
