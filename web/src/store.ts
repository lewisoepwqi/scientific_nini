/**
 * 单一 Zustand Store —— 管理会话、消息、WebSocket 连接。
 */
import { create } from 'zustand'

// ---- 类型 ----

export interface ArtifactInfo {
  name: string
  type: string
  format?: string
  download_url: string
}

export interface RetrievalItem {
  source: string
  score?: number
  hits?: number
  snippet: string
}

export interface SkillItem {
  type: 'function' | 'markdown' | string
  name: string
  description: string
  location: string
  enabled: boolean
  metadata?: Record<string, unknown>
}

export interface DatasetItem {
  id: string
  name: string
  file_type: string
  file_size: number
  row_count: number
  column_count: number
  created_at?: string
  loaded: boolean
}

export interface WorkspaceFile {
  id: string
  name: string
  kind: 'dataset' | 'artifact' | 'note'
  size: number
  created_at?: string
  download_url: string
  meta?: Record<string, unknown>
  folder?: string | null
}

export interface WorkspaceFolder {
  id: string
  name: string
  parent: string | null
  created_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  toolName?: string
  toolCallId?: string
  toolInput?: Record<string, unknown> // 工具调用参数
  toolResult?: string // 工具执行结果
  toolStatus?: 'success' | 'error' // 工具执行状态
  chartData?: unknown
  dataPreview?: unknown
  artifacts?: ArtifactInfo[]
  images?: string[] // 图片 URL 列表
  retrievals?: RetrievalItem[] // 检索命中结果
  turnId?: string // Agent 回合 ID，用于消息分组
  timestamp: number
}

export interface SessionItem {
  id: string
  title: string
  message_count: number
  source: 'memory' | 'disk'
}

export interface ActiveModelInfo {
  provider_id: string
  provider_name: string
  model: string
  preferred_provider: string | null
}

export interface CodeExecution {
  id: string
  session_id: string
  code: string
  output: string
  status: string
  language: string
  created_at: string
}

interface WSEvent {
  type: string
  data?: unknown
  session_id?: string
  tool_call_id?: string
  tool_name?: string
  turn_id?: string
}

interface RawSessionMessage {
  role?: string
  content?: string | null
  event_type?: string | null
  tool_calls?: Array<{
    id?: string
    type?: string
    function?: {
      name?: string
      arguments?: string
    }
  }>
  tool_call_id?: string | null
  chart_data?: unknown
  data_preview?: unknown
  artifacts?: ArtifactInfo[]
  images?: string[]
}

interface AppState {
  // 会话
  sessionId: string | null
  messages: Message[]
  sessions: SessionItem[]
  datasets: DatasetItem[]
  workspaceFiles: WorkspaceFile[]
  skills: SkillItem[]

  // 模型选择（统一为全局首选）
  activeModel: ActiveModelInfo | null

  // 工作区面板状态
  workspacePanelOpen: boolean
  workspacePanelTab: 'files' | 'executions'
  fileSearchQuery: string
  previewTabs: string[]
  previewFileId: string | null
  codeExecutions: CodeExecution[]
  workspaceFolders: WorkspaceFolder[]
  isUploading: boolean
  uploadProgress: number
  uploadingFileName: string | null

  // 连接
  ws: WebSocket | null
  wsConnected: boolean
  isStreaming: boolean

  // 当前流式文本的累积
  _streamingText: string
  _currentTurnId: string | null
  _reconnectAttempts: number

  // 操作
  connect: () => void
  disconnect: () => void
  initApp: () => Promise<void>
  sendMessage: (content: string) => void
  stopStreaming: () => void
  retryLastTurn: () => void
  uploadFile: (file: File) => Promise<void>
  clearMessages: () => void
  fetchSessions: () => Promise<void>
  fetchDatasets: () => Promise<void>
  fetchWorkspaceFiles: () => Promise<void>
  fetchSkills: () => Promise<void>
  loadDataset: (datasetId: string) => Promise<void>
  compressCurrentSession: () => Promise<{ success: boolean; message: string }>
  createNewSession: () => Promise<void>
  switchSession: (sessionId: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>
  fetchActiveModel: () => Promise<void>
  setPreferredProvider: (providerId: string) => Promise<void>

  // 工作区面板操作
  toggleWorkspacePanel: () => void
  setWorkspacePanelTab: (tab: 'files' | 'executions') => void
  setFileSearchQuery: (query: string) => void
  deleteWorkspaceFile: (fileId: string) => Promise<void>
  renameWorkspaceFile: (fileId: string, newName: string) => Promise<void>
  openPreview: (fileId: string) => void
  setActivePreview: (fileId: string | null) => void
  closePreview: (fileId?: string) => void
  fetchCodeExecutions: () => Promise<void>
  fetchFolders: () => Promise<void>
  createFolder: (name: string, parent?: string | null) => Promise<void>
  moveFileToFolder: (fileId: string, folderId: string | null) => Promise<void>
  createWorkspaceFile: (filename: string, content?: string) => Promise<void>
}

// ---- 工具函数 ----

let msgCounter = 0
function nextId(): string {
  return `msg-${Date.now()}-${++msgCounter}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = window.location.host
  return `${proto}://${host}/ws`
}

function uploadWithProgress(
  form: FormData,
  onProgress: (percent: number) => void,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/upload')
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
      onProgress(percent)
    }

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(`上传失败: HTTP ${xhr.status}`))
        return
      }
      const jsonResp = xhr.response
      if (jsonResp && typeof jsonResp === 'object') {
        resolve(jsonResp as Record<string, unknown>)
        return
      }
      try {
        const parsed = JSON.parse(xhr.responseText) as Record<string, unknown>
        resolve(parsed)
      } catch {
        reject(new Error('上传响应解析失败'))
      }
    }

    xhr.onerror = () => reject(new Error('上传请求失败'))
    xhr.send(form)
  })
}

// ---- Store ----

export const useStore = create<AppState>((set, get) => ({
  sessionId: null,
  messages: [],
  sessions: [],
  datasets: [],
  workspaceFiles: [],
  skills: [],
  activeModel: null,
  workspacePanelOpen: false,
  workspacePanelTab: 'files',
  fileSearchQuery: '',
  previewTabs: [],
  previewFileId: null,
  codeExecutions: [],
  workspaceFolders: [],
  isUploading: false,
  uploadProgress: 0,
  uploadingFileName: null,
  ws: null,
  wsConnected: false,
  isStreaming: false,
  _streamingText: '',
  _currentTurnId: null,
  _reconnectAttempts: 0,

  connect() {
    const existing = get().ws
    if (existing && existing.readyState === WebSocket.OPEN) return
    if (existing && existing.readyState === WebSocket.CONNECTING) return

    // 页面不可见时不主动连接
    if (document.hidden) return

    const ws = new WebSocket(getWsUrl())

    ws.onopen = () => {
      set({ wsConnected: true, _reconnectAttempts: 0 })
      // 启动心跳检测 - 15秒间隔，保持连接活跃
      const pingInterval = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        } else {
          window.clearInterval(pingInterval)
        }
      }, 15000)
      ;(ws as WebSocket & { _pingInterval?: number })._pingInterval = pingInterval
    }

    ws.onclose = () => {
      const pingInterval = (ws as WebSocket & { _pingInterval?: number })._pingInterval
      if (pingInterval) clearInterval(pingInterval)

      const state = get()
      const attempts = (state as unknown as Record<string, number>)._reconnectAttempts || 0
      const maxAttempts = 10

      set({
        ws: null,
        wsConnected: false,
        isStreaming: false,
        _streamingText: '',
        _currentTurnId: null,
      })

      // 指数退避重连：1s, 2s, 4s, 8s, 16s, 30s(max)
      if (attempts < maxAttempts && !document.hidden) {
        const delay = Math.min(1000 * Math.pow(2, attempts), 30000)
        set({ _reconnectAttempts: attempts + 1 } as Partial<AppState>)
        setTimeout(() => get().connect(), delay)
      }
    }

    ws.onerror = () => {
      // onclose 会紧随触发
    }

    ws.onmessage = (event) => {
      try {
        const evt: WSEvent = JSON.parse(event.data)
        // 忽略 pong 消息
        if (evt.type === 'pong') return
        handleEvent(evt, set, get)
      } catch {
        // 忽略非法消息
      }
    }

    set({ ws })
  },

  disconnect() {
    const ws = get().ws
    if (ws) {
      // 清除心跳
      const pingInterval = (ws as WebSocket & { _pingInterval?: number })._pingInterval
      if (pingInterval) window.clearInterval(pingInterval)
      // 避免触发自动重连
      ws.onclose = null
      ws.close()
    }
    set({
      ws: null,
      wsConnected: false,
      _reconnectAttempts: 0,
      isStreaming: false,
      _streamingText: '',
    })
  },

  async initApp() {
    // 1. 获取会话列表
    await get().fetchSessions()
    await get().fetchSkills()
    
    // 2. 尝试恢复上次使用的会话
    const savedSessionId = localStorage.getItem('nini_last_session_id')
    const { sessions } = get()
    
    if (savedSessionId) {
      // 检查保存的会话是否仍存在
      const sessionExists = sessions.some(s => s.id === savedSessionId)
      if (sessionExists) {
        await get().switchSession(savedSessionId)
        return
      }
    }
    
    // 3. 如果没有保存的会话或会话已不存在，自动切换到最近的会话（如果有）
    if (sessions.length > 0) {
      // sessions 已按时间倒序排列，第一个是最新的
      await get().switchSession(sessions[0].id)
    }
    // 4. 如果没有现有会话，保持空状态，等待用户点击"新建会话"
  },

  sendMessage(content: string) {
    const { ws, sessionId } = get()
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    // 添加用户消息
    const userMsg: Message = {
      id: nextId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    set((s) => ({ messages: [...s.messages, userMsg] }))

    // 发送到服务器
    ws.send(JSON.stringify({
      type: 'chat',
      content,
      session_id: sessionId,
    }))

    set({ isStreaming: true, _streamingText: '' })
  },

  stopStreaming() {
    const { ws, isStreaming, sessionId } = get()
    if (!isStreaming) return

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: 'stop',
          session_id: sessionId,
        }),
      )
    }

    // 立即停止前端流式状态，避免继续渲染后续 token
    set({ isStreaming: false, _streamingText: '', _currentTurnId: null })
  },

  retryLastTurn() {
    const { ws, sessionId, messages, isStreaming } = get()
    if (isStreaming) return
    if (!sessionId || !ws || ws.readyState !== WebSocket.OPEN) return

    let lastUserIndex = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUserIndex = i
        break
      }
    }
    if (lastUserIndex < 0) return

    const retryContent = messages[lastUserIndex].content.trim()
    if (!retryContent) return

    // 清空最后一条用户消息之后的 Agent 输出
    const trimmedMessages = messages.slice(0, lastUserIndex + 1)
    set({
      messages: trimmedMessages,
      isStreaming: true,
      _streamingText: '',
      _currentTurnId: null,
    })

    ws.send(
      JSON.stringify({
        type: 'retry',
        session_id: sessionId,
        content: retryContent,
      }),
    )
  },

  async uploadFile(file: File) {
    let { sessionId } = get()
    if (!sessionId) {
      try {
        const resp = await fetch('/api/sessions', { method: 'POST' })
        const payload = await resp.json()
        const data = isRecord(payload) ? payload.data : null
        const createdSessionId = isRecord(data) ? data.session_id : null
        if (typeof createdSessionId !== 'string' || !createdSessionId) {
          throw new Error('会话创建失败')
        }
        sessionId = createdSessionId
        set({ sessionId })
        localStorage.setItem('nini_last_session_id', createdSessionId)
      } catch {
        const errMsg: Message = {
          id: nextId(),
          role: 'assistant',
          content: '错误: 自动创建会话失败，请先发送一条消息后重试上传。',
          timestamp: Date.now(),
        }
        set((s) => ({ messages: [...s.messages, errMsg] }))
        return
      }
    }

    const form = new FormData()
    form.append('file', file)
    form.append('session_id', sessionId)

    set({
      isUploading: true,
      uploadProgress: 0,
      uploadingFileName: file.name,
    })

    try {
      const payload = await uploadWithProgress(form, (percent) => {
        set({ uploadProgress: percent })
      })
      const success = payload.success === true
      const dataset = isRecord(payload.dataset) ? payload.dataset : null
      if (success && dataset) {
        const datasetName = typeof dataset.name === 'string' ? dataset.name : file.name
        const rowCount = typeof dataset.row_count === 'number' ? dataset.row_count : 0
        const columnCount = typeof dataset.column_count === 'number' ? dataset.column_count : 0
        // 通知用户上传成功
        const sysMsg: Message = {
          id: nextId(),
          role: 'assistant',
          content: `数据集 **${datasetName}** 已加载（${rowCount} 行 × ${columnCount} 列）`,
          timestamp: Date.now(),
        }
        set((s) => ({ messages: [...s.messages, sysMsg] }))
        await get().fetchDatasets()
        await get().fetchWorkspaceFiles()
      } else {
        throw new Error(typeof payload.error === 'string' ? payload.error : '上传失败')
      }
    } catch (e) {
      console.error('上传失败:', e)
      const err = e instanceof Error ? e.message : '上传失败'
      const errMsg: Message = {
        id: nextId(),
        role: 'assistant',
        content: `错误: ${err}`,
        timestamp: Date.now(),
      }
      set((s) => ({ messages: [...s.messages, errMsg] }))
    } finally {
      set({
        isUploading: false,
        uploadProgress: 0,
        uploadingFileName: null,
      })
    }
  },

  clearMessages() {
    set({
      messages: [],
      sessionId: null,
      datasets: [],
      workspaceFiles: [],
      previewTabs: [],
      previewFileId: null,
    })
  },

  async fetchSessions() {
    try {
      const resp = await fetch('/api/sessions')
      const payload = await resp.json()
      if (payload.success && Array.isArray(payload.data)) {
        set({ sessions: payload.data as SessionItem[] })
      }
    } catch (e) {
      console.error('获取会话列表失败:', e)
    }
  },

  async fetchDatasets() {
    const sid = get().sessionId
    if (!sid) {
      set({ datasets: [] })
      return
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/datasets`)
      const payload = await resp.json()
      const data = isRecord(payload.data) ? payload.data : null
      const datasets = data && Array.isArray(data.datasets) ? data.datasets : []
      set({ datasets: datasets as DatasetItem[] })
    } catch (e) {
      console.error('获取数据集列表失败:', e)
    }
  },

  async fetchWorkspaceFiles() {
    const sid = get().sessionId
    if (!sid) {
      set({ workspaceFiles: [] })
      return
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/files`)
      const payload = await resp.json()
      const data = isRecord(payload.data) ? payload.data : null
      const files = data && Array.isArray(data.files) ? data.files : []
      set({ workspaceFiles: files as WorkspaceFile[] })
    } catch (e) {
      console.error('获取工作空间文件失败:', e)
    }
  },

  async fetchSkills() {
    try {
      const resp = await fetch('/api/skills')
      const payload = await resp.json()
      const data = isRecord(payload.data) ? payload.data : null
      const skills = data && Array.isArray(data.skills) ? data.skills : []
      set({ skills: skills as SkillItem[] })
    } catch (e) {
      console.error('获取技能列表失败:', e)
    }
  },

  async loadDataset(datasetId: string) {
    const sid = get().sessionId
    if (!sid || !datasetId) return
    try {
      await fetch(`/api/sessions/${sid}/datasets/${datasetId}/load`, { method: 'POST' })
      await get().fetchDatasets()
    } catch (e) {
      console.error('加载数据集失败:', e)
    }
  },

  async compressCurrentSession() {
    const sid = get().sessionId
    if (!sid) {
      return { success: false, message: '请先选择会话' }
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/compress`, { method: 'POST' })
      const payload = await resp.json()
      if (!payload.success) {
        return {
          success: false,
          message: typeof payload.error === 'string' ? payload.error : '会话压缩失败',
        }
      }
      const data = isRecord(payload.data) ? payload.data : null
      const archivedCount = typeof data?.archived_count === 'number' ? data.archived_count : 0
      const remainingCount = typeof data?.remaining_count === 'number' ? data.remaining_count : 0
      const message = `会话压缩完成：归档 ${archivedCount} 条，剩余 ${remainingCount} 条`

      // 压缩成功后刷新当前消息列表
      await get().switchSession(sid)
      return { success: true, message }
    } catch (e) {
      console.error('压缩会话失败:', e)
      return { success: false, message: '压缩会话失败，请稍后重试' }
    }
  },

  async createNewSession() {
    try {
      const resp = await fetch('/api/sessions', { method: 'POST' })
      const payload = await resp.json()
      const data = isRecord(payload) ? payload.data : null
      const newSessionId = isRecord(data) ? data.session_id : null
      if (typeof newSessionId !== 'string' || !newSessionId) {
        throw new Error('会话创建失败')
      }
      // 切换到新会话，清空当前消息显示
      set({
        sessionId: newSessionId,
        messages: [],
        datasets: [],
        workspaceFiles: [],
        previewTabs: [],
        previewFileId: null,
        _streamingText: '',
        isStreaming: false,
      })
      // 清除保存的 session_id（新会话不需要恢复）
      localStorage.removeItem('nini_last_session_id')
      // 刷新会话列表
      await get().fetchSessions()
    } catch (e) {
      console.error('创建新会话失败:', e)
    }
  },

  async switchSession(targetSessionId: string) {
    const { sessionId } = get()
    if (targetSessionId === sessionId) return

    try {
      const resp = await fetch(`/api/sessions/${targetSessionId}/messages`)
      const payload = await resp.json()
      if (!payload.success) {
        // 会话存在但无消息，直接切换到空会话
        set({
          sessionId: targetSessionId,
          messages: [],
          previewTabs: [],
          previewFileId: null,
          _streamingText: '',
          isStreaming: false,
        })
        await get().fetchDatasets()
        await get().fetchWorkspaceFiles()
        return
      }

      const data = isRecord(payload.data) ? payload.data : null
      const rawMessages = isRecord(data) && Array.isArray(data.messages) ? data.messages : []

      // 将后端消息格式转换为前端 Message 格式（包含工具调用与结果）
      const messages = buildMessagesFromHistory(rawMessages as RawSessionMessage[])

      set({
        sessionId: targetSessionId,
        messages,
        previewTabs: [],
        previewFileId: null,
        _streamingText: '',
        isStreaming: false,
      })
      // 保存当前会话 ID 到 localStorage
      localStorage.setItem('nini_last_session_id', targetSessionId)
      await get().fetchDatasets()
      await get().fetchWorkspaceFiles()
      await get().fetchCodeExecutions()
      await get().fetchFolders()
    } catch (e) {
      console.error('切换会话失败:', e)
    }
  },

  async deleteSession(targetSessionId: string) {
    try {
      await fetch(`/api/sessions/${targetSessionId}`, { method: 'DELETE' })
      const { sessionId } = get()
      // 如果删除的是当前会话，清空状态
      if (targetSessionId === sessionId) {
        set({
          sessionId: null,
          messages: [],
          datasets: [],
          workspaceFiles: [],
          previewTabs: [],
          previewFileId: null,
          _streamingText: '',
          isStreaming: false,
        })
      }
      // 刷新会话列表
      await get().fetchSessions()
    } catch (e) {
      console.error('删除会话失败:', e)
    }
  },

  async updateSessionTitle(targetSessionId: string, title: string) {
    try {
      await fetch(`/api/sessions/${targetSessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      // 更新本地状态
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === targetSessionId ? { ...sess, title } : sess
        ),
      }))
    } catch (e) {
      console.error('更新会话标题失败:', e)
    }
  },

  async fetchActiveModel() {
    try {
      const resp = await fetch('/api/models/active')
      const payload = await resp.json()
      if (payload.success && isRecord(payload.data)) {
        set({ activeModel: payload.data as ActiveModelInfo })
      }
    } catch (e) {
      console.error('获取活跃模型失败:', e)
    }
  },

  async setPreferredProvider(providerId: string) {
    try {
      // 同时设为内存首选和持久化默认
      const resp = await fetch('/api/models/preferred', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId }),
      })
      const payload = await resp.json()
      if (payload.success && isRecord(payload.data)) {
        set({ activeModel: payload.data as ActiveModelInfo })
      }
    } catch (e) {
      console.error('设置首选模型失败:', e)
    }
  },

  toggleWorkspacePanel() {
    set((s) => ({ workspacePanelOpen: !s.workspacePanelOpen }))
  },

  setWorkspacePanelTab(tab: 'files' | 'executions') {
    set({ workspacePanelTab: tab })
  },

  setFileSearchQuery(query: string) {
    set({ fileSearchQuery: query })
  },

  async deleteWorkspaceFile(fileId: string) {
    const sid = get().sessionId
    if (!sid) return
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/files/${fileId}`, {
        method: 'DELETE',
      })
      const payload = await resp.json()
      if (payload.success) {
        await get().fetchWorkspaceFiles()
        await get().fetchDatasets()
      }
    } catch (e) {
      console.error('删除文件失败:', e)
    }
  },

  openPreview(fileId: string) {
    set((s) => {
      if (s.previewTabs.includes(fileId)) {
        return { previewFileId: fileId }
      }
      return {
        previewTabs: [...s.previewTabs, fileId],
        previewFileId: fileId,
      }
    })
  },

  setActivePreview(fileId: string | null) {
    set({ previewFileId: fileId })
  },

  closePreview(fileId?: string) {
    set((s) => {
      const target = fileId ?? s.previewFileId
      if (!target) return { previewFileId: null }
      const nextTabs = s.previewTabs.filter((id) => id !== target)
      if (nextTabs.length === 0) {
        return { previewTabs: [], previewFileId: null }
      }
      if (s.previewFileId !== target) {
        return { previewTabs: nextTabs }
      }
      return {
        previewTabs: nextTabs,
        previewFileId: nextTabs[nextTabs.length - 1],
      }
    })
  },

  async fetchCodeExecutions() {
    const sid = get().sessionId
    if (!sid) {
      set({ codeExecutions: [] })
      return
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/executions`)
      const payload = await resp.json()
      const data = isRecord(payload.data) ? payload.data : null
      const executions = data && Array.isArray(data.executions) ? data.executions : []
      set({ codeExecutions: executions as CodeExecution[] })
    } catch (e) {
      console.error('获取执行历史失败:', e)
    }
  },

  async renameWorkspaceFile(fileId: string, newName: string) {
    const sid = get().sessionId
    if (!sid || !newName.trim()) return
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/files/${fileId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      })
      const payload = await resp.json()
      if (payload.success) {
        await get().fetchWorkspaceFiles()
        await get().fetchDatasets()
      }
    } catch (e) {
      console.error('重命名文件失败:', e)
    }
  },

  async fetchFolders() {
    const sid = get().sessionId
    if (!sid) {
      set({ workspaceFolders: [] })
      return
    }
    try {
      const resp = await fetch(`/api/sessions/${sid}/workspace/folders`)
      const payload = await resp.json()
      const data = isRecord(payload.data) ? payload.data : null
      const folders = data && Array.isArray(data.folders) ? data.folders : []
      set({ workspaceFolders: folders as WorkspaceFolder[] })
    } catch (e) {
      console.error('获取文件夹失败:', e)
    }
  },

  async createFolder(name: string, parent?: string | null) {
    const sid = get().sessionId
    if (!sid || !name.trim()) return
    try {
      await fetch(`/api/sessions/${sid}/workspace/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, parent: parent ?? null }),
      })
      await get().fetchFolders()
    } catch (e) {
      console.error('创建文件夹失败:', e)
    }
  },

  async moveFileToFolder(fileId: string, folderId: string | null) {
    const sid = get().sessionId
    if (!sid) return
    try {
      await fetch(`/api/sessions/${sid}/workspace/files/${fileId}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: folderId }),
      })
      await get().fetchWorkspaceFiles()
    } catch (e) {
      console.error('移动文件失败:', e)
    }
  },

  async createWorkspaceFile(filename: string, content?: string) {
    const sid = get().sessionId
    if (!sid || !filename.trim()) return
    try {
      await fetch(`/api/sessions/${sid}/workspace/files`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, content: content ?? '' }),
      })
      await get().fetchWorkspaceFiles()
    } catch (e) {
      console.error('创建文件失败:', e)
    }
  },
}))

// ---- 页面可见性处理 ----
// 页面切出时断开连接，切回时重连
document.addEventListener('visibilitychange', () => {
  const store = useStore.getState()
  if (document.hidden) {
    // 页面隐藏时若在生成中则保留连接，避免中途断线
    if (!store.isStreaming) {
      store.disconnect()
    }
  } else {
    // 页面可见时重置重连计数并连接
    useStore.setState({ _reconnectAttempts: 0 } as Partial<AppState>)
    store.connect()
  }
})

function parseToolArgs(rawArgs: unknown): Record<string, unknown> {
  if (typeof rawArgs !== 'string' || !rawArgs.trim()) return {}
  try {
    const parsed = JSON.parse(rawArgs)
    return isRecord(parsed) ? parsed : { value: parsed }
  } catch {
    return { raw: rawArgs }
  }
}

function normalizeToolResult(rawContent: unknown): { message: string; status: 'success' | 'error' } {
  if (typeof rawContent !== 'string' || !rawContent.trim()) {
    return { message: '', status: 'success' }
  }
  try {
    const parsed = JSON.parse(rawContent)
    if (isRecord(parsed)) {
      if (typeof parsed.error === 'string' && parsed.error) {
        return { message: parsed.error, status: 'error' }
      }
      if (parsed.success === false) {
        const msg = typeof parsed.message === 'string' && parsed.message ? parsed.message : '工具执行失败'
        return { message: msg, status: 'error' }
      }
      if (typeof parsed.message === 'string' && parsed.message) {
        return { message: parsed.message, status: 'success' }
      }
    }
  } catch {
    // 保持原始文本
  }
  return { message: rawContent, status: 'success' }
}

function buildMessagesFromHistory(rawMessages: RawSessionMessage[]): Message[] {
  const messages: Message[] = []
  const toolCallMap = new Map<string, { name?: string; input?: Record<string, unknown> }>()
  let tsOffset = 0

  const nextTimestamp = () => Date.now() + tsOffset++

  for (const raw of rawMessages) {
    const role = raw.role
    if (role === 'user' && typeof raw.content === 'string' && raw.content) {
      messages.push({
        id: nextId(),
        role: 'user',
        content: raw.content,
        timestamp: nextTimestamp(),
      })
      continue
    }

    if (role === 'assistant') {
      const eventType = typeof raw.event_type === 'string' ? raw.event_type : ''
      if (eventType === 'chart') {
        messages.push({
          id: nextId(),
          role: 'assistant',
          content: typeof raw.content === 'string' && raw.content ? raw.content : '图表已生成',
          chartData: raw.chart_data,
          timestamp: nextTimestamp(),
        })
        continue
      }
      if (eventType === 'data') {
        messages.push({
          id: nextId(),
          role: 'assistant',
          content: typeof raw.content === 'string' && raw.content ? raw.content : '数据预览如下',
          dataPreview: raw.data_preview,
          timestamp: nextTimestamp(),
        })
        continue
      }
      if (eventType === 'artifact') {
        messages.push({
          id: nextId(),
          role: 'assistant',
          content: typeof raw.content === 'string' && raw.content ? raw.content : '产物已生成',
          artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : [],
          timestamp: nextTimestamp(),
        })
        continue
      }
      if (eventType === 'image') {
        messages.push({
          id: nextId(),
          role: 'assistant',
          content: typeof raw.content === 'string' && raw.content ? raw.content : '图片已生成',
          images: Array.isArray(raw.images) ? raw.images : [],
          timestamp: nextTimestamp(),
        })
        continue
      }

      if (typeof raw.content === 'string' && raw.content) {
        messages.push({
          id: nextId(),
          role: 'assistant',
          content: raw.content,
          timestamp: nextTimestamp(),
        })
      }

      const toolCalls = Array.isArray(raw.tool_calls) ? raw.tool_calls : []
      for (const tc of toolCalls) {
        const name = tc.function?.name || '工具调用'
        const argsRaw = tc.function?.arguments || ''
        const toolArgs = parseToolArgs(argsRaw)
        const toolCallId = tc.id
        const msg: Message = {
          id: nextId(),
          role: 'tool',
          content: `调用工具: **${name}**`,
          toolName: name,
          toolCallId: toolCallId || undefined,
          toolInput: toolArgs,
          timestamp: nextTimestamp(),
        }
        messages.push(msg)
        if (toolCallId) {
          toolCallMap.set(toolCallId, { name, input: toolArgs })
        }
      }
      continue
    }

    if (role === 'tool') {
      const toolCallId = typeof raw.tool_call_id === 'string' ? raw.tool_call_id : undefined
      const normalized = normalizeToolResult(raw.content)
      const existingIndex = toolCallId
        ? messages.findIndex((m) => m.role === 'tool' && m.toolCallId === toolCallId && !m.toolResult)
        : -1

      if (existingIndex >= 0) {
        messages[existingIndex] = {
          ...messages[existingIndex],
          toolResult: normalized.message,
          toolStatus: normalized.status,
        }
      } else {
        const meta = toolCallId ? toolCallMap.get(toolCallId) : undefined
        messages.push({
          id: nextId(),
          role: 'tool',
          content: normalized.message,
          toolName: meta?.name,
          toolCallId: toolCallId,
          toolInput: meta?.input,
          toolResult: normalized.message,
          toolStatus: normalized.status,
          timestamp: nextTimestamp(),
        })
      }
    }
  }

  return messages
}

// ---- 事件处理 ----

function handleEvent(
  evt: WSEvent,
  set: (fn: Partial<AppState> | ((s: AppState) => Partial<AppState>)) => void,
  get: () => AppState,
) {
  switch (evt.type) {
    case 'session': {
      const data = evt.data
      if (isRecord(data) && typeof data.session_id === 'string') {
        set({ sessionId: data.session_id })
        // 新会话创建后刷新会话列表
        get().fetchSessions()
        get().fetchDatasets()
        get().fetchWorkspaceFiles()
        get().fetchSkills()
      }
      break
    }

    case 'iteration_start': {
      // 新迭代开始：重置流式文本累积，记录 turnId
      set({ _streamingText: '', _currentTurnId: evt.turn_id || null })
      break
    }

    case 'text': {
      const text = evt.data as string
      const newStreamText = get()._streamingText + text
      const turnId = evt.turn_id || get()._currentTurnId || undefined

      set((s) => {
        // 更新或创建 assistant 消息（同一迭代内）
        const msgs = [...s.messages]
        const last = msgs[msgs.length - 1]
        if (
          last &&
          last.role === 'assistant' &&
          !last.toolName &&
          !last.retrievals &&
          last.turnId === turnId
        ) {
          msgs[msgs.length - 1] = { ...last, content: newStreamText }
        } else {
          msgs.push({
            id: nextId(),
            role: 'assistant',
            content: newStreamText,
            turnId,
            timestamp: Date.now(),
          })
        }
        return { messages: msgs, _streamingText: newStreamText }
      })
      break
    }

    case 'tool_call': {
      const data = evt.data as { name: string; arguments: string }
      const turnId = evt.turn_id || get()._currentTurnId || undefined
      let toolArgs: Record<string, unknown> = {}
      try {
        toolArgs = JSON.parse(data.arguments)
      } catch {
        toolArgs = { raw: data.arguments }
      }
      const msg: Message = {
        id: nextId(),
        role: 'tool',
        content: `调用工具: **${data.name}**`,
        toolName: data.name,
        toolCallId: evt.tool_call_id || undefined,
        toolInput: toolArgs,
        turnId,
        timestamp: Date.now(),
      }
      set((s) => ({ messages: [...s.messages, msg] }))
      break
    }

    case 'tool_result': {
      const data = evt.data as Record<string, unknown>
      const status = data.status as 'success' | 'error' || 'success'
      const resultMessage = data.message as string || (status === 'error' ? '工具执行失败' : '工具执行完成')
      const toolCallId = evt.tool_call_id
      const turnId = evt.turn_id || get()._currentTurnId || undefined

      set((s) => {
        const msgs = [...s.messages]
        // 查找是否有对应的 tool_call 消息
        const existingIndex = msgs.findIndex(
          (m) => m.role === 'tool' && m.toolCallId === toolCallId && !m.toolResult
        )

        if (existingIndex >= 0) {
          // 合并到现有消息
          msgs[existingIndex] = {
            ...msgs[existingIndex],
            toolResult: resultMessage,
            toolStatus: status,
          }
        } else {
          // 创建新的结果消息
          msgs.push({
            id: nextId(),
            role: 'tool',
            content: resultMessage,
            toolName: evt.tool_name || undefined,
            toolCallId: toolCallId || undefined,
            toolResult: resultMessage,
            toolStatus: status,
            turnId,
            timestamp: Date.now(),
          })
        }
        return { messages: msgs }
      })
      break
    }

    case 'retrieval': {
      const data = isRecord(evt.data) ? evt.data : null
      const query = data && typeof data.query === 'string' ? data.query : '检索结果'
      const rawResults = data && Array.isArray(data.results) ? data.results : []
      const retrievals: RetrievalItem[] = rawResults
        .filter((item): item is Record<string, unknown> => isRecord(item))
        .map((item) => ({
          source: typeof item.source === 'string' ? item.source : 'unknown',
          score: typeof item.score === 'number' ? item.score : undefined,
          hits: typeof item.hits === 'number' ? item.hits : undefined,
          snippet: typeof item.snippet === 'string' ? item.snippet : '',
        }))
      if (retrievals.length === 0) break

      const turnId = evt.turn_id || get()._currentTurnId || undefined
      const msg: Message = {
        id: nextId(),
        role: 'assistant',
        content: `检索上下文：${query}`,
        retrievals,
        turnId,
        timestamp: Date.now(),
      }
      set((s) => ({ messages: [...s.messages, msg] }))
      break
    }

    case 'chart': {
      const turnId = evt.turn_id || get()._currentTurnId || undefined
      const msg: Message = {
        id: nextId(),
        role: 'assistant',
        content: '图表已生成',
        chartData: evt.data,
        turnId,
        timestamp: Date.now(),
      }
      set((s) => ({ messages: [...s.messages, msg] }))
      break
    }

    case 'data': {
      const turnId = evt.turn_id || get()._currentTurnId || undefined
      const msg: Message = {
        id: nextId(),
        role: 'assistant',
        content: '数据预览如下',
        dataPreview: evt.data,
        turnId,
        timestamp: Date.now(),
      }
      set((s) => ({ messages: [...s.messages, msg] }))
      break
    }

    case 'artifact': {
      // 将产物附加到最近的 tool/assistant 消息上
      const artifact = evt.data as ArtifactInfo
      if (artifact && artifact.download_url) {
        set((s) => {
          const msgs = [...s.messages]
          // 找到最近的 tool 或 assistant 消息来附加 artifact
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'tool' || msgs[i].role === 'assistant') {
              const existing = msgs[i].artifacts || []
              msgs[i] = { ...msgs[i], artifacts: [...existing, artifact] }
              break
            }
          }
          return { messages: msgs }
        })
      }
      break
    }

    case 'image': {
      // 图片事件：将图片 URL 附加到最近的 assistant 消息，或创建新消息
      const imageData = evt.data as { url?: string; urls?: string[] }
      const urls: string[] = []
      if (imageData.url) urls.push(imageData.url)
      if (imageData.urls) urls.push(...imageData.urls)

      if (urls.length > 0) {
        set((s) => {
          const msgs = [...s.messages]
          // 尝试找到最近的 assistant 消息来附加图片
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant' && !msgs[i].toolName) {
              const existing = msgs[i].images || []
              msgs[i] = { ...msgs[i], images: [...existing, ...urls] }
              return { messages: msgs }
            }
          }
          // 如果没找到 assistant 消息，创建一个新消息
          msgs.push({
            id: nextId(),
            role: 'assistant',
            content: '图片已生成',
            images: urls,
            timestamp: Date.now(),
          })
          return { messages: msgs }
        })
      }
      break
    }

    case 'session_title': {
      const data = evt.data as { session_id: string; title: string }
      if (data && data.session_id && data.title) {
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === data.session_id ? { ...sess, title: data.title } : sess
          ),
        }))
      }
      break
    }

    case 'workspace_update': {
      // 工作区文件变更，刷新文件列表
      get().fetchWorkspaceFiles()
      get().fetchDatasets()
      break
    }

    case 'code_execution': {
      // 新的代码执行记录
      const execRecord = evt.data as CodeExecution
      if (execRecord && execRecord.id) {
        set((s) => ({
          codeExecutions: [execRecord, ...s.codeExecutions],
        }))
      }
      break
    }

    case 'done':
      set({ isStreaming: false, _streamingText: '', _currentTurnId: null })
      // 对话结束后刷新会话列表（更新消息计数）
      get().fetchSessions()
      break

    case 'stopped':
      set({ isStreaming: false, _streamingText: '', _currentTurnId: null })
      break

    case 'error': {
      const errMsg: Message = {
        id: nextId(),
        role: 'assistant',
        content: `错误: ${evt.data}`,
        timestamp: Date.now(),
      }
      set((s) => ({
        messages: [...s.messages, errMsg],
        isStreaming: false,
        _streamingText: '',
        _currentTurnId: null,
      }))
      break
    }
  }
}
