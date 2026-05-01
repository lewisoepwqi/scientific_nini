# Nini 应用内更新——服务器端搭建手册（小白版）

> 适用人群：第一次接触 Linux 服务器、SSH、systemd 的开发者或运维。
> 目标：在一台 Linux 服务器上托管 Nini 的更新清单和安装包，让所有客户端能通过"检查更新"按钮自动升级。
> 阅读约定：命令前缀 `本地$` 表示在你**本地打包电脑**执行；`服务器$` 表示在**远程 Linux 服务器**执行。

---

## 0. 你即将搭建什么

### 0.1 总体架构（一句话）

```
┌──────────────────┐    HTTPS/HTTP GET     ┌────────────────────────┐
│ Nini 客户端 (exe)│ ────────────────────▶ │ 静态文件服务器          │
│  - check update  │ ◀──── latest.json ─── │  /opt/nini-updates/... │
│  - download exe  │ ◀──── Setup.exe   ─── │  (systemd + http.server│
│  - verify+install│                       │   或 Caddy/Nginx)      │
└──────────────────┘                       └────────────────────────┘
```

**服务器只做一件事**：把两个文件放到 HTTP 能访问的目录里。
**它不跑任何 Nini 代码**，不需要 Python 解释器之外的任何依赖（脚本会用 Python 内置的 `http.server` 当文件服务器）。

### 0.2 客户端与服务器之间约定的"协议"

客户端会拉取这个 URL：

```
{NINI_UPDATE_BASE_URL}/{channel}/latest.json
例：http://1.2.3.4:8080/nini/updates/stable/latest.json
```

`latest.json` 的形状（由 `scripts/generate_update_manifest.py` 生成，不要手写）：

```jsonc
{
  "schema_version": 1,
  "product": "nini",
  "channel": "stable",
  "version": "0.1.2",
  "released_at": "2026-05-01T10:00:00+00:00",
  "minimum_supported_version": "0.1.0",
  "important": false,
  "title": "Nini 0.1.2",
  "notes": ["修复若干问题", "新增导出功能"],
  "assets": [
    {
      "platform": "windows-x64",
      "kind": "nsis-installer",
      "url": "http://1.2.3.4:8080/nini/updates/stable/Nini-0.1.2-Setup.exe",
      "size": 712345678,
      "sha256": "<64 位十六进制>"
    }
  ],
  "signature_policy": "...",
  "signature": null,
  "signature_url": null
}
```

客户端拿到后会做的事：
1. 比版本号（PEP 440 规范，比如 `0.1.2 > 0.1.1`）。
2. 用 `assets[].url` 下载 `.exe`，**禁止 3xx 跳转**（所以 url 必须是直链）。
3. 比对下载完文件的 SHA256 是否等于 `assets[].sha256`。
4. 在 Windows 上额外校验 Authenticode 数字签名（如果客户端启用）。
5. 启动 `nini-updater.exe`，由它**再做一次** SHA256 + Authenticode 校验，然后调用 NSIS 静默安装。

### 0.3 你必须接受的几个前置规则

| 规则 | 原因 |
|---|---|
| `latest.json` 和 `Setup.exe` 必须在**同一个域名/IP + 端口**下 | 客户端会校验 asset URL 与 base URL 同源，跨域会拒绝 |
| 默认必须 HTTPS；如果用 HTTP，则只能用 IP 或 localhost，且客户端要显式开启 `NINI_UPDATE_ALLOW_INSECURE_HTTP=true` | 防止中间人篡改下载内容 |
| 服务器**不能**做 301/302 跳转 | 客户端 `follow_redirects=False`，跳一次就直接报错 |
| 每次发新版必须**先**重新生成 `latest.json` 再上传 `.exe`，**而且两个一起替换** | `latest.json` 里的 SHA256 和 size 都是和具体 exe 绑定的 |
| 版本号必须严格符合 PEP 440 (`0.1.2`、`1.0.0rc1` 等) | 客户端用 `packaging.version.Version` 比较，不规范会拒绝 |

---

## 1. 准备阶段

### 1.1 你需要准备的东西

| 类别 | 内容 | 怎么获得 |
|---|---|---|
| 服务器 | 一台 Linux（Ubuntu 20.04+/Debian 11+/CentOS 8+ 都行），1 核 1G 起步够了 | 阿里云、腾讯云、华为云、Vultr、DigitalOcean 任意一个 |
| 服务器访问 | SSH 用户名 + 密码或私钥；最好有 sudo 权限 | 购买服务器时设置 |
| 网络 | 公网 IP（或者你打算配的域名），TCP 8080 端口在云厂商安全组放行 | 云厂商控制台 → 安全组/防火墙 |
| 客户端电脑 | 已经能跑 `build_windows.bat` 打包出 `Nini-x.y.z-Setup.exe` 的 Windows 机器 | 仓库现状 |
| 本仓库代码 | 至少包含 `scripts/setup_update_server.sh` 和 `scripts/generate_update_manifest.py` | 你已经有了 |

> **如果只是内网部署**：服务器换成内网一台 Linux 就行，IP 用内网 IP，客户端 `.env` 里加 `NINI_UPDATE_ALLOW_INSECURE_HTTP=true` 即可，省去 HTTPS 配置。

### 1.2 把脚本传到服务器

**为什么**：服务器上还没有 `setup_update_server.sh`，得先把它送过去。

**怎么做**（在本地电脑执行）：

```bash
本地$ scp scripts/setup_update_server.sh 用户名@服务器IP:~/
```

**验证**：

```bash
本地$ ssh 用户名@服务器IP 'ls -l ~/setup_update_server.sh'
# 应能看到几 KB 的文件
```

**意外处理**：

| 报错 | 原因 | 解决 |
|---|---|---|
| `Permission denied (publickey,password)` | SSH 密码/秘钥不对 | 检查云厂商控制台里的登录信息 |
| `Connection timed out` | 安全组没开 22 端口 / 服务器没启 | 云厂商控制台放行 22；用 VNC 连进去看 sshd 状态 |
| `scp: command not found` | 你本地没装 `scp` | macOS/Linux 默认有；Windows 用 PowerShell 自带的 `scp` 或 WinSCP 客户端 |

---

## 2. 在服务器上跑安装脚本

### 2.1 这一步会做什么

`setup_update_server.sh` 会：

1. 创建发布目录 `/opt/nini-updates/public/nini/updates/{stable,beta}`。
2. 写一份 `UPLOAD_INSTRUCTIONS.txt` 备忘。
3. 用 Python 内置的 `http.server` 起一个静态文件服务，监听你指定的端口。
4. 把它做成 systemd 服务（`nini-updates.service`），开机自启 + 崩了自动拉起。
5. （可选）尝试用 ufw / firewalld 放行端口。

### 2.2 操作

```bash
服务器$ bash ~/setup_update_server.sh
```

脚本是**全程交互**的，下面给出每个问题的推荐答法和"为什么"。

| 问题 | 推荐回答 | 为什么 |
|---|---|---|
| 发布文件根目录 | 回车（默认 `/opt/nini-updates/public`） | `/opt` 是 Linux 习惯放可选软件的位置，权限干净 |
| 更新渠道 | 回车（`stable`） | 客户端默认拉 `stable`；以后想发 beta 再加目录即可 |
| 监听地址 | 回车（`0.0.0.0`） | 表示监听所有网卡。**只想内网访问**就改成内网 IP |
| 监听端口 | 回车（`8080`） | 1024 以下端口要 root，8080 不冲突且常用 |
| 客户端访问的 IP / 主机名 | 填你的**公网 IP** 或域名 | 脚本探测的可能是内网 IP，不能直接给客户端用 |
| 上传示例使用的版本号 | 改成你下一个要发的版本，如 `0.1.2` | 仅用于 README 里的示例命令，可乱填 |
| 客户端是否通过 HTTPS 访问 | 没配证书选 `N`，配了 Caddy/Nginx 反代选 `Y` | 决定 `latest.json` 里的 url 用什么协议 |
| 是否创建 systemd 后台服务 | `Y` | 否则 SSH 一断服务就停 |
| 是否放行防火墙端口 | `Y` | 系统级防火墙；**云厂商安全组要另外手动开** |

### 2.3 验证

脚本结尾会打印一段配置摘要，**完整复制保存**。然后做三个验证：

```bash
# 1. systemd 服务跑起来了吗？
服务器$ sudo systemctl status nini-updates
# 看到 "active (running)" 即可

# 2. 端口监听上了吗？
服务器$ ss -tlnp | grep 8080
# 应看到 python3 在 0.0.0.0:8080

# 3. 在你本地浏览器打开
http://你的公网IP:8080/nini/updates/stable/
# 应看到一个简陋的目录列表（可能是空的或只有 UPLOAD_INSTRUCTIONS.txt），这是正常的
```

### 2.4 意外处理

| 现象 | 原因 | 解决 |
|---|---|---|
| `bash: setup_update_server.sh: 权限不够` | 文件没执行权 | 用 `bash 路径` 运行（脚本里已经这么做了），或 `chmod +x` |
| `缺少命令：python3` | 服务器太精简 | `sudo apt install python3` 或 `sudo yum install python3` |
| `缺少命令：sudo` | 你以 root 登录，没装 sudo | 直接以 root 跑脚本即可，脚本兼容 |
| `systemctl: command not found` | 老系统不用 systemd（如 Alpine） | 选 `N` 跳过创建服务，自己用 `nohup`/`tmux` 起一个进程；或换 systemd 系统 |
| 脚本结束但 `systemctl status` 显示 `failed` | 端口被占 / 目录没权限 | `sudo journalctl -u nini-updates -n 50` 看错 |
| 浏览器打不开 | 云厂商安全组没放行 8080 | 进云控制台 → 安全组 → 入方向 → 添加 TCP 8080 来源 0.0.0.0/0 |
| 浏览器打开但是慢/丢包 | 服务器在境外 + 没备案 | 换境内服务器，或上 Cloudflare 加速 |

### 2.5 想推倒重来怎么办

```bash
服务器$ sudo systemctl disable --now nini-updates
服务器$ sudo rm /etc/systemd/system/nini-updates.service
服务器$ sudo systemctl daemon-reload
服务器$ sudo rm -rf /opt/nini-updates
# 然后重新跑脚本
```

---

## 3. 在本地生成 `latest.json`

### 3.1 为什么必须在本地生成

- `latest.json` 里有 `sha256` 和 `size`，是**针对具体 .exe 文件计算的**。
- 在服务器上手写 JSON 几乎一定会算错或漏字段，客户端校验会失败。
- 必须用仓库里的 `scripts/generate_update_manifest.py`，它会做 PEP 440、协议、URL 等所有校验。

### 3.2 操作

先确认你本地已经有打包产物：

```bash
本地$ ls dist/Nini-0.1.2-Setup.exe   # 路径以你实际为准
```

然后运行：

```bash
本地$ python scripts/generate_update_manifest.py \
  --installer dist/Nini-0.1.2-Setup.exe \
  --version 0.1.2 \
  --channel stable \
  --base-url "http://你的公网IP:8080/nini/updates/stable/" \
  --notes "修复若干问题|新增导出功能" \
  --output dist/latest.json \
  --allow-insecure-http
```

参数详解：

| 参数 | 必填 | 说明 |
|---|---|---|
| `--installer` | ✅ | 指向本地 .exe，脚本会读出大小并算 SHA256 |
| `--version` | ✅ | **必须和 exe 内嵌版本一致**；不一致客户端比对会出 bug |
| `--channel` | ✅ | `stable` 或 `beta`；要和服务器目录、客户端 `.env` 一致 |
| `--base-url` | ✅ | **末尾必须有 `/`**，且包含 channel 段；客户端会做同源校验 |
| `--notes` | 可选 | `\|` 分隔多条更新说明；前端会按列表展示 |
| `--important` | 可选 | 加上后客户端会强制弹窗，不能"下次再说" |
| `--allow-insecure-http` | HTTP 时必须加 | 如果 `--base-url` 用 HTTP + IP，必须显式同意；用 HTTPS 不需要 |
| `--output` | ✅ | 写到哪里；后面会上传它 |

### 3.3 验证

```bash
本地$ cat dist/latest.json
# 检查：
#   - "version" 和你打包的一致
#   - "url" 末尾的 exe 文件名和实际文件名一模一样（大小写敏感）
#   - "sha256" 是 64 位十六进制
#   - "size" 是字节数（几亿是正常的）
```

补充手动校验 SHA256（可选）：

```bash
本地$ sha256sum dist/Nini-0.1.2-Setup.exe
# 输出的前 64 位应该和 latest.json 里的 sha256 完全一致
```

### 3.4 意外处理

| 报错 | 原因 | 解决 |
|---|---|---|
| `版本号不符合 PEP 440: xxx` | 用了 `v0.1.2`、`0.1.2-beta` 等非法格式 | 改成 `0.1.2` 或 `0.1.2b1` |
| `更新安装包下载 URL 必须使用 HTTPS` | 用了 HTTP 但忘了加 `--allow-insecure-http` | 加上参数；或换 HTTPS |
| `更新安装包下载 URL 必须使用 HTTPS；HTTP 仅允许显式开启的 IP 地址或 localhost` | HTTP + 域名（如 `update.example.com`） | 要么换 HTTPS，要么 base-url 用 IP |
| `FileNotFoundError` | `--installer` 路径不对 | 用绝对路径，或先 `ls` 确认 |
| `latest.json` 看起来对，但客户端报"清单无效" | `schema_version` 不是 1 | 别手动改 JSON，重跑脚本 |

---

## 4. 上传文件到服务器

### 4.1 为什么要按特定顺序

客户端拉到 `latest.json` 后会立刻去下 `assets[].url`。如果你**先**传了新的 `latest.json`、**还没**传新的 .exe，那段时间内任何检查更新的客户端都会下载到 404 或旧 exe，导致 SHA256 不匹配。

**正确顺序：先传 .exe，再传 `latest.json`。**（exe 是大文件，传得慢；最后再切 latest.json 等于做"原子切换"。）

### 4.2 操作

```bash
# 第 1 步：先传 .exe（耗时）
本地$ scp dist/Nini-0.1.2-Setup.exe \
        用户名@服务器IP:/opt/nini-updates/public/nini/updates/stable/Nini-0.1.2-Setup.exe

# 第 2 步：再传 latest.json（瞬间完成）
本地$ scp dist/latest.json \
        用户名@服务器IP:/opt/nini-updates/public/nini/updates/stable/latest.json
```

### 4.3 验证

在浏览器打开：

```
http://你的公网IP:8080/nini/updates/stable/latest.json
```

应该返回完整 JSON。再点一下 JSON 里的 `assets[0].url`，浏览器应该开始下载（或返回 200，看浏览器策略）。

更严谨的命令行验证：

```bash
本地$ curl -I "http://你的公网IP:8080/nini/updates/stable/latest.json"
# 期望：HTTP/1.0 200 OK，Content-Type: application/json

本地$ curl -I "http://你的公网IP:8080/nini/updates/stable/Nini-0.1.2-Setup.exe"
# 期望：HTTP/1.0 200 OK，Content-Length 等于 latest.json 里的 size
```

### 4.4 意外处理

| 现象 | 原因 | 解决 |
|---|---|---|
| `scp: ... Permission denied` | 目标目录属主不是你 | 在服务器上 `sudo chown -R $USER:$USER /opt/nini-updates/public`；或用 `sudo scp`（需配置） |
| `scp: ... No such file or directory` | 路径写错 | 注意是 `nini/updates/stable/`，三层目录不能少 |
| 浏览器返回 403 | 目录或文件没"其他人可读"权限 | `sudo chmod -R a+rX /opt/nini-updates/public` |
| 浏览器返回 404 | 文件名大小写不匹配 | Linux 大小写敏感，`Nini-0.1.2-Setup.exe` ≠ `nini-0.1.2-setup.exe` |
| 下载到一半断开 | Python `http.server` 不太稳健 / 公网带宽小 | 大版本上线建议把 `.exe` 放对象存储 + CDN（见第 8 节） |

---

## 5. 配置客户端

### 5.1 写入 `.env`

在每台 Nini 客户端电脑上，找到 `.env`（一般在 Nini 安装目录或用户配置目录，运行 `nini init` 会生成）。

最小可用配置：

```ini
NINI_UPDATE_BASE_URL=http://你的公网IP:8080/nini/updates/
NINI_UPDATE_CHANNEL=stable
NINI_UPDATE_ALLOW_INSECURE_HTTP=true
```

**关键约束**：

- `NINI_UPDATE_BASE_URL` **末尾必须有 `/`**。
- **不要**把 channel 拼进 base url，channel 由 `NINI_UPDATE_CHANNEL` 单独传。
- 用 HTTPS 的话第三行删掉。

### 5.2 其他可调参数（按需）

| 配置项 | 默认 | 何时需要改 |
|---|---|---|
| `NINI_UPDATE_AUTO_CHECK_ENABLED` | `true` | 关闭自动检查时设 `false` |
| `NINI_UPDATE_CHECK_INTERVAL_HOURS` | `24` | 想更频繁检查改小 |
| `NINI_UPDATE_DISABLED` | `false` | 企业离线部署彻底关掉更新功能 |
| `NINI_UPDATE_DOWNLOAD_TIMEOUT_SECONDS` | `300` | 网速慢、包大改大 |
| `NINI_UPDATE_SIGNATURE_CHECK_ENABLED` | `true` | 测试环境没签名时设 `false`（**生产请勿关闭**） |
| `NINI_UPDATE_SIGNATURE_ALLOWED_THUMBPRINTS` | 空 | 多个证书指纹用逗号分隔，正式发布推荐 |
| `NINI_UPDATE_SIGNATURE_ALLOWED_PUBLISHERS` | 空 | 测试用证书的 CN，逗号分隔 |
| `NINI_UPDATE_REQUIRE_ORIGIN_CHECK` | `true` | 企业 Tauri/Electron 自定义 scheme 时配合 `NINI_UPDATE_ALLOWED_ORIGINS`；**不要随意关闭** |
| `NINI_UPDATE_ALLOWED_ORIGINS` | 空 | 例：`tauri://localhost,nini://app` |
| `NINI_UPDATE_APPLY_GRACE_SECONDS` | `5` | 后端 shutdown 时 grace 周期，慢机器可调到 10–15 |
| `NINI_UPDATE_APPLY_LOCK_PROBE_SECONDS` | `10` | 等待 install_dir 解锁的探测时长，杀软多的环境调高 |
| `NINI_UPDATE_APPLY_WAIT_TIMEOUT_SECONDS` | `60` | updater 等所有 PID 退出的总超时 |

### 5.3 验证

启动 Nini → 设置 / 关于页 → 点"检查更新"：

- 期望看到"发现新版本 0.1.2"。
- 点"立即更新"应能进入下载 → 校验 → 重启的完整流程。

### 5.4 意外处理（客户端侧常见报错）

| 现象 | 原因 | 解决 |
|---|---|---|
| `更新源不可信` / `must be HTTPS` | base url 是 HTTP 但 `NINI_UPDATE_ALLOW_INSECURE_HTTP=false` | 设为 `true`，或换 HTTPS |
| `更新包 URL 必须与更新源同域` | `latest.json` 里 url 的 host 和 base url 不一致 | 重新生成 `latest.json`，确保 `--base-url` 写对 |
| `clientversionnewerthanmanifest` / 提示无更新 | 服务器上版本号 ≤ 客户端版本 | 升 manifest 版本号，记得 PEP 440 |
| `verify_failed` (sha256 mismatch) | 服务器上的 .exe 被替换过但 `latest.json` 没更新 | 重新跑生成脚本，重传两个文件 |
| `verify_failed` (Authenticode) | 安装包没签名 / 签名被吊销 | 测试时关 `NINI_UPDATE_SIGNATURE_CHECK_ENABLED`（仅测试），生产必须签名 |
| 客户端拉清单 5xx / `RemoteProtocolError` | 服务器进程挂了 / 端口没开 | 第 7 节的运维命令 |
| 客户端弹"channel_mismatch" | 服务器 manifest 的 channel 和客户端 `NINI_UPDATE_CHANNEL` 不一致 | 检查两边的渠道是否都是 `stable`/`beta` |
| 报"redirect not allowed" | 服务器中间走了 nginx 的 301 | 取消跳转，或在 nginx 上直接 `proxy_pass`，不要 `return 301` |

---

## 6. 发新版的标准流程（以后每次发版都这么做）

> 把它当作 SOP 抄到你团队的发布手册里。

```bash
# === 本地 ===
# 1) 改 src/nini/version.py 或 pyproject.toml 的版本号
# 2) 跑 build_windows.bat 出新的 dist/Nini-x.y.z-Setup.exe
# 3) 生成新的 latest.json
本地$ python scripts/generate_update_manifest.py \
        --installer dist/Nini-x.y.z-Setup.exe \
        --version x.y.z \
        --channel stable \
        --base-url "http://你的公网IP:8080/nini/updates/stable/" \
        --notes "本次更新内容 1|本次更新内容 2" \
        --output dist/latest.json \
        --allow-insecure-http

# 4) 验证 latest.json 正确性（可选）
本地$ python scripts/verify_update_manifest.py --manifest dist/latest.json

# === 上传 ===
# 5) 先传 .exe（大文件，慢）
本地$ scp dist/Nini-x.y.z-Setup.exe \
        用户名@服务器IP:/opt/nini-updates/public/nini/updates/stable/

# 6) 再传 latest.json（瞬间切换）
本地$ scp dist/latest.json \
        用户名@服务器IP:/opt/nini-updates/public/nini/updates/stable/

# === 验证 ===
# 7) 浏览器开 http://IP:8080/nini/updates/stable/latest.json 看是否更新到新 version
# 8) 拿一台旧版本客户端点"检查更新"，跑通完整流程
```

旧版本的 `Nini-x.y.(z-1)-Setup.exe` 可以保留也可以删，**`latest.json` 只指向最新一个**。

### 6.1 紧急回滚

发现新版有重大问题，要让所有正在升级的客户端**回到旧版**：

```bash
# 方案 A：把 latest.json 改回指向旧 exe（推荐）
本地$ python scripts/generate_update_manifest.py \
        --installer dist/Nini-旧版本-Setup.exe \
        --version 旧版本 \
        --channel stable \
        --base-url ... \
        --output dist/latest.json
本地$ scp dist/latest.json 用户名@服务器IP:/opt/nini-updates/public/nini/updates/stable/

# 方案 B：直接删 latest.json
服务器$ sudo rm /opt/nini-updates/public/nini/updates/stable/latest.json
# 客户端会拉到 404，自动检查会安静失败，不会推送任何更新
```

> 注意：**已经升级到新版的客户端不会自动回滚**——客户端只接受 `is_safe_upgrade()` 通过的更新，老版本号会被识别为降级而拒绝。回滚只是阻止剩余客户端继续升级，已经升上去的需要用户手动卸载重装。

---

## 7. 日常运维

### 7.1 服务管理

```bash
服务器$ sudo systemctl status nini-updates    # 看状态
服务器$ sudo systemctl restart nini-updates   # 重启
服务器$ sudo systemctl stop nini-updates      # 停止
服务器$ sudo systemctl start nini-updates     # 启动
服务器$ sudo journalctl -u nini-updates -f    # 实时日志（Ctrl+C 退出）
服务器$ sudo journalctl -u nini-updates -n 200 # 最近 200 行
```

### 7.2 看谁在拉

`http.server` 默认会把每个请求打到 stdout，systemd 会收进 journal：

```bash
服务器$ sudo journalctl -u nini-updates --since "1 hour ago" | grep latest.json
```

可以粗略看到每小时多少客户端在检查更新。

### 7.3 占用空间清理

```bash
服务器$ du -sh /opt/nini-updates/public/nini/updates/stable/
# 一般每个版本 700MB 左右

服务器$ ls -lt /opt/nini-updates/public/nini/updates/stable/*.exe
# 按时间倒序，保留最近 2~3 个，其他可删
服务器$ sudo rm /opt/nini-updates/public/nini/updates/stable/Nini-0.1.0-Setup.exe
```

### 7.4 改端口

```bash
服务器$ sudo systemctl edit nini-updates
# 在打开的编辑器里写：
# [Service]
# ExecStart=
# ExecStart=/usr/bin/python3 -m http.server 9090 --bind 0.0.0.0 --directory /opt/nini-updates/public
# 保存退出，然后：
服务器$ sudo systemctl daemon-reload
服务器$ sudo systemctl restart nini-updates
# 别忘了云厂商安全组也开 9090
```

### 7.5 服务器迁移

```bash
# 老服务器：
老服务器$ sudo tar czf /tmp/nini-updates.tgz -C /opt nini-updates
本地$ scp 老服务器:/tmp/nini-updates.tgz .
本地$ scp nini-updates.tgz 新服务器:/tmp/

# 新服务器：先跑一遍 setup_update_server.sh 装好 systemd 服务，然后：
新服务器$ sudo systemctl stop nini-updates
新服务器$ sudo rm -rf /opt/nini-updates
新服务器$ sudo tar xzf /tmp/nini-updates.tgz -C /opt
新服务器$ sudo systemctl start nini-updates
# 同时更新所有客户端的 NINI_UPDATE_BASE_URL，或在原 IP 上做 DNS 切换
```

---

## 8. 进阶：上 HTTPS（强烈推荐用于公网）

### 8.1 为什么要做

- HTTP 下，运营商或 WiFi 中间人能改 `latest.json`，把 SHA256 换成自己的恶意 exe。客户端虽然有 Authenticode 校验兜底，但还是少一层防御。
- 客户端 `NINI_UPDATE_ALLOW_INSECURE_HTTP=true` 是临时方案，长期使用会让其他配置项的安全假设失效。

### 8.2 用 Caddy（最简单）

Caddy 会自动申请 Let's Encrypt 证书，5 行配置搞定。

```bash
服务器$ sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
服务器$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
服务器$ curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
        sudo tee /etc/apt/sources.list.d/caddy-stable.list
服务器$ sudo apt update && sudo apt install caddy
服务器$ sudo nano /etc/caddy/Caddyfile
```

写入（把 `update.example.com` 改成你的域名，DNS 先解析到这台服务器）：

```caddyfile
update.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
服务器$ sudo systemctl reload caddy
# 等几秒证书签发完成
本地$ curl -I https://update.example.com/nini/updates/stable/latest.json
# 应看到 HTTP/2 200
```

之后客户端 `.env` 改成：

```ini
NINI_UPDATE_BASE_URL=https://update.example.com/nini/updates/
NINI_UPDATE_CHANNEL=stable
# 删掉 NINI_UPDATE_ALLOW_INSECURE_HTTP
```

并**重新生成** `latest.json`（base-url 也要改成 https），重传。

### 8.3 让 8080 不再公开

HTTPS 上了之后，8080 应该只允许本机访问：

```bash
# 修改 systemd 单元，把 --bind 0.0.0.0 改成 --bind 127.0.0.1
服务器$ sudo systemctl edit nini-updates
# [Service]
# ExecStart=
# ExecStart=/usr/bin/python3 -m http.server 8080 --bind 127.0.0.1 --directory /opt/nini-updates/public
服务器$ sudo systemctl daemon-reload && sudo systemctl restart nini-updates

# 关云厂商安全组 8080 入方向，只保留 22 + 443
```

---

## 9. 进阶：CDN / 对象存储分发大文件

### 9.1 适用场景

- 客户端分布全国/全球，自建机器带宽撑不住。
- 单文件 700MB+，ScP 上传慢，CDN 推送一次到处都快。

### 9.2 关键约束

客户端**禁止 follow 3xx**，所以不能用"短链"或重定向型 CDN，必须返回直链 200。
推荐组合：

- `latest.json` 仍由你自己服务器（HTTPS）托管。
- `assets[].url` 直接指向对象存储的公开直链（如 `https://nini-releases.oss-cn-hangzhou.aliyuncs.com/stable/Nini-0.1.2-Setup.exe`）。

但是！**客户端会校验 asset URL 与 base URL 同域**（见 `manifest.py:validate_asset_url` 的 `asset_url.netloc != source_url.netloc`）。所以**目前架构下还不能跨域**。要么：

1. 用 CDN 反向代理同域路径（如 Caddy + `reverse_proxy /downloads/* https://oss/...`），让客户端看到的还是同一个域名。
2. 或等仓库后续放开同域限制（请关注 `add-in-app-updater` 后续 change）。

最简方案：用 Caddy 在 `update.example.com` 下做路径反代到对象存储：

```caddyfile
update.example.com {
    handle_path /downloads/* {
        reverse_proxy https://nini-releases.oss-cn-hangzhou.aliyuncs.com {
            header_up Host {http.reverse_proxy.upstream.hostport}
        }
    }
    handle {
        reverse_proxy 127.0.0.1:8080
    }
}
```

`latest.json` 里的 url 写 `https://update.example.com/downloads/Nini-0.1.2-Setup.exe`。

---

## 10. 进阶：Authenticode 代码签名（生产必做）

服务器无关，但流程上跟更新强绑定，所以放在这里提一下：

1. 申请 EV 或 OV Code Signing 证书（DigiCert / Sectigo / GlobalSign）。
2. 在打包流水线里用 `signtool sign /tr ... /td sha256 /fd sha256 /a` 给 `nini.exe`、`nini-cli.exe`、`nini-updater.exe` 和最终的 `Nini-x.y.z-Setup.exe` 都签上。
3. 客户端默认开启 `NINI_UPDATE_SIGNATURE_CHECK_ENABLED=true`；建议把证书指纹写进 `NINI_UPDATE_SIGNATURE_ALLOWED_THUMBPRINTS`，比按 publisher CN 严格。
4. 测试期间可以临时设 `NINI_UPDATE_SIGNATURE_CHECK_ENABLED=false`，**生产环境绝对不要**。

---

## 11. 故障排查总流程图

当客户端报"更新失败"时按这个顺序查：

```
[1] 服务器进程在跑吗？
    sudo systemctl status nini-updates
    └── 不在跑 → restart，看 journalctl
[2] 端口能从外网访问吗？
    curl -I http://你的IP:8080/nini/updates/stable/latest.json
    └── 超时 → 云厂商安全组；连接重置 → systemd 没监听
    └── 403 → chmod a+rX；404 → 文件名/路径
[3] latest.json 内容对吗？
    浏览器打开看 version、url、sha256
    └── 字段缺失 → 重新跑 generate_update_manifest.py
[4] .exe 能下载吗？
    curl -I 上面 JSON 里的 url
    └── 200 + 正确 size → OK
[5] 客户端配置对吗？
    检查 .env：BASE_URL 末尾 /、CHANNEL、ALLOW_INSECURE_HTTP
[6] 客户端日志怎么说？
    %APPDATA%\nini\logs 下找最新日志
    搜 "update" / "verify_failed" / "redirect"
[7] 都对但 Authenticode 报错？
    生产：检查证书是否被吊销 / 时间是否同步
    测试：临时关 NINI_UPDATE_SIGNATURE_CHECK_ENABLED
```

---

## 12. 速查表

### 服务器路径

| 路径 | 作用 |
|---|---|
| `/opt/nini-updates/public/nini/updates/stable/latest.json` | stable 渠道清单 |
| `/opt/nini-updates/public/nini/updates/stable/Nini-x.y.z-Setup.exe` | stable 渠道安装包 |
| `/opt/nini-updates/public/nini/updates/beta/...` | beta 渠道（同结构） |
| `/etc/systemd/system/nini-updates.service` | systemd 单元文件 |

### 客户端环境变量（最小集合）

```ini
NINI_UPDATE_BASE_URL=http://IP:8080/nini/updates/    # 末尾必须有 /
NINI_UPDATE_CHANNEL=stable
NINI_UPDATE_ALLOW_INSECURE_HTTP=true                 # 仅 HTTP 时
```

### 命令速查

```bash
# 服务器：服务管理
sudo systemctl {status|restart|stop|start} nini-updates
sudo journalctl -u nini-updates -f

# 本地：生成清单 + 上传
python scripts/generate_update_manifest.py --installer ... --version ... --base-url ... --output dist/latest.json [--allow-insecure-http]
scp dist/Nini-*.exe 用户@IP:/opt/nini-updates/public/nini/updates/stable/
scp dist/latest.json 用户@IP:/opt/nini-updates/public/nini/updates/stable/

# 验证
curl -I http://IP:8080/nini/updates/stable/latest.json
curl -I "<latest.json 里的 asset url>"
sha256sum dist/Nini-*.exe   # 对照 latest.json 里的 sha256
```

---

如有任何步骤卡住，按第 11 节流程图定位；仍解决不了，把 `journalctl -u nini-updates -n 100` 和客户端日志（`%APPDATA%\nini\logs`）一起贴出来排查。
