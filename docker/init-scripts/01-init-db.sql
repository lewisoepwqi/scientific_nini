-- ============================================
-- 数据库初始化脚本
-- 科研数据分析Web工具
-- ============================================

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- 用于全文搜索

-- 创建自定义类型
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'analysis_status') THEN
        CREATE TYPE analysis_status AS ENUM ('pending', 'processing', 'completed', 'failed');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'researcher', 'viewer');
    END IF;
END
$$;

-- 创建更新时间的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 创建用户表
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role user_role DEFAULT 'researcher',
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    avatar_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITH TIME ZONE
);

-- 用户表更新时间触发器
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建数据集表
CREATE TABLE IF NOT EXISTS datasets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    file_type VARCHAR(50),
    row_count INTEGER,
    column_count INTEGER,
    column_info JSONB,  -- 存储列信息
    sample_data JSONB,  -- 样本数据
    is_public BOOLEAN DEFAULT false,
    tags TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 数据集表更新时间触发器
DROP TRIGGER IF EXISTS update_datasets_updated_at ON datasets;
CREATE TRIGGER update_datasets_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建数据分析任务表
CREATE TABLE IF NOT EXISTS analysis_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    analysis_type VARCHAR(100) NOT NULL,  -- 分析类型：descriptive, correlation, clustering, etc.
    parameters JSONB,  -- 分析参数
    status analysis_status DEFAULT 'pending',
    progress INTEGER DEFAULT 0,  -- 进度百分比
    result_data JSONB,  -- 分析结果
    result_summary TEXT,  -- 结果摘要
    error_message TEXT,  -- 错误信息
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 分析任务表更新时间触发器
DROP TRIGGER IF EXISTS update_analysis_tasks_updated_at ON analysis_tasks;
CREATE TRIGGER update_analysis_tasks_updated_at
    BEFORE UPDATE ON analysis_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建AI对话记录表
CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,
    analysis_task_id UUID REFERENCES analysis_tasks(id) ON DELETE SET NULL,
    title VARCHAR(255),
    messages JSONB NOT NULL DEFAULT '[]',  -- 对话消息
    model VARCHAR(100) DEFAULT 'gpt-4',
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI对话表更新时间触发器
DROP TRIGGER IF EXISTS update_ai_conversations_updated_at ON ai_conversations;
CREATE TRIGGER update_ai_conversations_updated_at
    BEFORE UPDATE ON ai_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建可视化配置表
CREATE TABLE IF NOT EXISTS visualizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    analysis_task_id UUID REFERENCES analysis_tasks(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    chart_type VARCHAR(100) NOT NULL,  -- 图表类型
    config JSONB NOT NULL,  -- 图表配置
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 可视化表更新时间触发器
DROP TRIGGER IF EXISTS update_visualizations_updated_at ON visualizations;
CREATE TRIGGER update_visualizations_updated_at
    BEFORE UPDATE ON visualizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 系统配置表更新时间触发器
DROP TRIGGER IF EXISTS update_system_configs_updated_at ON system_configs;
CREATE TRIGGER update_system_configs_updated_at
    BEFORE UPDATE ON system_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);
CREATE INDEX IF NOT EXISTS idx_datasets_created_at ON datasets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_user_id ON analysis_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_dataset_id ON analysis_tasks(dataset_id);
CREATE INDEX IF NOT EXISTS idx_analysis_tasks_status ON analysis_tasks(status);
CREATE INDEX IF NOT EXISTS idx_ai_conversations_user_id ON ai_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_visualizations_user_id ON visualizations(user_id);

-- 全文搜索索引
CREATE INDEX IF NOT EXISTS idx_datasets_name_trgm ON datasets USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_datasets_description_trgm ON datasets USING gin (description gin_trgm_ops);

-- 插入默认系统配置
INSERT INTO system_configs (key, value, description) VALUES
    ('max_file_size', '104857600', '最大文件上传大小（字节）'),
    ('allowed_extensions', 'csv,xlsx,xls,json,txt', '允许上传的文件扩展名'),
    ('max_analysis_concurrency', '3', '最大并发分析任务数'),
    ('ai_model_default', 'gpt-4', '默认AI模型'),
    ('enable_registration', 'true', '是否允许用户注册')
ON CONFLICT (key) DO NOTHING;

-- 创建视图：用户统计
CREATE OR REPLACE VIEW user_statistics AS
SELECT 
    u.id,
    u.username,
    u.email,
    u.role,
    u.created_at,
    COUNT(DISTINCT d.id) as dataset_count,
    COUNT(DISTINCT at.id) as analysis_count,
    COUNT(DISTINCT ac.id) as conversation_count
FROM users u
LEFT JOIN datasets d ON u.id = d.user_id
LEFT JOIN analysis_tasks at ON u.id = at.user_id
LEFT JOIN ai_conversations ac ON u.id = ac.user_id
GROUP BY u.id, u.username, u.email, u.role, u.created_at;

-- 创建视图：分析统计
CREATE OR REPLACE VIEW analysis_statistics AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as total_tasks,
    COUNT(*) FILTER (WHERE status = 'completed') as completed_tasks,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_tasks,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (WHERE status = 'completed') as avg_duration_seconds
FROM analysis_tasks
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;

-- 注释
COMMENT ON TABLE users IS '用户表';
COMMENT ON TABLE datasets IS '数据集表';
COMMENT ON TABLE analysis_tasks IS '数据分析任务表';
COMMENT ON TABLE ai_conversations IS 'AI对话记录表';
COMMENT ON TABLE visualizations IS '可视化配置表';
COMMENT ON TABLE system_configs IS '系统配置表';
