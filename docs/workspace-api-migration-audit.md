# 工作空间 API 新旧路由迁移审计

## 文档目的

- 说明前端当前仍依赖的旧版工作空间接口。
- 审计新版 `/api/workspace/{session_id}/...` 路由是否已具备替代能力。
- 为后续迁移提供阻塞点清单和最小迁移顺序。

记录时间：2026-02-28

---

## 审计结论

本轮迁移已经完成。

当前状态：

- 前端工作空间主链路已切换到新版 `/api/workspace/{session_id}/...`
- 旧版 `/api/sessions/{sid}/workspace...` 兼容接口已从后端移除
- 新版工作空间 API 已覆盖：
  - 文件列表与搜索
  - 文件树
  - 路径式读写
  - 路径式预览
  - 路径式重命名/删除
  - 执行历史
  - 文件夹列表与创建
  - 路径式移动
  - 路径式 ZIP 打包下载

数据集主链路也已切换到新版 `/api/datasets/{session_id}/...`，旧版 `/api/sessions/{session_id}/datasets...` 兼容接口已移除。

---

## 历史记录：旧版工作空间接口

以下接口是迁移前的旧版工作空间路径，现已下线：

1. `GET /api/sessions/{sid}/workspace/files`
   - 用途：获取平铺文件列表，支持搜索结果展示。
   - 前端依赖语义：
     - 返回平铺列表而不是树结构。
     - 每个条目带 `id`、`kind`、`download_url`、`folder`、`meta`。

2. `POST /api/sessions/{sid}/workspace/save_text`
   - 用途：保存文本笔记。
   - 前端依赖语义：
     - 自动写入工作空间索引。
     - 返回新文件记录。

3. `DELETE /api/sessions/{sid}/workspace/files/{file_id}`
   - 用途：按 `file_id` 删除文件。
   - 前端依赖语义：
     - 目标是工作空间索引中的文件记录，不是磁盘路径。

4. `PATCH /api/sessions/{sid}/workspace/files/{file_id}`
   - 用途：按 `file_id` 重命名。
   - 前端依赖语义：
     - 返回更新后的文件记录。
     - 数据集重命名后仍与会话内存保持一致。

5. `GET /api/sessions/{sid}/workspace/files/{file_id}/preview`
   - 用途：文件预览。
   - 前端依赖语义：
     - 支持文本、图片、HTML、PDF、Plotly JSON 等不同 `preview_type`。

6. `GET /api/sessions/{sid}/workspace/executions`
   - 用途：读取代码执行历史。

7. `POST /api/sessions/{sid}/workspace/folders`
   - 用途：创建自定义文件夹。

8. `GET /api/sessions/{sid}/workspace/folders`
   - 用途：列出自定义文件夹。

9. `POST /api/sessions/{sid}/workspace/files/{file_id}/move`
   - 用途：按 `file_id` 移动文件到目标文件夹。

10. `POST /api/sessions/{sid}/workspace/files`
    - 用途：创建文本文件。
    - 前端依赖语义：
      - 实际行为仍是“新建 note 并更新索引”。

11. `POST /api/sessions/{sid}/workspace/batch-download`
    - 用途：按 `file_id` 选择集打包下载。
    - 前端依赖语义：
      - 不是按路径打包。
      - 处理重名文件。

### 前端依赖过的协议细节

前端不是只依赖“有这个接口”，而是依赖这些接口背后的具体协议：

- 文件列表必须是平铺列表，而不是树结构。
- 文件主键统一使用 `WorkspaceFile.id`。
- 批量下载请求体使用的是 `file_ids`，不是路径列表。
- 文件列表条目必须包含：
  - `id`
  - `name`
  - `kind`
  - `size`
  - `download_url`
  - 可选 `created_at`
  - `folder`
  - `meta`
- `preview` 响应必须包含 `preview_type`，并支持：
  - `image`
  - `image_too_large`
  - `plotly_chart`
  - `text`
  - `html`
  - `pdf`
  - `unsupported`
  - `unavailable`
  - `error`
- `executions` 响应必须返回数组字段 `executions`。
- `folders` 响应必须返回平铺 `folders` 数组，而不是嵌套树。
- `download_url` 仍是前端协议的一部分，尤其会影响：
  - 图片缩略图
  - Plotly/PDF 预览
  - Markdown 下载兼容逻辑

---

## 新版工作空间接口现状

### 已声明的新式路由

当前后端声明了以下新式路由：

1. `GET /api/workspace/{session_id}/tree`
2. `GET /api/workspace/{session_id}/files/{file_path}`
3. `POST /api/workspace/{session_id}/files/{file_path}`
4. `DELETE /api/workspace/{session_id}/files/{file_path}`
5. `POST /api/workspace/{session_id}/files/{file_path}/rename`
6. `GET /api/workspace/{session_id}/download/{file_path}`
7. `POST /api/workspace/{session_id}/download-zip`
8. `GET /api/workspace/{session_id}/uploads/{filename}`
9. `GET /api/workspace/{session_id}/notes/{filename}`
10. `GET /api/workspace/{session_id}/artifacts/{filename}/bundle`

### 当前已落地的部分

以下新版路由当前已作为正式接口使用：

- `/files`
- `/files/{path}`
- `/files/{path}/preview`
- `/files/{path}/rename`
- `/files/{path}/move`
- `/tree`
- `/executions`
- `/folders`
- `/download-zip`
- `/uploads/{filename}`
- `/notes/{filename}`
- `/artifacts/{filename}/bundle`

---

## 迁移结果

本次迁移包含以下关键动作：

1. 补齐 `WorkspaceManager` 的路径式能力：
   - `workspace_dir`
   - 路径安全解析
   - `get_tree`
   - `read_file`
   - `save_text_file`
   - 路径式删除、重命名、移动、ZIP 打包
2. 让新版路由追平旧版关键语义：
   - 列表/搜索
   - 预览
   - 执行历史
   - 文件夹
   - 数据集删除/重命名后的 `session.datasets` 同步
3. 前端工作空间主链路切换到新版 API
4. 删除旧版 `/api/sessions/{sid}/workspace...` 兼容接口
