#!/bin/bash
# ============================================
# 服务器初始化脚本
# 用于新服务器的初始化配置
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    log_error "请使用root权限运行此脚本"
    exit 1
fi

# ============================================
# 1. 系统更新
# ============================================
log_info "正在更新系统..."
apt-get update && apt-get upgrade -y

# ============================================
# 2. 安装基本工具
# ============================================
log_info "正在安装基本工具..."
apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# ============================================
# 3. 安装Docker
# ============================================
log_info "正在安装Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log_info "Docker安装完成"
else
    log_warn "Docker已安装，跳过..."
fi

# ============================================
# 4. 安装Docker Compose
# ============================================
log_info "正在安装Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    log_info "Docker Compose安装完成"
else
    log_warn "Docker Compose已安装，跳过..."
fi

# ============================================
# 5. 配置Docker（国内镜像加速）
# ============================================
log_info "正在配置Docker..."
mkdir -p /etc/docker

# 使用国内镜像加速（可选，根据服务器位置）
cat > /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF

systemctl restart docker
log_info "Docker配置完成"

# ============================================
# 6. 创建应用目录结构
# ============================================
log_info "正在创建应用目录..."
APP_DIR="/opt/research-app"
mkdir -p ${APP_DIR}/{backend,frontend,docker,scripts,logs,backups}
mkdir -p ${APP_DIR}/docker/{nginx/ssl,nginx/conf.d}
mkdir -p ${APP_DIR}/docker/init-scripts

# 创建非root用户用于部署
if ! id "deploy" &>/dev/null; then
    useradd -m -s /bin/bash deploy
    usermod -aG docker deploy
    log_info "创建deploy用户完成"
fi

# 设置目录权限
chown -R deploy:deploy ${APP_DIR}
chmod -R 755 ${APP_DIR}

log_info "目录结构创建完成: ${APP_DIR}"

# ============================================
# 7. 配置防火墙
# ============================================
log_info "正在配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    log_info "UFW防火墙配置完成"
fi

# ============================================
# 8. 配置自动安全更新
# ============================================
log_info "正在配置自动安全更新..."
apt-get install -y unattended-upgrades

cat > /etc/apt/apt.conf.d/50unattended-upgrades <<EOF
Unattended-Upgrade::Allowed-Origins {
    "\${distro_id}:\${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::InstallOnShutdown "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

log_info "自动安全更新配置完成"

# ============================================
# 9. 安装Certbot（用于SSL证书）
# ============================================
log_info "正在安装Certbot..."
apt-get install -y certbot python3-certbot-nginx

# 创建Certbot目录
mkdir -p /var/www/certbot

log_info "Certbot安装完成"

# ============================================
# 10. 配置时区
# ============================================
log_info "正在配置时区..."
timedatectl set-timezone Asia/Shanghai

# ============================================
# 11. 配置日志轮转
# ============================================
log_info "正在配置日志轮转..."
cat > /etc/logrotate.d/research-app <<EOF
/opt/research-app/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 deploy deploy
    sharedscripts
    postrotate
        /usr/bin/docker kill --signal="USR1" research_nginx 2>/dev/null || true
    endscript
}
EOF

log_info "日志轮转配置完成"

# ============================================
# 12. 创建系统服务
# ============================================
log_info "正在创建系统服务..."

cat > /etc/systemd/system/research-app.service <<EOF
[Unit]
Description=Research Data Analysis Web Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/research-app/docker
User=deploy
Group=deploy
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable research-app.service

log_info "系统服务创建完成"

# ============================================
# 完成
# ============================================
log_info "============================================"
log_info "服务器初始化完成！"
log_info "============================================"
log_info "应用目录: /opt/research-app"
log_info "部署用户: deploy"
log_info ""
log_info "下一步:"
log_info "1. 上传应用代码到 /opt/research-app"
log_info "2. 配置环境变量文件"
log_info "3. 运行部署脚本"
log_info "============================================"
