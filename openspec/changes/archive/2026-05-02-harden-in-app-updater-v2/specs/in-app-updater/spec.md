## ADDED Requirements

### Requirement: 更新 API 鉴权与 CSRF 防护
系统 SHALL 对所有可触发下载或安装动作的更新 API 进行鉴权，并通过 Origin/Referer 校验防止本地浏览器中其它来源的请求触发升级。

#### Scenario: 未携带 API Key 的下载或安装请求被拒绝
- **GIVEN** 客户端调用 `/api/update/download` 或 `/api/update/apply` 但未携带 `X-Nini-Token`
- **WHEN** 后端处理请求
- **THEN** 系统 MUST 返回 401，并 MUST 不启动下载或 updater

#### Scenario: 非允许 Origin 的下载或安装请求被拒绝
- **GIVEN** `update_require_origin_check=true` 且请求的 `Origin`/`Referer` 不属于允许列表
- **WHEN** 客户端调用 `/api/update/download` 或 `/api/update/apply`
- **THEN** 系统 MUST 返回 403

#### Scenario: 企业离线部署关闭 Origin 校验
- **GIVEN** 部署方显式设置 `update_require_origin_check=false`
- **WHEN** 客户端调用 `/api/update/download` 或 `/api/update/apply` 且通过 API Key 校验
- **THEN** 系统 MUST 接受请求并按正常流程执行

### Requirement: updater 二次校验
系统 SHALL 在独立 updater 进程真正执行 NSIS 安装器之前，对安装包重新做一次完整性与签名校验，关闭主进程校验通过后文件被替换的时间窗口。

#### Scenario: updater 二次校验 SHA256 失败
- **GIVEN** updater 收到来自后端的 `--expected-sha256`
- **WHEN** updater 在等待 PID 退出后重新计算 SHA256，结果与期望值不一致
- **THEN** updater MUST 写入失败日志、返回非零退出码、不启动 NSIS 安装器

#### Scenario: updater 二次校验 Authenticode 失败
- **GIVEN** updater 在 Windows 平台对安装包重新执行 Authenticode 校验
- **WHEN** 校验状态非 `Valid` 或证书不在允许列表
- **THEN** updater MUST 写入失败日志、返回非零退出码、不启动 NSIS 安装器

### Requirement: 下载链路 redirect 禁用
系统 SHALL 在 manifest 与安装包下载过程中显式禁用 HTTP 重定向，确保校验过的 URL 与最终下载来源一致。

#### Scenario: manifest 或安装包返回 3xx 时下载被拒绝
- **GIVEN** 服务器对 manifest 或安装包 URL 返回任意 3xx 重定向
- **WHEN** 客户端处理响应
- **THEN** 系统 MUST 终止下载并返回可读错误，且 MUST 不向重定向目标发起下载

### Requirement: 有序 shutdown
系统 SHALL 在启动 updater 之后以有序方式释放后端资源、子进程与文件句柄，再退出当前后端进程，确保 updater 不被文件锁阻塞。

#### Scenario: 沙箱子进程在 grace 周期内退出
- **GIVEN** 后端在收到合法 apply 请求后启动 updater
- **WHEN** 后端进入退出流程并通知所有沙箱子进程关闭
- **THEN** 系统 MUST 在 `update_apply_grace_seconds` 之内等待子进程退出，再 flush 日志、关闭 SQLite/文件句柄

#### Scenario: 沙箱子进程超时未退出
- **GIVEN** 沙箱子进程在 grace 周期内未退出
- **WHEN** grace 周期到期
- **THEN** 系统 MUST 兜底执行 `os._exit(0)`，并把所有派生子进程 PID 一起传给 updater 等待

### Requirement: updater 文件锁探测
系统 SHALL 在 PID 退出之后、NSIS 安装之前对安装目录做独占文件锁探测，避免杀软或 Explorer 预览导致 NSIS 失败；该机制兼作 GUI 壳子进程残留场景的兜底。

#### Scenario: 文件锁探测超时
- **GIVEN** 安装目录被其它进程持有文件锁
- **WHEN** updater 在 `update_apply_lock_probe_seconds` 内反复尝试独占重命名安装目录仍未成功
- **THEN** updater MUST 取消安装、保留安装包、写日志，并返回特定退出码以区分文件锁失败与其它失败

### Requirement: 备份硬链接 clone
系统 SHALL 优先使用 NTFS 硬链接克隆安装目录作为备份，避免 PyInstaller 产物的完整拷贝消耗 GB 级磁盘。

#### Scenario: 硬链接克隆成功
- **GIVEN** 安装目录位于支持硬链接的 NTFS 卷
- **WHEN** updater 备份当前安装目录
- **THEN** 系统 MUST 使用 `os.link` 递归克隆并在秒级完成

#### Scenario: 硬链接失败时回退到拷贝
- **GIVEN** 安装目录所在卷不支持硬链接（如 FAT32、网络盘）
- **WHEN** updater 尝试硬链接克隆失败
- **THEN** 系统 MUST 回退到 `shutil.copytree` 完成备份

#### Scenario: 备份失败时中止升级
- **GIVEN** 硬链接与拷贝均失败
- **WHEN** updater 进入备份阶段
- **THEN** updater MUST 返回非零退出码、不进入 NSIS 安装器

### Requirement: 续传期望 SHA256 比对
系统 SHALL 在断点续传前比对当前 manifest 的 sha256 与已下载状态中的 `expected_sha256`，不一致即丢弃旧字节。

#### Scenario: 同 version 重发布丢弃旧字节
- **GIVEN** 服务器以同 version 重发布安装包，sha256 发生变化
- **WHEN** 客户端尝试续传
- **THEN** 系统 MUST 删除旧 `.download` 临时文件、状态置 `idle`，并从头开始下载

### Requirement: updater 进程 detach
系统 SHALL 在启动 updater 时尽力使用 detach 标志，避免 GUI 壳的生命周期连带杀死 updater。

#### Scenario: GUI 壳关闭后 updater 仍存活
- **GIVEN** GUI 壳通过 job object 启动后端，且 job 在后端退出后被关闭
- **WHEN** 后端启动 updater 后退出
- **THEN** updater MUST 通过 detach 相关 `creationflags` 尝试脱离上层进程组继续运行；当具体标志组合在当前 job 设置下不被支持时，系统 SHOULD fallback 到不依赖 BREAKAWAY 的 detach 组合，再失败可回退到当前的 `CREATE_NO_WINDOW`

### Requirement: 检查状态枚举
系统 SHALL 将检查更新结果的状态字段定义为有限枚举，并在前后端共享类型定义。

#### Scenario: 渠道切换无法降级时返回 channel_mismatch
- **GIVEN** 当前安装为 beta 版本，stable 渠道 manifest 版本低于当前版本
- **WHEN** 客户端检查 stable 渠道
- **THEN** 系统 MUST 返回 `channel_mismatch` 状态而非 `up_to_date`，让 UI 给出"切换渠道无法降级"的提示

### Requirement: downgrade 保护
系统 SHALL 在版本比较时拒绝 manifest 中版本低于当前安装版本的"升级"。

#### Scenario: manifest 版本低于当前安装版本
- **GIVEN** manifest 中 `version` 低于当前安装版本（不同渠道）
- **WHEN** 客户端比较版本
- **THEN** 系统 MUST 不报告 `update_available=true`，并在状态中提示 `channel_mismatch` 或 `up_to_date`，避免静默降级
