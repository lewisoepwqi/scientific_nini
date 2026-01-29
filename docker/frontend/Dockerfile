# 科研数据分析Web工具 - 前端Dockerfile
# 基于React + TypeScript + Vite

# ============================================
# 构建阶段 (Build Stage)
# ============================================
FROM node:20-alpine AS builder

# 设置工作目录
WORKDIR /app

# 设置npm镜像加速（国内服务器建议）
# RUN npm config set registry https://registry.npmmirror.com

# 先复制依赖文件（利用Docker缓存层）
COPY package*.json ./

# 安装依赖
RUN npm ci --only=production=false

# 复制源代码
COPY . .

# 构建应用
RUN npm run build

# ============================================
# 生产阶段 (Production Stage)
# ============================================
FROM nginx:alpine

# 安装必要的工具
RUN apk add --no-cache curl

# 复制自定义nginx配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 创建健康检查脚本
RUN echo '#!/bin/sh\ncurl -f http://localhost:80/health || exit 1' > /healthcheck.sh && \
    chmod +x /healthcheck.sh

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD /healthcheck.sh

# 暴露端口
EXPOSE 80

# 启动nginx
CMD ["nginx", "-g", "daemon off;"]
