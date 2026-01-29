"""
FastAPI应用主入口
AI分析服务API
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_service.api.endpoints import router as ai_router
from ai_service.core.llm_client import LLMConfig, ModelProvider, get_llm_client


# 从环境变量读取配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # 启动时初始化
    print("Initializing AI Analysis Service...")
    
    # 配置LLM客户端
    config = LLMConfig(
        provider=ModelProvider.OPENAI,
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        temperature=0.3,
        max_tokens=4096,
        enable_cost_tracking=True
    )
    
    # 初始化全局LLM客户端
    llm_client = get_llm_client(config)
    print(f"LLM Client initialized with model: {OPENAI_MODEL}")
    
    yield
    
    # 关闭时清理
    print("Shutting down AI Analysis Service...")
    # 可以在这里添加清理逻辑


# 创建FastAPI应用
app = FastAPI(
    title="科研数据分析AI服务",
    description="提供智能图表推荐、数据分析、实验设计等AI能力",
    version="0.1.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(ai_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "科研数据分析AI服务",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量读取服务器配置
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        "ai_service.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
