# AI服务集成指南

## 快速集成

### 1. 启动AI服务

```bash
# 克隆代码
cd ai_service

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 OPENAI_API_KEY

# 启动服务
python -m ai_service.main
```

服务将在 `http://localhost:8000` 启动

### 2. 前端配置

```javascript
// config.js
const AI_SERVICE_URL = 'http://localhost:8000/api/ai';

export { AI_SERVICE_URL };
```

### 3. 安装HTTP客户端

```bash
# 如果使用axios
npm install axios

# 如果使用fetch（原生，无需安装）
```

## 功能集成

### 智能图表推荐

#### 场景：用户上传Excel后自动推荐图表

```javascript
// services/aiService.js
import { AI_SERVICE_URL } from '../config';

/**
 * 获取图表推荐
 * @param {Object} dataInfo - 数据信息
 * @returns {Promise<Object>} 推荐结果
 */
export async function getChartRecommendation(dataInfo) {
  const response = await fetch(`${AI_SERVICE_URL}/chart/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataInfo)
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * 流式获取图表推荐
 * @param {Object} dataInfo - 数据信息
 * @param {Function} onChunk - 处理文本片段的回调
 */
export async function getChartRecommendationStream(dataInfo, onChunk) {
  const response = await fetch(`${AI_SERVICE_URL}/chart/recommend/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataInfo)
  });
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    const lines = text.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.chunk) onChunk(data.chunk);
      }
    }
  }
}
```

```javascript
// components/ChartRecommendation.jsx (React)
import React, { useState } from 'react';
import { getChartRecommendation } from '../services/aiService';

function ChartRecommendation({ excelData }) {
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const handleRecommend = async () => {
    setLoading(true);
    
    try {
      // 准备数据信息
      const dataInfo = {
        data_description: excelData.description,
        data_sample: excelData.getSample(5),  // 前5行
        data_types: excelData.getColumnTypes(),
        statistics: excelData.getStatistics(),
        user_requirement: ''  // 可选
      };
      
      const result = await getChartRecommendation(dataInfo);
      setRecommendation(result);
      
    } catch (error) {
      console.error('图表推荐失败:', error);
      alert('推荐失败，请重试');
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="chart-recommendation">
      <button onClick={handleRecommend} disabled={loading}>
        {loading ? '分析中...' : '智能推荐图表'}
      </button>
      
      {recommendation && (
        <div className="recommendation-result">
          <h3>推荐图表：{recommendation.primary_recommendation.chart_name_cn}</h3>
          <p>置信度：{recommendation.primary_recommendation.confidence}</p>
          <p>推荐理由：{recommendation.primary_recommendation.reasoning}</p>
          
          <h4>可视化建议：</h4>
          <ul>
            {recommendation.visualization_tips.map((tip, i) => (
              <li key={i}>{tip}</li>
            ))}
          </ul>
          
          <h4>注意事项：</h4>
          <ul>
            {recommendation.pitfalls_to_avoid.map((pitfall, i) => (
              <li key={i}>{pitfall}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ChartRecommendation;
```

### AI辅助数据分析

#### 场景：用户查看统计结果后请求AI解读

```javascript
// services/aiService.js

/**
 * 分析数据（流式）
 * @param {Object} analysisInfo - 分析信息
 * @param {Function} onChunk - 处理文本片段
 * @param {Function} onComplete - 完成回调
 * @param {Function} onError - 错误回调
 */
export async function analyzeDataStream(analysisInfo, onChunk, onComplete, onError) {
  try {
    const response = await fetch(`${AI_SERVICE_URL}/data/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysisInfo)
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        onComplete?.();
        break;
      }
      
      const text = decoder.decode(value);
      const lines = text.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) onChunk(data.chunk);
            if (data.error) onError?.(data.error);
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    }
  } catch (error) {
    onError?.(error);
  }
}
```

```javascript
// components/AIAnalysisPanel.jsx (React)
import React, { useState, useRef } from 'react';
import { analyzeDataStream } from '../services/aiService';

function AIAnalysisPanel({ dataContext, statistics }) {
  const [analysis, setAnalysis] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const analysisRef = useRef('');
  
  const handleAnalyze = async () => {
    setAnalysis('');
    analysisRef.current = '';
    setIsAnalyzing(true);
    
    const analysisInfo = {
      context: dataContext,
      data_description: '用户当前查看的数据',
      statistics: statistics,
      question: '请解读这些统计结果'
    };
    
    await analyzeDataStream(
      analysisInfo,
      (chunk) => {
        // 实时更新分析结果
        analysisRef.current += chunk;
        setAnalysis(analysisRef.current);
      },
      () => {
        setIsAnalyzing(false);
      },
      (error) => {
        console.error('分析错误:', error);
        setIsAnalyzing(false);
        alert('分析失败，请重试');
      }
    );
  };
  
  return (
    <div className="ai-analysis-panel">
      <div className="panel-header">
        <h3>AI 数据分析</h3>
        <button onClick={handleAnalyze} disabled={isAnalyzing}>
          {isAnalyzing ? '分析中...' : '开始分析'}
        </button>
      </div>
      
      <div className="analysis-content">
        {analysis ? (
          <div className="analysis-text">
            {analysis.split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
        ) : (
          <p className="placeholder">点击"开始分析"获取AI解读</p>
        )}
      </div>
      
      {isAnalyzing && (
        <div className="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
      )}
    </div>
  );
}

export default AIAnalysisPanel;
```

### 实验设计助手

#### 场景：用户在实验设计页面获取AI建议

```javascript
// components/ExperimentDesigner.jsx (React)
import React, { useState } from 'react';
import { designExperiment } from '../services/aiService';

function ExperimentDesigner() {
  const [formData, setFormData] = useState({
    background: '',
    objective: '',
    studyType: '随机对照试验',
    primaryEndpoint: '',
    effectSize: 0.5,
    alpha: 0.05,
    power: 0.8,
    numGroups: 2
  });
  
  const [design, setDesign] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const result = await designExperiment({
        background: formData.background,
        objective: formData.objective,
        study_type: formData.studyType,
        primary_endpoint: formData.primaryEndpoint,
        effect_size: parseFloat(formData.effectSize),
        alpha: parseFloat(formData.alpha),
        power: parseFloat(formData.power),
        num_groups: parseInt(formData.numGroups)
      });
      
      setDesign(result.design);
    } catch (error) {
      console.error('实验设计失败:', error);
      alert('设计失败，请重试');
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="experiment-designer">
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>研究背景</label>
          <textarea
            value={formData.background}
            onChange={(e) => setFormData({...formData, background: e.target.value})}
            placeholder="描述研究背景..."
            required
          />
        </div>
        
        <div className="form-group">
          <label>研究目的</label>
          <textarea
            value={formData.objective}
            onChange={(e) => setFormData({...formData, objective: e.target.value})}
            placeholder="描述研究目的..."
            required
          />
        </div>
        
        <div className="form-row">
          <div className="form-group">
            <label>主要终点指标</label>
            <input
              type="text"
              value={formData.primaryEndpoint}
              onChange={(e) => setFormData({...formData, primaryEndpoint: e.target.value})}
              placeholder="如：肿瘤体积变化"
              required
            />
          </div>
          
          <div className="form-group">
            <label>预期效应量 (Cohen's d)</label>
            <input
              type="number"
              step="0.1"
              value={formData.effectSize}
              onChange={(e) => setFormData({...formData, effectSize: e.target.value})}
            />
          </div>
        </div>
        
        <div className="form-row">
          <div className="form-group">
            <label>显著性水平 (α)</label>
            <select
              value={formData.alpha}
              onChange={(e) => setFormData({...formData, alpha: e.target.value})}
            >
              <option value="0.05">0.05</option>
              <option value="0.01">0.01</option>
            </select>
          </div>
          
          <div className="form-group">
            <label>统计功效 (1-β)</label>
            <select
              value={formData.power}
              onChange={(e) => setFormData({...formData, power: e.target.value})}
            >
              <option value="0.8">0.8</option>
              <option value="0.9">0.9</option>
            </select>
          </div>
        </div>
        
        <button type="submit" disabled={loading}>
          {loading ? '设计中...' : '获取实验设计建议'}
        </button>
      </form>
      
      {design && (
        <div className="design-result">
          <h3>实验设计建议</h3>
          <div className="design-content">
            {design.split('\n').map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ExperimentDesigner;
```

## React Hook 封装

```javascript
// hooks/useAI.js
import { useState, useCallback } from 'react';

/**
 * 使用流式AI服务
 * @param {Function} streamFunction - 流式服务函数
 * @returns {Object} 状态和控制器
 */
export function useAIStream(streamFunction) {
  const [result, setResult] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const execute = useCallback(async (params) => {
    setResult('');
    setIsLoading(true);
    setError(null);
    
    let accumulated = '';
    
    try {
      await streamFunction(
        params,
        (chunk) => {
          accumulated += chunk;
          setResult(accumulated);
        },
        () => setIsLoading(false),
        (err) => {
          setError(err);
          setIsLoading(false);
        }
      );
    } catch (err) {
      setError(err);
      setIsLoading(false);
    }
    
    return accumulated;
  }, [streamFunction]);
  
  const reset = useCallback(() => {
    setResult('');
    setIsLoading(false);
    setError(null);
  }, []);
  
  return { result, isLoading, error, execute, reset };
}
```

## 使用示例

```javascript
// App.jsx
import React from 'react';
import { useAIStream } from './hooks/useAI';
import { analyzeDataStream } from './services/aiService';

function App() {
  const { result, isLoading, error, execute } = useAIStream(analyzeDataStream);
  
  const handleAnalyze = async () => {
    await execute({
      context: '研究背景...',
      data_description: '数据描述...',
      statistics: { /* 统计数据 */ },
      question: '分析目标...'
    });
  };
  
  return (
    <div>
      <button onClick={handleAnalyze} disabled={isLoading}>
        {isLoading ? '分析中...' : 'AI分析'}
      </button>
      
      {error && <div className="error">{error.message}</div>}
      
      <div className="result">
        {result}
      </div>
    </div>
  );
}
```

## 错误处理

```javascript
// utils/errorHandler.js

/**
 * 处理AI服务错误
 * @param {Error} error - 错误对象
 * @returns {string} 用户友好的错误消息
 */
export function handleAIError(error) {
  if (error.message.includes('RateLimitError')) {
    return '请求过于频繁，请稍后再试';
  }
  if (error.message.includes('TimeoutError')) {
    return '请求超时，请重试';
  }
  if (error.message.includes('AuthenticationError')) {
    return 'API密钥无效，请联系管理员';
  }
  return '服务暂时不可用，请稍后重试';
}
```

## 成本显示

```javascript
// components/CostDisplay.jsx
import React, { useState, useEffect } from 'react';

function CostDisplay() {
  const [costSummary, setCostSummary] = useState(null);
  
  useEffect(() => {
    fetchCostSummary();
  }, []);
  
  const fetchCostSummary = async () => {
    try {
      const response = await fetch(`${AI_SERVICE_URL}/cost/summary`);
      const data = await response.json();
      setCostSummary(data);
    } catch (error) {
      console.error('获取成本统计失败:', error);
    }
  };
  
  if (!costSummary) return null;
  
  return (
    <div className="cost-display">
      <span>今日AI调用成本: ${costSummary.total_cost_usd.toFixed(2)}</span>
    </div>
  );
}

export default CostDisplay;
```

## 最佳实践

### 1. 防抖处理

```javascript
import { useCallback } from 'react';
import { debounce } from 'lodash';

const debouncedAnalyze = useCallback(
  debounce((params) => analyzeDataStream(params, ...), 500),
  []
);
```

### 2. 取消请求

```javascript
const abortController = new AbortController();

fetch(url, { signal: abortController.signal });

// 组件卸载时取消
useEffect(() => {
  return () => abortController.abort();
}, []);
```

### 3. 结果缓存

```javascript
import { useQuery } from '@tanstack/react-query';

const { data, isLoading } = useQuery({
  queryKey: ['chartRecommendation', dataId],
  queryFn: () => getChartRecommendation(dataInfo),
  staleTime: 5 * 60 * 1000  // 5分钟
});
```

## 常见问题

### Q: 流式响应如何处理特殊字符？

A: 使用 `TextDecoder` 正确处理UTF-8编码

### Q: 如何处理网络中断？

A: 实现自动重试机制，或在UI中提供重试按钮

### Q: 如何限制请求频率？

A: 使用防抖和节流，或在后端配置速率限制

### Q: 如何保护API Key？

A: API Key只存储在服务端，前端通过代理访问
