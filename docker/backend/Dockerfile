# 科研数据分析Web工具 - 后端Dockerfile
# 基于Python FastAPI + Celery

# ============================================
# 基础镜像
# ============================================
FROM python:3.11-slim AS base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1

# 设置工作目录
WORKDIR /app

# ============================================
# 依赖阶段
# ============================================
FROM base AS dependencies

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖管理工具
RUN pip install --no-cache-dir poetry

# 复制依赖定义文件
COPY pyproject.toml poetry.lock* ./

# 生成requirements.txt（不使用poetry虚拟环境）
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# ============================================
# 生产阶段
# ============================================
FROM base AS production

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非root用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 从依赖阶段复制requirements
COPY --from=dependencies /app/requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY ./app ./app
COPY ./alembic ./alembic
COPY ./alembic.ini ./

# 创建必要的目录并设置权限
RUN mkdir -p /app/logs /app/data /app/uploads && \
    chown -R appuser:appgroup /app

# 切换到非root用户
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================
# Celery Worker 阶段
# ============================================
FROM production AS celery-worker

# 启动Celery Worker
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-Q", "default,data_analysis,email"]

# ============================================
# Celery Beat 阶段（定时任务）
# ============================================
FROM production AS celery-beat

# 启动Celery Beat
CMD ["celery", "-A", "app.celery_app", "beat", "--loglevel=info"]
