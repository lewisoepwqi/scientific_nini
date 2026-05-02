## ADDED Requirements

### Requirement: 写操作端点鉴权
所有修改数据的 HTTP API 端点（POST/PUT/PATCH/DELETE）SHALL 通过 FastAPI 依赖项 `require_auth` 验证请求已认证。未认证请求 SHALL 返回 401。

威胁模型：本鉴权防御的是浏览器跨域 CSRF（恶意网页诱导浏览器向 localhost 发 POST），而非本地恶意进程。本地恶意进程可直接获取 HMAC Cookie。

#### Scenario: 未认证写操作被拒绝
- **WHEN** 未携带有效 Cookie 或 Bearer Token 的请求访问 `POST /api/upload`
- **THEN** 返回 HTTP 401

#### Scenario: 已认证写操作成功
- **WHEN** 携带有效 Cookie 的请求访问 `POST /api/upload`
- **THEN** 请求正常处理

#### Scenario: 读操作无需鉴权
- **WHEN** 未认证请求访问 `GET /api/datasets/{session_id}`
- **THEN** 请求正常处理，不要求鉴权

### Requirement: 文件路径 TOCTOU 防御
`_resolve_file_path` SHALL 在 resolve 后使用 `os.path.realpath` 做最终校验，确保解析后的路径未超出预期目录。

#### Scenario: 符号链接指向外部被拒绝
- **WHEN** `workspace/artifacts/safe.csv` 是指向 `/etc/passwd` 的符号链接
- **THEN** `_resolve_file_path` 返回 None
