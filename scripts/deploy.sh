#!/bin/bash
# ============================================
# 应用部署脚本
# 用于部署或更新应用
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
APP_DIR="/opt/research-app"
DOCKER_DIR="${APP_DIR}/docker"
BACKUP_DIR="${APP_DIR}/backups"
LOG_FILE="${APP_DIR}/logs/deploy.log"

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a ${LOG_FILE}
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a ${LOG_FILE}
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a ${LOG_FILE}
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1" | tee -a ${LOG_FILE}
}

# 确保日志目录存在
mkdir -p $(dirname ${LOG_FILE})

# ============================================
# 显示帮助
# ============================================
show_help() {
    cat <<EOF
科研数据分析Web工具 - 部署脚本

用法: $0 [选项]

选项:
    -h, --help          显示帮助信息
    -f, --full          完整部署（包含数据库迁移）
    -u, --update        仅更新应用（不执行迁移）
    -b, --backup        部署前备份数据库
    -s, --ssl           申请/更新SSL证书
    -c, --cleanup       清理旧镜像和容器
    -d, --domain DOMAIN 指定域名
    -e, --env FILE      指定环境变量文件

示例:
    $0 --full --backup              # 完整部署并备份
    $0 --update                     # 仅更新应用
    $0 --ssl -d example.com         # 申请SSL证书
    $0 --full -e .env.production    # 使用指定环境文件

EOF
}

# ============================================
# 解析参数
# ============================================
FULL_DEPLOY=false
UPDATE_ONLY=false
BACKUP=false
SSL_SETUP=false
CLEANUP=false
DOMAIN=""
ENV_FILE=".env"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--full)
            FULL_DEPLOY=true
            shift
            ;;
        -u|--update)
            UPDATE_ONLY=true
            shift
            ;;
        -b|--backup)
            BACKUP=true
            shift
            ;;
        -s|--ssl)
            SSL_SETUP=true
            shift
            ;;
        -c|--cleanup)
            CLEANUP=true
            shift
            ;;
        -d|--domain)
            DOMAIN="$2"
            shift 2
            ;;
        -e|--env)
            ENV_FILE="$2"
            shift 2
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# ============================================
# 前置检查
# ============================================
log_step "执行前置检查..."

# 检查Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker未安装，请先运行服务器初始化脚本"
    exit 1
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose未安装"
    exit 1
fi

# 检查环境变量文件
if [ ! -f "${DOCKER_DIR}/${ENV_FILE}" ]; then
    log_warn "环境变量文件不存在: ${DOCKER_DIR}/${ENV_FILE}"
    log_info "请从 .env.example 创建环境变量文件"
    exit 1
fi

# 加载环境变量
export $(grep -v '^#' ${DOCKER_DIR}/${ENV_FILE} | xargs)

log_info "前置检查通过"

# ============================================
# 备份数据库
# ============================================
backup_database() {
    if [ "$BACKUP" = false ]; then
        return
    fi

    log_step "备份数据库..."
    
    BACKUP_FILE="${BACKUP_DIR}/backup_$(date +%Y%m%d_%H%M%S).sql"
    mkdir -p ${BACKUP_DIR}
    
    # 检查数据库容器是否运行
    if docker ps | grep -q research_db; then
        docker exec research_db pg_dump -U ${DB_USER:-research} ${DB_NAME:-research_db} > ${BACKUP_FILE}
        log_info "数据库备份完成: ${BACKUP_FILE}"
    else
        log_warn "数据库容器未运行，跳过备份"
    fi
}

# ============================================
# SSL证书申请
# ============================================
setup_ssl() {
    if [ "$SSL_SETUP" = false ]; then
        return
    fi

    log_step "配置SSL证书..."
    
    if [ -z "$DOMAIN" ]; then
        log_error "请使用 -d 参数指定域名"
        exit 1
    fi

    # 停止Nginx（释放80端口）
    docker stop research_nginx 2>/dev/null || true
    
    # 申请证书
    certbot certonly --standalone \
        -d ${DOMAIN} \
        -d www.${DOMAIN} \
        --agree-tos \
        --non-interactive \
        --email admin@${DOMAIN} \
        --preferred-challenges http
    
    # 复制证书到Nginx目录
    mkdir -p ${DOCKER_DIR}/nginx/ssl
    cp /etc/letsencrypt/live/${DOMAIN}/fullchain.pem ${DOCKER_DIR}/nginx/ssl/
    cp /etc/letsencrypt/live/${DOMAIN}/privkey.pem ${DOCKER_DIR}/nginx/ssl/
    
    # 设置权限
    chmod 644 ${DOCKER_DIR}/nginx/ssl/*.pem
    
    log_info "SSL证书配置完成"
}

# ============================================
# 清理旧资源
# ============================================
cleanup() {
    if [ "$CLEANUP" = false ]; then
        return
    fi

    log_step "清理旧资源..."
    
    # 清理未使用的镜像
    docker image prune -af --filter "until=168h"
    
    # 清理未使用的卷
    docker volume prune -f
    
    # 清理构建缓存
    docker builder prune -f
    
    log_info "清理完成"
}

# ============================================
# 部署应用
# ============================================
deploy() {
    log_step "开始部署应用..."
    
    cd ${DOCKER_DIR}
    
    # 拉取最新代码（如果使用git）
    if [ -d "${APP_DIR}/.git" ]; then
        log_info "拉取最新代码..."
        cd ${APP_DIR}
        git pull origin main
        cd ${DOCKER_DIR}
    fi
    
    # 构建镜像
    log_info "构建Docker镜像..."
    docker-compose build --no-cache
    
    # 停止旧容器
    log_info "停止旧容器..."
    docker-compose down
    
    # 启动服务
    log_info "启动服务..."
    docker-compose up -d
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 10
    
    # 检查服务状态
    log_info "检查服务状态..."
    docker-compose ps
    
    log_info "应用部署完成"
}

# ============================================
# 数据库迁移
# ============================================
run_migrations() {
    if [ "$FULL_DEPLOY" = false ]; then
        return
    fi

    log_step "执行数据库迁移..."
    
    # 等待数据库就绪
    log_info "等待数据库就绪..."
    sleep 5
    
    # 执行迁移
    docker exec research_backend alembic upgrade head
    
    log_info "数据库迁移完成"
}

# ============================================
# 健康检查
# ============================================
health_check() {
    log_step "执行健康检查..."
    
    # 检查各个服务
    services=("research_db" "research_redis" "research_backend" "research_frontend" "research_nginx")
    
    for service in "${services[@]}"; do
        if docker ps | grep -q ${service}; then
            log_info "✓ ${service} 运行正常"
        else
            log_error "✗ ${service} 未运行"
        fi
    done
    
    # API健康检查
    API_URL="http://localhost:8000/api/health"
    if curl -sf ${API_URL} > /dev/null 2>&1; then
        log_info "✓ API健康检查通过"
    else
        log_warn "✗ API健康检查失败"
    fi
}

# ============================================
# 主流程
# ============================================
main() {
    echo "============================================" | tee -a ${LOG_FILE}
    echo "科研数据分析Web工具 - 部署脚本" | tee -a ${LOG_FILE}
    echo "============================================" | tee -a ${LOG_FILE}
    echo "部署时间: $(date)" | tee -a ${LOG_FILE}
    echo "============================================" | tee -a ${LOG_FILE}
    
    # 执行部署流程
    backup_database
    setup_ssl
    cleanup
    deploy
    run_migrations
    health_check
    
    echo "============================================" | tee -a ${LOG_FILE}
    log_info "部署完成！"
    echo "============================================" | tee -a ${LOG_FILE}
    
    # 显示访问地址
    if [ -n "$DOMAIN" ]; then
        log_info "应用地址: https://${DOMAIN}"
    else
        log_info "应用地址: http://$(curl -s ifconfig.me)"
    fi
}

# 执行主流程
main
