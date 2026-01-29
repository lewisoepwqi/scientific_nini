/**
 * AI服务前端集成示例
 * 
 * 这些函数可以直接集成到React/Vue/Angular前端项目中
 */

const API_BASE_URL = 'http://localhost:8000/api/ai';

/**
 * ==================== 图表推荐 ====================
 */

/**
 * 获取图表推荐（非流式）
 * @param {Object} dataInfo - 数据信息
 * @returns {Promise<Object>} 推荐结果
 */
async function recommendChart(dataInfo) {
  const response = await fetch(`${API_BASE_URL}/chart/recommend`, {
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
 * 获取图表推荐（流式）
 * @param {Object} dataInfo - 数据信息
 * @param {Function} onChunk - 处理每个文本片段的回调
 * @param {Function} onComplete - 完成回调
 * @param {Function} onError - 错误回调
 */
async function recommendChartStream(dataInfo, onChunk, onComplete, onError) {
  try {
    const response = await fetch(`${API_BASE_URL}/chart/recommend/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dataInfo)
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // 保留不完整的行
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) onChunk(data.chunk);
            if (data.done) {
              onComplete?.();
              return;
            }
            if (data.error) {
              onError?.(data.error);
              return;
            }
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    }
    
    onComplete?.();
  } catch (error) {
    onError?.(error);
  }
}

/**
 * ==================== 数据分析 ====================
 */

/**
 * 分析数据（非流式）
 * @param {Object} analysisInfo - 分析信息
 * @returns {Promise<Object>} 分析结果
 */
async function analyzeData(analysisInfo) {
  const response = await fetch(`${API_BASE_URL}/data/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(analysisInfo)
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * 分析数据（流式）
 * @param {Object} analysisInfo - 分析信息
 * @param {Function} onChunk - 处理每个文本片段的回调
 * @param {Function} onComplete - 完成回调
 * @param {Function} onError - 错误回调
 */
async function analyzeDataStream(analysisInfo, onChunk, onComplete, onError) {
  try {
    const response = await fetch(`${API_BASE_URL}/data/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(analysisInfo)
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) onChunk(data.chunk);
            if (data.done) {
              onComplete?.();
              return;
            }
            if (data.error) {
              onError?.(data.error);
              return;
            }
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    }
    
    onComplete?.();
  } catch (error) {
    onError?.(error);
  }
}

/**
 * ==================== 实验设计 ====================
 */

/**
 * 设计实验（非流式）
 * @param {Object} experimentInfo - 实验信息
 * @returns {Promise<Object>} 设计结果
 */
async function designExperiment(experimentInfo) {
  const response = await fetch(`${API_BASE_URL}/experiment/design`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(experimentInfo)
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * 设计实验（流式）
 * @param {Object} experimentInfo - 实验信息
 * @param {Function} onChunk - 处理每个文本片段的回调
 * @param {Function} onComplete - 完成回调
 * @param {Function} onError - 错误回调
 */
async function designExperimentStream(experimentInfo, onChunk, onComplete, onError) {
  try {
    const response = await fetch(`${API_BASE_URL}/experiment/design/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(experimentInfo)
    });
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) onChunk(data.chunk);
            if (data.done) {
              onComplete?.();
              return;
            }
            if (data.error) {
              onError?.(data.error);
              return;
            }
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    }
    
    onComplete?.();
  } catch (error) {
    onError?.(error);
  }
}

/**
 * ==================== 统计建议 ====================
 */

/**
 * 获取统计方法建议
 * @param {Object} adviceInfo - 建议请求信息
 * @returns {Promise<Object>} 建议结果
 */
async function getStatisticalAdvice(adviceInfo) {
  const response = await fetch(`${API_BASE_URL}/statistical/advice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(adviceInfo)
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * ==================== 多组学分析 ====================
 */

/**
 * 分析多组学数据
 * @param {Object} omicsInfo - 组学数据信息
 * @returns {Promise<Object>} 分析结果
 */
async function analyzeOmics(omicsInfo) {
  const response = await fetch(`${API_BASE_URL}/omics/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(omicsInfo)
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * ==================== 成本管理 ====================
 */

/**
 * 获取成本统计
 * @returns {Promise<Object>} 成本统计
 */
async function getCostSummary() {
  const response = await fetch(`${API_BASE_URL}/cost/summary`);
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * 重置成本统计
 * @returns {Promise<Object>} 重置结果
 */
async function resetCostTracking() {
  const response = await fetch(`${API_BASE_URL}/cost/reset`, {
    method: 'POST'
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  return await response.json();
}

/**
 * ==================== React Hook 示例 ====================
 */

/**
 * React Hook: 使用流式AI分析
 * @param {Function} service - AI服务函数
 * @returns {Object} 状态和控制器
 */
function useStreamingAI(service) {
  const [result, setResult] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  
  const analyze = React.useCallback(async (params) => {
    setResult('');
    setIsLoading(true);
    setError(null);
    
    try {
      await service(
        params,
        (chunk) => setResult(prev => prev + chunk),
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
  }, [service]);
  
  return { result, isLoading, error, analyze };
}

/**
 * ==================== 使用示例 ====================
 */

// 示例1：图表推荐
async function exampleChartRecommendation() {
  const dataInfo = {
    data_description: '包含100个样本的基因表达数据',
    data_sample: `SampleID,GeneA,GeneB,Group
S001,2.5,3.1,Control
S002,2.8,3.5,Treatment
S003,2.3,2.9,Control`,
    data_types: {
      SampleID: 'string',
      GeneA: 'float',
      GeneB: 'float',
      Group: 'categorical'
    },
    statistics: {
      row_count: 100,
      column_count: 4
    },
    user_requirement: '比较不同组的基因表达差异'
  };
  
  try {
    const result = await recommendChart(dataInfo);
    console.log('推荐图表:', result.primary_recommendation);
  } catch (error) {
    console.error('错误:', error);
  }
}

// 示例2：流式数据分析
async function exampleStreamingAnalysis() {
  const analysisInfo = {
    context: '研究药物对基因表达的影响',
    data_description: 'RNA-seq数据，包含对照组和治疗组',
    statistics: {
      control_mean: 2.5,
      treatment_mean: 3.2,
      p_value: 0.003
    },
    question: '结果有什么统计学意义？'
  };
  
  await analyzeDataStream(
    analysisInfo,
    (chunk) => {
      // 实时更新UI
      document.getElementById('analysis-result').innerHTML += chunk;
    },
    () => {
      console.log('分析完成');
    },
    (error) => {
      console.error('分析错误:', error);
    }
  );
}

// 示例3：实验设计
async function exampleExperimentDesign() {
  const experimentInfo = {
    background: '研究新药对肿瘤生长的抑制效果',
    objective: '评估药物疗效',
    study_type: '随机对照试验',
    primary_endpoint: '肿瘤体积变化',
    effect_size: 0.5,
    alpha: 0.05,
    power: 0.8,
    test_type: 'two-sided',
    num_groups: 2
  };
  
  try {
    const result = await designExperiment(experimentInfo);
    console.log('实验设计:', result.design);
  } catch (error) {
    console.error('错误:', error);
  }
}

// 导出所有函数
export {
  recommendChart,
  recommendChartStream,
  analyzeData,
  analyzeDataStream,
  designExperiment,
  designExperimentStream,
  getStatisticalAdvice,
  analyzeOmics,
  getCostSummary,
  resetCostTracking,
  useStreamingAI
};
