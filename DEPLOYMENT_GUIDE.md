# 科研数据分析Web工具 - 完整部署指南

> 为你的女朋友打造的专属科研数据分析平台部署文档

## 目录

1. [准备工作](#准备工作)
2. [服务器购买与配置](#服务器购买与配置)
3. [域名购买与配置](#域名购买与配置)
4. [服务器初始化](#服务器初始化)
5. [应用部署](#应用部署)
6. [SSL证书配置](#ssl证书配置)
7. [日常维护](#日常维护)
8. [故障排查](#故障排查)
9. [项目文件结构](#项目文件结构)

---

## 准备工作

### 你需要准备

| 项目 | 说明 | 费用 |
|------|------|------|
| 云服务器 | 推荐2核4G起步 | ¥200-500/年 |
| 域名 | 推荐.com/.cn后缀 | ¥50-100/年 |
| OpenAI API Key | 用于AI功能 | 按量付费 |

### 推荐云服务商

- **国内**: 阿里云、腾讯云、华为云（需要备案）
- **国外**: Vultr、DigitalOcean、Linode（无需备案）

### 推荐服务器配置

```
最低配置: 2核CPU / 4GB内存 / 50GB SSD / 3Mbps带宽
推荐配置: 4核CPU / 8GB内存 / 100GB SSD / 5Mbps带宽
```

---

## 服务器购买与配置

### 1. 购买服务器（以阿里云为例）

1. 访问 [阿里云官网](https://www.aliyun.com/)
2. 选择 "云服务器ECS"
3. 选择配置：
   - **地域**: 选择离你最近的节点
   - **实例规格**: 2核4G（ecs.s6-c1m2.large）
   - **镜像**: Ubuntu 22.04 LTS 64位
   - **存储**: 50GB高效云盘
   - **带宽**: 3Mbps按固定带宽
4. 设置安全组规则：
   - 允许SSH (22端口)
   - 允许HTTP (80端口)
   - 允许HTTPS (443端口)

### 2. 获取服务器信息

购买完成后，记录以下信息：
- 公网IP地址
- 登录用户名（通常是root）
- 登录密码或密钥

---

## 域名购买与配置

### 1. 购买域名

推荐平台：
- [阿里云万网](https://wanwang.aliyun.com/)
- [腾讯云DNSPod](https://dnspod.cloud.tencent.com/)
- [GoDaddy](https://www.godaddy.com/)（国外）

### 2. 域名解析配置

登录域名控制台，添加以下DNS记录：

| 记录类型 | 主机记录 | 记录值 | 说明 |
|---------|---------|--------|------|
| A | @ | 你的服务器IP | 主域名 |
| A | www | 你的服务器IP | www子域名 |

### 3. 备案（国内服务器必需）

如果使用国内服务器，需要进行ICP备案：
1. 登录阿里云/腾讯云备案系统
2. 填写备案信息（需要身份证）
3. 等待审核（通常7-20个工作日）

---

## 服务器初始化

### 1. 连接服务器

```bash
# 使用密码登录
ssh root@你的服务器IP

# 或使用密钥登录
ssh -i /path/to/key.pem root@你的服务器IP
```

### 2. 运行初始化脚本

```bash
# 上传初始化脚本
scp scripts/server-init.sh root@你的服务器IP:/tmp/

# 在服务器上执行
ssh root@你的服务器IP
chmod +x /tmp/server-init.sh
/tmp/server-init.sh
```

初始化脚本会自动完成：
- ✅ 系统更新
- ✅ Docker和Docker Compose安装
- ✅ 防火墙配置
- ✅ 应用目录创建
- ✅ 自动安全更新配置
- ✅ Certbot安装

---

## 应用部署

### 1. 上传应用代码

```bash
# 方式1: 使用scp上传
scp -r backend frontend docker scripts root@你的服务器IP:/opt/research-app/

# 方式2: 使用git克隆（推荐）
ssh root@你的服务器IP
su - deploy
cd /opt/research-app
git clone https://github.com/yourusername/research-app.git .
```

### 2. 配置环境变量

```bash
ssh root@你的服务器IP
cd /opt/research-app/docker

# 复制环境变量模板
cp .env.example .env

# 编辑环境变量（必须修改以下值）
vim .env
```

**必须修改的配置项：**

```bash
# 数据库密码（生成命令: openssl rand -hex 16）
DB_PASSWORD=your-secure-password-here

# Redis密码
REDIS_PASSWORD=your-redis-password-here

# 应用密钥（生成命令: openssl rand -hex 32）
SECRET_KEY=your-super-secret-key

# OpenAI API Key
OPENAI_API_KEY=sk-your-openai-api-key

# 你的域名
DOMAIN=your-domain.com

# 管理员邮箱
ADMIN_EMAIL=admin@your-domain.com
```

### 3. 执行部署

```bash
# 切换到deploy用户
su - deploy
cd /opt/research-app

# 执行完整部署
./scripts/deploy.sh --full --backup -d your-domain.com

# 或者分步执行
./scripts/deploy.sh --full           # 完整部署
./scripts/deploy.sh --ssl -d your-domain.com  # 配置SSL
```

### 4. 验证部署

```bash
# 检查容器状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 测试API
curl http://localhost:8000/api/health
```

---

## SSL证书配置

### 自动配置（推荐）

部署脚本会自动申请Let's Encrypt免费SSL证书：

```bash
./scripts/deploy.sh --ssl -d your-domain.com
```

### 手动配置

```bash
# 停止Nginx
docker stop research_nginx

# 申请证书
certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# 复制证书
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/research-app/docker/nginx/ssl/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/research-app/docker/nginx/ssl/

# 重启Nginx
docker start research_nginx
```

### 自动续期

Let's Encrypt证书有效期为90天，已配置自动续期：

```bash
# 测试续期
certbot renew --dry-run

# 手动续期
certbot renew
```

---

## 日常维护

### 查看应用状态

```bash
# 查看所有容器
docker-compose ps

# 查看资源使用
docker stats

# 查看日志
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f nginx
```

### 更新应用

```bash
# 拉取最新代码
git pull origin main

# 执行更新部署
./scripts/deploy.sh --update
```

### 数据库备份

```bash
# 手动备份
./scripts/db-migrate.sh backup

# 查看备份列表
ls -la /opt/research-app/backups/

# 恢复数据库
./scripts/db-migrate.sh restore backups/backup_20240101.sql.gz
```

### 数据库迁移

```bash
# 查看迁移状态
./scripts/db-migrate.sh status

# 执行迁移
./scripts/db-migrate.sh migrate

# 回滚一个版本
./scripts/db-migrate.sh rollback head-1

# 创建新迁移
./scripts/db-migrate.sh create add_new_table
```

### 重启服务

```bash
# 重启所有服务
docker-compose restart

# 重启单个服务
docker-compose restart backend
docker-compose restart nginx
```

---

## 故障排查

### 容器无法启动

```bash
# 查看详细日志
docker-compose logs service_name

# 检查端口占用
netstat -tlnp | grep 80
netstat -tlnp | grep 443

# 释放端口
kill -9 $(lsof -t -i:80)
```

### 数据库连接失败

```bash
# 检查数据库容器
docker-compose ps postgres
docker-compose logs postgres

# 进入数据库容器
docker exec -it research_db psql -U research -d research_db

# 检查连接
docker exec research_backend python -c "import psycopg2; conn = psycopg2.connect('$DATABASE_URL'); print('OK')"
```

### SSL证书问题

```bash
# 检查证书
certbot certificates

# 重新申请
certbot delete --cert-name your-domain.com
certbot certonly --standalone -d your-domain.com

# 强制续期
certbot renew --force-renewal
```

### 内存不足

```bash
# 查看内存使用
free -h

# 清理Docker
docker system prune -a

# 重启服务释放内存
docker-compose restart
```

---

## 项目文件结构

```
/opt/research-app/
├── backend/                    # 后端代码
│   ├── app/                    # FastAPI应用
│   ├── alembic/                # 数据库迁移
│   ├── pyproject.toml          # Python依赖
│   └── Dockerfile              # 后端Dockerfile
├── frontend/                   # 前端代码
│   ├── src/                    # React源码
│   ├── dist/                   # 构建产物
│   ├── package.json            # Node依赖
│   ├── Dockerfile              # 前端Dockerfile
│   └── nginx.conf              # 前端Nginx配置
├── docker/                     # Docker配置
│   ├── docker-compose.yml      # 主Compose配置
│   ├── docker-compose.monitoring.yml  # 监控配置
│   ├── .env.example            # 环境变量模板
│   ├── .env.development        # 开发环境配置
│   ├── nginx/                  # Nginx配置
│   │   ├── nginx.conf          # 主配置
│   │   ├── conf.d/             # 站点配置
│   │   └── ssl/                # SSL证书
│   ├── init-scripts/           # 数据库初始化
│   │   └── 01-init-db.sql      # 初始化SQL
│   └── monitoring/             # 监控配置
│       ├── prometheus/
│       ├── grafana/
│       ├── loki/
│       └── promtail/
├── scripts/                    # 部署脚本
│   ├── server-init.sh          # 服务器初始化
│   ├── deploy.sh               # 应用部署
│   └── db-migrate.sh           # 数据库迁移
├── logs/                       # 日志目录
├── backups/                    # 备份目录
└── README.md                   # 项目说明
```

---

## 快速命令参考

```bash
# 服务器初始化（只需执行一次）
curl -fsSL https://your-repo/server-init.sh | bash

# 完整部署
./scripts/deploy.sh --full --backup -d your-domain.com

# 仅更新
./scripts/deploy.sh --update

# 查看状态
docker-compose ps
docker stats

# 查看日志
docker-compose logs -f [service]

# 数据库操作
./scripts/db-migrate.sh backup
./scripts/db-migrate.sh restore backup_file.sql.gz
./scripts/db-migrate.sh migrate

# 重启服务
docker-compose restart
docker-compose down && docker-compose up -d
```

---

## 安全建议

1. **定期更新系统**: `apt update && apt upgrade`
2. **使用强密码**: 数据库、Redis使用随机生成的强密码
3. **定期备份**: 数据库每日自动备份
4. **监控日志**: 定期检查异常访问
5. **限制SSH**: 使用密钥登录，禁用密码登录
6. **防火墙**: 只开放必要的端口

---

## 联系支持

如有问题，请检查：
1. 日志文件: `/opt/research-app/logs/`
2. Docker日志: `docker-compose logs`
3. 系统日志: `journalctl -u research-app`

---

**祝你和女朋友使用愉快！** 🎉
