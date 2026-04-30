## ADDED Requirements

### Requirement: 版本检查
系统 SHALL 支持从配置的更新服务器获取当前渠道的最新版本信息，并判断当前安装版本是否需要更新。

#### Scenario: 发现可用更新
- **GIVEN** 当前 Nini 版本低于服务器 manifest 中的最新版本
- **WHEN** 用户手动检查更新或自动检查任务运行
- **THEN** 系统 MUST 返回可更新状态、最新版本号、发布时间、更新说明、安装包大小和是否重要更新

#### Scenario: 当前已是最新版本
- **GIVEN** 当前 Nini 版本等于或高于服务器 manifest 中的最新版本
- **WHEN** 用户检查更新
- **THEN** 系统 MUST 返回无需更新状态，并展示当前版本号

#### Scenario: 更新服务器不可用
- **GIVEN** 更新服务器超时、不可达或返回无效 manifest
- **WHEN** 系统检查更新
- **THEN** 系统 MUST 返回检查失败状态和可读错误信息，且不得影响 Nini 现有功能运行

#### Scenario: 未配置更新源
- **GIVEN** 系统未配置更新服务器 URL
- **WHEN** 自动检查更新任务运行
- **THEN** 系统 MUST 跳过检查且不得向用户展示失败提示

### Requirement: Manifest 约束
系统 SHALL 通过 manifest 描述发布版本，并校验 manifest 的产品、渠道、平台、版本号和安装包信息。

#### Scenario: Manifest 与当前产品不匹配
- **GIVEN** manifest 的 product 不是 `nini`
- **WHEN** 系统解析 manifest
- **THEN** 系统 MUST 拒绝该 manifest 并返回更新源不可信或不匹配错误

#### Scenario: Manifest 缺少安装包校验信息
- **GIVEN** manifest 中目标平台 asset 缺少 sha256 或 size
- **WHEN** 系统解析 manifest
- **THEN** 系统 MUST 拒绝该更新包并禁止下载

#### Scenario: 重要更新不阻断使用
- **GIVEN** manifest 将更新标记为 important
- **WHEN** 系统展示更新提示
- **THEN** 系统 MUST 将其作为重要提示展示，但不得阻断用户继续使用当前版本

#### Scenario: 不支持的平台
- **GIVEN** manifest 中没有适用于当前平台的 asset
- **WHEN** 系统检查更新
- **THEN** 系统 MUST 返回无适用安装包状态，不得尝试下载其他平台文件

### Requirement: 更新包下载与校验
系统 SHALL 在用户确认后下载更新安装包，并在安装前完成完整性和签名校验。

#### Scenario: 下载并校验成功
- **GIVEN** 用户确认下载更新且更新包 URL 使用 HTTPS 或显式允许的内网 HTTP
- **WHEN** 下载完成、文件 SHA256 与 manifest 一致且 Authenticode 签名可信
- **THEN** 系统 MUST 将更新状态标记为 ready，并允许用户进入安装确认步骤

#### Scenario: 下载 URL 不安全
- **GIVEN** manifest 中安装包 URL 不是 HTTPS，且不是显式允许的 localhost、环回地址、私有网段 IP 或链路本地地址 HTTP
- **WHEN** 系统准备下载更新包
- **THEN** 系统 MUST 拒绝下载并返回安全错误

#### Scenario: SHA256 校验失败
- **GIVEN** 下载完成的安装包 SHA256 与 manifest 不一致
- **WHEN** 系统执行校验
- **THEN** 系统 MUST 删除或隔离该安装包，标记校验失败，并禁止安装

#### Scenario: 安装包签名不可信
- **GIVEN** 下载完成的 Windows 安装包缺少 Authenticode 签名或签名证书不在允许列表中
- **WHEN** 系统执行安装前校验
- **THEN** 系统 MUST 标记签名校验失败，并禁止安装

#### Scenario: 下载失败可重试
- **GIVEN** 下载过程中网络中断或服务器返回错误
- **WHEN** 用户再次点击下载
- **THEN** 系统 MUST 支持重新开始下载，并保留当前已安装版本不受影响

#### Scenario: 重复下载请求幂等
- **GIVEN** 已存在正在下载或已校验通过的 active update
- **WHEN** 用户再次请求下载同一版本
- **THEN** 系统 MUST 返回现有更新任务状态，不得并发启动第二个同版本下载任务

#### Scenario: 新版本替换旧 ready 包
- **GIVEN** 本地已有已校验通过的旧版本更新包
- **WHEN** manifest 显示存在更高版本更新
- **THEN** 系统 MUST 将旧版本更新包状态标记为过期或历史，不得将其作为当前 ready 更新包安装

### Requirement: 半自动静默安装
系统 SHALL 在用户确认后启动独立 updater，退出当前 Nini 进程，并由 updater 静默运行安装器完成升级。

#### Scenario: 用户确认立即升级
- **GIVEN** 更新包已下载且校验通过
- **WHEN** 用户点击立即重启并升级
- **THEN** 系统 MUST 启动独立 updater，并安排当前 Nini 进程退出

#### Scenario: Updater 等待 Nini 相关进程退出
- **GIVEN** updater 已启动且收到后端 PID、可选 GUI PID 或安装目录进程匹配信息
- **WHEN** 仍存在相关 Nini 进程运行或安装目录文件锁未释放
- **THEN** updater MUST 等待相关进程退出或超时失败后再决定是否运行安装器

#### Scenario: GUI 与后端共同退出
- **GIVEN** Nini 以 Windows GUI 壳启动并运行后端服务
- **WHEN** 用户确认立即升级
- **THEN** 系统 MUST 协调 GUI 壳和后端服务退出，避免仅退出后端而保留 GUI 进程占用安装目录

#### Scenario: 静默安装成功
- **GIVEN** updater 已确认主进程退出且安装包存在
- **WHEN** 安装器以静默参数成功退出
- **THEN** updater MUST 启动新版本 Nini，并记录升级成功日志

#### Scenario: 静默安装失败
- **GIVEN** updater 运行安装器后收到非零退出码
- **WHEN** 安装过程失败
- **THEN** updater MUST 记录失败日志，不得删除用户数据目录，并不得报告升级成功

### Requirement: 用户数据保护
系统 SHALL 在升级过程中保留用户配置、会话、数据库、上传文件、知识库和日志等运行时数据。

#### Scenario: 升级覆盖程序文件
- **GIVEN** 用户数据位于配置解析后的用户数据目录，默认 `%USERPROFILE%\.nini`
- **WHEN** updater 静默覆盖安装 Nini 程序目录
- **THEN** 系统 MUST 保留该用户数据目录中的用户数据

#### Scenario: 卸载提示不影响升级
- **GIVEN** NSIS 安装器执行覆盖安装而不是卸载流程
- **WHEN** 用户执行应用内升级
- **THEN** 系统 MUST 不弹出删除用户数据的确认，也不得自动清理用户数据

### Requirement: 安装条件保护
系统 SHALL 在不适合安装的状态下阻止 apply 操作，并给出明确原因。

#### Scenario: 源码开发环境禁止安装
- **GIVEN** Nini 运行在非打包源码环境
- **WHEN** 用户请求立即升级
- **THEN** 系统 MUST 拒绝执行安装，并提示源码环境不支持应用内安装升级

#### Scenario: Agent 任务运行中禁止安装
- **GIVEN** 当前存在正在运行的 Agent 任务或长耗时操作
- **WHEN** 用户请求立即升级
- **THEN** 系统 MUST 阻止安装并提示用户等待任务完成，但 MAY 允许提前下载更新包

#### Scenario: 运行状态由后端判定
- **GIVEN** 前端请求 apply 操作
- **WHEN** 后端检查是否存在运行中的 Agent 任务
- **THEN** 后端 MUST 使用服务端运行状态作为最终判定，不得只信任前端传入的运行状态

#### Scenario: 更新包未就绪禁止安装
- **GIVEN** 更新包尚未下载或校验未通过
- **WHEN** 用户请求立即升级
- **THEN** 系统 MUST 拒绝启动 updater，并提示需要先下载并校验更新包

### Requirement: 前端更新体验
系统 SHALL 在 Web UI 中提供清晰的更新状态、用户确认和错误恢复入口。

#### Scenario: 自动低频检查
- **GIVEN** 用户启用自动检查更新且距离上次检查超过配置间隔
- **WHEN** Nini 前端初始化完成
- **THEN** 前端 MUST 请求更新检查，并在发现新版本时展示非阻塞提示

#### Scenario: 下载进度展示
- **GIVEN** 用户已开始下载更新包
- **WHEN** 前端查询更新状态
- **THEN** 前端 MUST 展示下载进度、目标版本和当前状态

#### Scenario: 安装前确认
- **GIVEN** 更新包已 ready
- **WHEN** 用户准备安装
- **THEN** 前端 MUST 明确提示 Nini 将重启升级，并要求用户确认后才调用 apply

#### Scenario: 错误可见
- **GIVEN** 检查、下载、校验或安装准备阶段失败
- **WHEN** 前端展示更新状态
- **THEN** 前端 MUST 展示可读错误信息和可执行的重试或稍后处理入口

### Requirement: 版本来源统一
系统 SHALL 使用单一版本读取逻辑为 CLI、API、更新检查和应用元数据提供当前版本。

#### Scenario: 已安装包版本可读取
- **GIVEN** Nini 作为已安装 Python 包或打包应用运行
- **WHEN** 系统需要当前版本
- **THEN** 系统 MUST 优先从包元数据读取版本，并在不可用时使用受控 fallback

#### Scenario: 版本不一致被测试捕获
- **GIVEN** 项目中存在多个展示版本的入口
- **WHEN** 运行版本一致性测试
- **THEN** 测试 MUST 验证这些入口使用同一版本来源或返回相同版本

#### Scenario: 版本比较遵循 PEP 440
- **GIVEN** 当前版本和 manifest 版本包含预发布或发布候选标记
- **WHEN** 系统比较版本新旧
- **THEN** 系统 MUST 按 PEP 440 规则判断版本顺序，或拒绝不符合 PEP 440 的发布版本

### Requirement: 发布元数据生成
系统 SHALL 在发布构建中提供生成或校验更新 manifest、SHA256 和签名策略的能力。

#### Scenario: 构建发布包
- **GIVEN** 构建脚本已生成 Windows 安装包
- **WHEN** 发布者执行发布元数据生成步骤
- **THEN** 系统 MUST 生成包含版本号、渠道、安装包大小、下载 URL 占位或配置值、SHA256、签名策略说明和更新说明的 manifest 草稿

#### Scenario: Manifest 与安装包不一致
- **GIVEN** manifest 中的 size 或 sha256 与安装包实际值不一致
- **WHEN** 发布者执行校验步骤
- **THEN** 系统 MUST 报告错误并阻止将该 manifest 标记为可发布
