#!/bin/bash
# ============================================
# 数据库迁移脚本
# ============================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# 显示帮助
show_help() {
    cat <<EOF
数据库迁移脚本

用法: $0 [命令] [选项]

命令:
    migrate             执行迁移（升级数据库）
    rollback [版本]     回滚到指定版本
    reset               重置数据库（危险！）
    create [名称]       创建新的迁移文件
    status              查看迁移状态
    backup              备份数据库
    restore [文件]      从备份恢复数据库

示例:
    $0 migrate                      # 执行所有待处理迁移
    $0 rollback head-1              # 回滚一个版本
    $0 create add_user_table        # 创建新迁移
    $0 backup                       # 备份数据库
    $0 restore backup_20240101.sql  # 恢复数据库

EOF
}

# 检查容器运行状态
check_container() {
    if ! docker ps | grep -q research_db; then
        log_error "数据库容器未运行，请先启动应用"
        exit 1
    fi
    
    if ! docker ps | grep -q research_backend; then
        log_error "后端容器未运行，请先启动应用"
        exit 1
    fi
}

# 执行迁移
cmd_migrate() {
    log_info "执行数据库迁移..."
    check_container
    
    docker exec research_backend alembic upgrade head
    
    log_info "迁移完成"
}

# 回滚
cmd_rollback() {
    local version=${1:-"-1"}
    log_info "回滚数据库到版本: ${version}"
    check_container
    
    docker exec research_backend alembic downgrade ${version}
    
    log_info "回滚完成"
}

# 重置数据库（危险）
cmd_reset() {
    log_warn "警告: 这将删除所有数据！"
    read -p "确定要继续吗? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        log_info "操作已取消"
        exit 0
    fi
    
    log_info "重置数据库..."
    check_container
    
    # 备份
    cmd_backup
    
    # 删除所有表
    docker exec research_db psql -U research -d research_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    
    # 重新执行迁移
    docker exec research_backend alembic upgrade head
    
    log_info "数据库重置完成"
}

# 创建新迁移
cmd_create() {
    local name=$1
    if [ -z "$name" ]; then
        log_error "请提供迁移名称"
        exit 1
    fi
    
    log_info "创建新迁移: ${name}"
    check_container
    
    docker exec research_backend alembic revision --autogenerate -m "${name}"
    
    log_info "迁移文件创建完成"
}

# 查看状态
cmd_status() {
    log_info "查看迁移状态..."
    check_container
    
    docker exec research_backend alembic current
    docker exec research_backend alembic history --verbose
}

# 备份数据库
cmd_backup() {
    log_info "备份数据库..."
    check_container
    
    BACKUP_DIR="/opt/research-app/backups"
    mkdir -p ${BACKUP_DIR}
    
    BACKUP_FILE="${BACKUP_DIR}/backup_$(date +%Y%m%d_%H%M%S).sql"
    
    docker exec research_db pg_dump -U research research_db > ${BACKUP_FILE}
    
    # 压缩备份
    gzip ${BACKUP_FILE}
    
    log_info "数据库备份完成: ${BACKUP_FILE}.gz"
    
    # 清理旧备份（保留30天）
    find ${BACKUP_DIR} -name "backup_*.sql.gz" -mtime +30 -delete
}

# 恢复数据库
cmd_restore() {
    local backup_file=$1
    if [ -z "$backup_file" ]; then
        log_error "请提供备份文件路径"
        exit 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "备份文件不存在: $backup_file"
        exit 1
    fi
    
    log_warn "警告: 这将覆盖现有数据！"
    read -p "确定要继续吗? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        log_info "操作已取消"
        exit 0
    fi
    
    log_info "恢复数据库..."
    check_container
    
    # 如果文件是压缩的，先解压
    if [[ $backup_file == *.gz ]]; then
        log_info "解压备份文件..."
        gunzip -c $backup_file > /tmp/restore.sql
        backup_file="/tmp/restore.sql"
    fi
    
    # 恢复数据库
    docker exec -i research_db psql -U research -d research_db < $backup_file
    
    # 清理临时文件
    rm -f /tmp/restore.sql
    
    log_info "数据库恢复完成"
}

# 主流程
case "${1:-}" in
    migrate)
        cmd_migrate
        ;;
    rollback)
        cmd_rollback $2
        ;;
    reset)
        cmd_reset
        ;;
    create)
        cmd_create $2
        ;;
    status)
        cmd_status
        ;;
    backup)
        cmd_backup
        ;;
    restore)
        cmd_restore $2
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
