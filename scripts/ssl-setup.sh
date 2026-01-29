#!/bin/bash
# ============================================
# SSL证书配置脚本
# 用于申请和管理Let's Encrypt证书
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
DOCKER_DIR="/opt/research-app/docker"
NGINX_SSL_DIR="${DOCKER_DIR}/nginx/ssl"
CERTBOT_DIR="/var/www/certbot"

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 显示帮助
show_help() {
    cat <<EOF
SSL证书配置脚本

用法: $0 [命令] [选项]

命令:
    setup DOMAIN [EMAIL]    申请新证书
    renew                   续期证书
    force-renew             强制续期
    delete DOMAIN           删除证书
    list                    列出所有证书
    test                    测试续期
    auto-renew              配置自动续期

示例:
    $0 setup example.com admin@example.com
    $0 setup example.com www.example.com admin@example.com
    $0 renew
    $0 list
    $0 auto-renew

EOF
}

# 检查Certbot安装
check_certbot() {
    if ! command -v certbot &> /dev/null; then
        log_error "Certbot未安装，请先运行服务器初始化脚本"
        exit 1
    fi
}

# 检查域名
check_domain() {
    local domain=$1
    if [ -z "$domain" ]; then
        log_error "请提供域名"
        show_help
        exit 1
    fi
}

# 申请证书
cmd_setup() {
    local domains=()
    local email=""
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == *"@"* ]]; then
            email="$1"
        else
            domains+=("$1")
        fi
        shift
    done
    
    if [ ${#domains[@]} -eq 0 ]; then
        log_error "请至少提供一个域名"
        exit 1
    fi
    
    if [ -z "$email" ]; then
        email="admin@${domains[0]}"
        log_warn "未提供邮箱，使用默认: $email"
    fi
    
    log_step "申请SSL证书..."
    log_info "域名: ${domains[*]}"
    log_info "邮箱: $email"
    
    # 创建Certbot目录
    mkdir -p ${CERTBOT_DIR}
    
    # 停止Nginx释放80端口
    log_info "停止Nginx..."
    docker stop research_nginx 2>/dev/null || true
    
    # 构建Certbot参数
    local certbot_args=""
    for domain in "${domains[@]}"; do
        certbot_args="$certbot_args -d $domain"
    done
    
    # 申请证书
    log_info "正在申请证书..."
    certbot certonly --standalone \
        $certbot_args \
        --agree-tos \
        --non-interactive \
        --email $email \
        --preferred-challenges http
    
    # 复制证书到Nginx目录
    log_info "复制证书..."
    mkdir -p ${NGINX_SSL_DIR}
    
    local primary_domain=${domains[0]}
    cp /etc/letsencrypt/live/${primary_domain}/fullchain.pem ${NGINX_SSL_DIR}/
    cp /etc/letsencrypt/live/${primary_domain}/privkey.pem ${NGINX_SSL_DIR}/
    
    # 设置权限
    chmod 644 ${NGINX_SSL_DIR}/*.pem
    
    # 更新Nginx配置
    log_info "更新Nginx配置..."
    update_nginx_config "${domains[0]}"
    
    # 启动Nginx
    log_info "启动Nginx..."
    docker start research_nginx 2>/dev/null || docker-compose -f ${DOCKER_DIR}/docker-compose.yml up -d nginx
    
    log_info "SSL证书配置完成！"
    log_info "证书路径: ${NGINX_SSL_DIR}"
    log_info "过期时间: $(openssl x509 -in ${NGINX_SSL_DIR}/fullchain.pem -noout -dates | grep notAfter)"
}

# 更新Nginx配置
update_nginx_config() {
    local domain=$1
    local nginx_conf="${DOCKER_DIR}/nginx/conf.d/default.conf"
    
    # 备份原配置
    cp ${nginx_conf} ${nginx_conf}.bak
    
    # 替换域名
    sed -i "s/your-domain.com/${domain}/g" ${nginx_conf}
    sed -i "s/www.your-domain.com/www.${domain}/g" ${nginx_conf}
    
    log_info "Nginx配置已更新: ${domain}"
}

# 续期证书
cmd_renew() {
    log_step "续期SSL证书..."
    
    # 停止Nginx
    log_info "停止Nginx..."
    docker stop research_nginx 2>/dev/null || true
    
    # 续期证书
    log_info "正在续期证书..."
    certbot renew
    
    # 复制新证书
    log_info "复制新证书..."
    for cert_dir in /etc/letsencrypt/live/*/; do
        if [ -d "$cert_dir" ]; then
            domain=$(basename "$cert_dir")
            cp ${cert_dir}/fullchain.pem ${NGINX_SSL_DIR}/
            cp ${cert_dir}/privkey.pem ${NGINX_SSL_DIR}/
            log_info "已更新: $domain"
        fi
    done
    
    # 启动Nginx
    log_info "启动Nginx..."
    docker start research_nginx
    
    log_info "证书续期完成！"
}

# 强制续期
cmd_force_renew() {
    log_step "强制续期SSL证书..."
    
    # 停止Nginx
    docker stop research_nginx 2>/dev/null || true
    
    # 强制续期
    certbot renew --force-renewal
    
    # 复制新证书
    for cert_dir in /etc/letsencrypt/live/*/; do
        if [ -d "$cert_dir" ]; then
            domain=$(basename "$cert_dir")
            cp ${cert_dir}/fullchain.pem ${NGINX_SSL_DIR}/
            cp ${cert_dir}/privkey.pem ${NGINX_SSL_DIR}/
        fi
    done
    
    # 启动Nginx
    docker start research_nginx
    
    log_info "强制续期完成！"
}

# 删除证书
cmd_delete() {
    local domain=$1
    check_domain $domain
    
    log_step "删除SSL证书: $domain"
    
    read -p "确定要删除证书吗? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "操作已取消"
        exit 0
    fi
    
    certbot delete --cert-name $domain
    
    log_info "证书已删除"
}

# 列出证书
cmd_list() {
    log_step "SSL证书列表"
    certbot certificates
    
    # 显示证书文件
    if [ -d ${NGINX_SSL_DIR} ]; then
        echo ""
        log_info "Nginx SSL目录:"
        ls -la ${NGINX_SSL_DIR}
    fi
}

# 测试续期
cmd_test() {
    log_step "测试证书续期..."
    certbot renew --dry-run
}

# 配置自动续期
cmd_auto_renew() {
    log_step "配置自动续期..."
    
    # 创建续期脚本
    cat > /usr/local/bin/certbot-renew.sh <<'RENEW_SCRIPT'
#!/bin/bash
# 停止Nginx
docker stop research_nginx 2>/dev/null || true

# 续期证书
certbot renew --quiet

# 复制证书
for cert_dir in /etc/letsencrypt/live/*/; do
    if [ -d "$cert_dir" ]; then
        domain=$(basename "$cert_dir")
        cp ${cert_dir}/fullchain.pem /opt/research-app/docker/nginx/ssl/
        cp ${cert_dir}/privkey.pem /opt/research-app/docker/nginx/ssl/
    fi
done

# 启动Nginx
docker start research_nginx
RENEW_SCRIPT

    chmod +x /usr/local/bin/certbot-renew.sh
    
    # 添加crontab任务
    (crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/bin/certbot-renew.sh >> /var/log/certbot-renew.log 2>&1") | crontab -
    
    log_info "自动续期已配置"
    log_info "续期时间: 每天凌晨3点"
    log_info "日志文件: /var/log/certbot-renew.log"
}

# 主流程
case "${1:-}" in
    setup)
        shift
        check_certbot
        cmd_setup "$@"
        ;;
    renew)
        check_certbot
        cmd_renew
        ;;
    force-renew)
        check_certbot
        cmd_force_renew
        ;;
    delete)
        shift
        check_certbot
        cmd_delete "$@"
        ;;
    list)
        check_certbot
        cmd_list
        ;;
    test)
        check_certbot
        cmd_test
        ;;
    auto-renew)
        check_certbot
        cmd_auto_renew
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        log_error "未知命令: ${1:-}"
        show_help
        exit 1
        ;;
esac
