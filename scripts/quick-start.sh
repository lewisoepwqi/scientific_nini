#!/bin/bash
# ============================================
# 快速启动脚本
# 用于本地开发环境快速启动
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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
快速启动脚本

用法: $0 [命令]

命令:
    dev             启动开发环境（本地运行）
    docker-dev      使用Docker启动开发环境
    docker-prod     使用Docker启动生产环境
    stop            停止所有服务
    restart         重启服务
    logs            查看日志
    clean           清理Docker资源

示例:
    $0 dev          # 本地开发环境
    $0 docker-dev   # Docker开发环境
    $0 docker-prod  # Docker生产环境
    $0 stop         # 停止服务

EOF
}

# 启动开发环境
cmd_dev() {
    log_step "启动开发环境..."
    
    # 检查依赖
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装"
        exit 1
    fi
    
    if ! command -v node &> /dev/null; then
        log_error "Node.js未安装"
        exit 1
    fi
    
    # 启动后端
    log_info "启动后端服务..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000 &
    BACKEND_PID=$!
    cd ..
    
    # 启动前端
    log_info "启动前端服务..."
    cd frontend
    npm install
    npm run dev &
    FRONTEND_PID=$!
    cd ..
    
    log_info "开发环境已启动！"
    log_info "前端地址: http://localhost:5173"
    log_info "后端地址: http://localhost:8000"
    log_info "API文档: http://localhost:8000/docs"
    
    # 保存PID
    echo $BACKEND_PID > /tmp/research-backend.pid
    echo $FRONTEND_PID > /tmp/research-frontend.pid
    
    # 等待用户输入
    read -p "按Enter键停止服务..."
    
    # 停止服务
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    rm -f /tmp/research-*.pid
}

# Docker开发环境
cmd_docker_dev() {
    log_step "启动Docker开发环境..."
    
    cd docker
    
    # 检查环境变量
    if [ ! -f .env ]; then
        log_warn "环境变量文件不存在，使用开发环境配置"
        cp .env.development .env
    fi
    
    # 启动服务（不包含Nginx）
    docker-compose up -d postgres redis backend
    
    log_info "等待数据库启动..."
    sleep 5
    
    # 执行数据库迁移
    log_info "执行数据库迁移..."
    docker-compose exec backend alembic upgrade head || true
    
    log_info "开发环境已启动！"
    log_info "后端API: http://localhost:8000"
    log_info "API文档: http://localhost:8000/docs"
    
    cd ..
}

# Docker生产环境
cmd_docker_prod() {
    log_step "启动Docker生产环境..."
    
    cd docker
    
    # 检查环境变量
    if [ ! -f .env ]; then
        log_error "环境变量文件不存在，请先配置 .env"
        exit 1
    fi
    
    # 构建并启动所有服务
    docker-compose up -d --build
    
    log_info "等待服务启动..."
    sleep 10
    
    # 执行数据库迁移
    log_info "执行数据库迁移..."
    docker-compose exec backend alembic upgrade head || true
    
    # 显示状态
    docker-compose ps
    
    log_info "生产环境已启动！"
    
    cd ..
}

# 停止服务
cmd_stop() {
    log_step "停止服务..."
    
    cd docker
    docker-compose down
    cd ..
    
    # 停止本地进程
    if [ -f /tmp/research-backend.pid ]; then
        kill $(cat /tmp/research-backend.pid) 2>/dev/null || true
        rm -f /tmp/research-backend.pid
    fi
    
    if [ -f /tmp/research-frontend.pid ]; then
        kill $(cat /tmp/research-frontend.pid) 2>/dev/null || true
        rm -f /tmp/research-frontend.pid
    fi
    
    log_info "服务已停止"
}

# 重启服务
cmd_restart() {
    cmd_stop
    sleep 2
    cmd_docker_prod
}

# 查看日志
cmd_logs() {
    cd docker
    docker-compose logs -f ${2:-}
    cd ..
}

# 清理资源
cmd_clean() {
    log_step "清理Docker资源..."
    
    cd docker
    docker-compose down -v
    cd ..
    
    docker system prune -af --volumes
    
    log_info "清理完成"
}

# 主流程
case "${1:-}" in
    dev)
        cmd_dev
        ;;
    docker-dev)
        cmd_docker_dev
        ;;
    docker-prod)
        cmd_docker_prod
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        shift
        cmd_logs "$@"
        ;;
    clean)
        cmd_clean
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
