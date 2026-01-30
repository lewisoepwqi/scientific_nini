import React, { useState } from 'react';
import { Calculator, Database, Play, Trash2, Download, ChevronDown, ChevronUp } from 'lucide-react';
import { useDatasetStore, useAnalysisStore, useUIStore } from '@store/index';
import { cn, formatNumber } from '@utils/helpers';
import { api } from '@services/api';
import type { StatisticalResult } from '../types';

interface AnalysisPageProps {
  className?: string;
}

const analysisTypes = [
  { id: 'descriptive', name: '描述性统计', description: '计算均值、标准差、分位数等' },
  { id: 'ttest', name: 't 检验', description: '比较两组数据的均值差异' },
  { id: 'anova', name: 'ANOVA', description: '比较多组数据的均值差异' },
  { id: 'correlation', name: '相关性分析', description: '计算变量间的相关系数' },
  { id: 'chisquare', name: '卡方检验', description: '检验分类变量的独立性' },
  { id: 'mannwhitney', name: 'Mann-Whitney U', description: '非参数检验两组差异' },
  { id: 'kruskal', name: 'Kruskal-Wallis', description: '非参数检验多组差异' },
];

export const AnalysisPage: React.FC<AnalysisPageProps> = ({ className }) => {
  const { currentDataset } = useDatasetStore();
  const { results, addResult, removeResult, isAnalyzing, setIsAnalyzing } = useAnalysisStore();
  const { setCurrentPage, addNotification } = useUIStore();
  
  const [selectedType, setSelectedType] = useState('descriptive');
  const [expandedResult, setExpandedResult] = useState<string | null>(null);

  const formatOptionalNumber = (value?: number | null, digits = 3) => {
    if (value === null || value === undefined || Number.isNaN(value)) return '-';
    return formatNumber(value, digits);
  };

  const buildBaseResult = (overrides: Partial<StatisticalResult>): StatisticalResult => ({
    id: Math.random().toString(36).substring(7),
    testName: analysisTypes.find((t) => t.id === selectedType)?.name || selectedType,
    testType: selectedType,
    columnX: '',
    statistic: 0,
    pValue: 0,
    confidence: 0.95,
    descriptiveStats: {},
    createdAt: new Date(),
    ...overrides,
  });

  const runAnalysis = async () => {
    if (!currentDataset) return;
    
    setIsAnalyzing(true);
    try {
      let response;
      const numericColumns = currentDataset.columns.filter((c) => c.type === 'numeric').map((c) => c.name);
      const categoricalColumns = currentDataset.columns
        .filter((c) => {
          if (c.type === 'categorical') return true;
          if (c.type !== 'text') return false;
          if (!c.uniqueCount || c.uniqueCount <= 0) return false;
          if (c.uniqueCount <= 20) return true;
          return currentDataset.rowCount > 0
            ? c.uniqueCount / currentDataset.rowCount <= 0.05
            : false;
        })
        .map((c) => c.name);
      
      switch (selectedType) {
        case 'descriptive':
          if (numericColumns.length === 0) {
            throw new Error('没有可用的数值列进行描述性统计');
          }
          response = await api.analysis.descriptiveStats(currentDataset.id, numericColumns.slice(0, 3));
          break;
        case 'ttest':
          if (numericColumns.length > 0 && categoricalColumns.length > 0) {
            response = await api.analysis.tTest(currentDataset.id, numericColumns[0], categoricalColumns[0]);
          } else {
            throw new Error('t 检验需要至少 1 个数值列和 1 个分组列');
          }
          break;
        case 'anova':
          if (numericColumns.length > 0 && categoricalColumns.length > 0) {
            response = await api.analysis.anova(currentDataset.id, numericColumns[0], categoricalColumns[0]);
          } else {
            throw new Error('ANOVA 需要至少 1 个数值列和 1 个分组列');
          }
          break;
        case 'correlation':
          if (numericColumns.length < 2) {
            throw new Error('相关性分析至少需要 2 个数值列');
          }
          response = await api.analysis.correlation(currentDataset.id, numericColumns.slice(0, 4));
          break;
        default:
          throw new Error('不支持的统计方法');
      }

      if (response?.success && response.data) {
        let result: StatisticalResult;

        if (selectedType === 'descriptive') {
          result = buildBaseResult({
            columnX: numericColumns[0] || '',
            descriptiveStats: response.data as Record<string, any>,
          });
        } else if (selectedType === 'ttest') {
          const tTestData = response.data as {
            statistic: number;
            pvalue: number;
            df: number;
            confidence_interval: number[];
            effect_size?: number | null;
            mean_diff?: number | null;
            std_diff?: number | null;
          };
          result = buildBaseResult({
            columnX: numericColumns[0] || '',
            columnY: categoricalColumns[0] || '',
            groupColumn: categoricalColumns[0] || '',
            statistic: tTestData.statistic,
            pValue: tTestData.pvalue,
            effectSize: tTestData.effect_size ?? undefined,
            effectSizeType: 'Cohen\'s d',
            rawData: {
              df: tTestData.df,
              confidenceInterval: tTestData.confidence_interval,
              meanDiff: tTestData.mean_diff,
              stdDiff: tTestData.std_diff,
            },
          });
        } else if (selectedType === 'anova') {
          const anovaData = response.data as {
            f_statistic: number;
            pvalue: number;
            df_between: number;
            df_within: number;
            sum_sq_between: number;
            sum_sq_within: number;
            mean_sq_between: number;
            mean_sq_within: number;
            eta_squared?: number | null;
            post_hoc_results?: Array<{
              group1: string;
              group2: string;
              pvalue: number;
              reject: boolean;
              mean_diff?: number;
              ci_lower?: number;
              ci_upper?: number;
            }>;
          };
          result = buildBaseResult({
            columnX: numericColumns[0] || '',
            columnY: categoricalColumns[0] || '',
            groupColumn: categoricalColumns[0] || '',
            statistic: anovaData.f_statistic,
            pValue: anovaData.pvalue,
            effectSize: anovaData.eta_squared ?? undefined,
            effectSizeType: 'η²',
            postHoc: anovaData.post_hoc_results?.map((item) => ({
              group1: item.group1,
              group2: item.group2,
              pValue: item.pvalue,
              significant: Boolean(item.reject),
            })),
            rawData: {
              dfBetween: anovaData.df_between,
              dfWithin: anovaData.df_within,
              sumSqBetween: anovaData.sum_sq_between,
              sumSqWithin: anovaData.sum_sq_within,
              meanSqBetween: anovaData.mean_sq_between,
              meanSqWithin: anovaData.mean_sq_within,
              postHocRaw: anovaData.post_hoc_results ?? [],
            },
          });
        } else if (selectedType === 'correlation') {
          const correlationData = response.data as {
            matrix: Record<string, Record<string, number>>;
            pValues: Record<string, Record<string, number>>;
            method: string;
          };
          result = buildBaseResult({
            columnX: numericColumns[0] || '',
            rawData: correlationData,
          });
        } else {
          result = buildBaseResult({
            columnX: numericColumns[0] || '',
          });
        }
        addResult(result);
        addNotification({
          type: 'success',
          message: '分析完成！',
        });
      }
    } catch (error) {
      addNotification({
        type: 'error',
        message: '分析失败: ' + (error instanceof Error ? error.message : '未知错误'),
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  if (!currentDataset) {
    return (
      <div className={cn('flex flex-col items-center justify-center h-full', className)}>
        <div className="w-24 h-24 bg-gray-100 rounded-full flex items-center justify-center mb-6">
          <Database className="w-12 h-12 text-gray-400" />
        </div>
        <h2 className="text-2xl font-bold text-gray-700 mb-3">暂无数据</h2>
        <p className="text-gray-500 mb-6">请先上传一个数据文件</p>
        <button
          onClick={() => setCurrentPage('upload')}
          className="px-6 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          去上传数据
        </button>
      </div>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* 页面标题 */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900">统计分析</h2>
        <p className="text-gray-500 mt-1">
          执行各种统计检验，获取数据洞察
        </p>
      </div>

      {/* 分析类型选择 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Calculator className="w-5 h-5" />
          选择分析方法
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {analysisTypes.map((type) => (
            <button
              key={type.id}
              onClick={() => setSelectedType(type.id)}
              className={cn(
                'p-4 rounded-lg border text-left transition-all',
                selectedType === type.id
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-primary-200 hover:bg-gray-50'
              )}
            >
              <p className="font-medium text-gray-900">{type.name}</p>
              <p className="text-xs text-gray-500 mt-1">{type.description}</p>
            </button>
          ))}
        </div>
        <button
          onClick={runAnalysis}
          disabled={isAnalyzing}
          className={cn(
            'mt-4 flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-all',
            isAnalyzing
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-primary-500 text-white hover:bg-primary-600 shadow-lg hover:shadow-xl'
          )}
        >
          {isAnalyzing ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              分析中...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              开始分析
            </>
          )}
        </button>
      </div>

      {/* 分析结果 */}
      {results.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-gray-900">分析结果</h3>
          {results.map((result) => (
            <div
              key={result.id}
              className="bg-white rounded-xl border border-gray-200 overflow-hidden"
            >
              <div
                className="flex items-center justify-between px-6 py-4 cursor-pointer hover:bg-gray-50"
                onClick={() => setExpandedResult(expandedResult === result.id ? null : result.id)}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary-50 rounded-lg flex items-center justify-center">
                    <Calculator className="w-5 h-5 text-primary-500" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{result.testName}</p>
                    <p className="text-sm text-gray-500">
                      {result.columnX} {result.columnY && `vs ${result.columnY}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500">
                    {result.createdAt.toLocaleString()}
                  </span>
                  {expandedResult === result.id ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </div>
              </div>
              
              {expandedResult === result.id && (
                <div className="px-6 pb-6 border-t border-gray-100">
                  <div className="pt-4">
                    {result.testType === 'descriptive' && (
                      <>
                        <h4 className="text-sm font-medium text-gray-700 mb-3">描述性统计</h4>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-4 py-2 text-left">变量</th>
                                <th className="px-4 py-2 text-right">计数</th>
                                <th className="px-4 py-2 text-right">均值</th>
                                <th className="px-4 py-2 text-right">标准差</th>
                                <th className="px-4 py-2 text-right">最小值</th>
                                <th className="px-4 py-2 text-right">最大值</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(result.descriptiveStats).map(([key, stats]: [string, any]) => (
                                <tr key={key} className="border-t border-gray-100">
                                  <td className="px-4 py-2">{key}</td>
                                  <td className="px-4 py-2 text-right">{formatOptionalNumber(stats.count, 0)}</td>
                                  <td className="px-4 py-2 text-right">{formatOptionalNumber(stats.mean)}</td>
                                  <td className="px-4 py-2 text-right">{formatOptionalNumber(stats.std)}</td>
                                  <td className="px-4 py-2 text-right">{formatOptionalNumber(stats.min)}</td>
                                  <td className="px-4 py-2 text-right">{formatOptionalNumber(stats.max)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}

                    {result.testType === 'ttest' && (
                      <div className="space-y-4">
                        <h4 className="text-sm font-medium text-gray-700">t 检验结果</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">t 统计量</p>
                            <p className="font-semibold text-gray-900">{formatOptionalNumber(result.statistic)}</p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">p 值</p>
                            <p className="font-semibold text-gray-900">{formatOptionalNumber(result.pValue)}</p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">自由度</p>
                            <p className="font-semibold text-gray-900">
                              {formatOptionalNumber((result.rawData as any)?.df)}
                            </p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">效应量 (Cohen&apos;s d)</p>
                            <p className="font-semibold text-gray-900">
                              {formatOptionalNumber(result.effectSize)}
                            </p>
                          </div>
                        </div>
                        <div className="text-sm text-gray-700">
                          <p className="font-medium text-gray-700 mb-2">置信区间</p>
                          <p>
                            {(() => {
                              const interval = (result.rawData as any)?.confidenceInterval as number[] | undefined;
                              if (!interval || interval.length < 2) return '—';
                              return `${formatOptionalNumber(interval[0])} ~ ${formatOptionalNumber(interval[1])}`;
                            })()}
                          </p>
                          <p className="mt-2 text-gray-500">
                            均值差异：{formatOptionalNumber((result.rawData as any)?.meanDiff)}，
                            合并标准差：{formatOptionalNumber((result.rawData as any)?.stdDiff)}
                          </p>
                        </div>
                      </div>
                    )}

                    {result.testType === 'anova' && (
                      <div className="space-y-4">
                        <h4 className="text-sm font-medium text-gray-700">方差分析结果</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">F 统计量</p>
                            <p className="font-semibold text-gray-900">{formatOptionalNumber(result.statistic)}</p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">p 值</p>
                            <p className="font-semibold text-gray-900">{formatOptionalNumber(result.pValue)}</p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">η² 效应量</p>
                            <p className="font-semibold text-gray-900">{formatOptionalNumber(result.effectSize)}</p>
                          </div>
                          <div className="bg-gray-50 rounded-lg p-3">
                            <p className="text-gray-500">分组</p>
                            <p className="font-semibold text-gray-900">{result.groupColumn || '-'}</p>
                          </div>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm border border-gray-100 rounded-lg">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-4 py-2 text-left">指标</th>
                                <th className="px-4 py-2 text-right">数值</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组间自由度</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.dfBetween)}
                                </td>
                              </tr>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组内自由度</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.dfWithin)}
                                </td>
                              </tr>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组间平方和</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.sumSqBetween)}
                                </td>
                              </tr>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组内平方和</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.sumSqWithin)}
                                </td>
                              </tr>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组间均方</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.meanSqBetween)}
                                </td>
                              </tr>
                              <tr className="border-t border-gray-100">
                                <td className="px-4 py-2">组内均方</td>
                                <td className="px-4 py-2 text-right">
                                  {formatOptionalNumber((result.rawData as any)?.meanSqWithin)}
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                        {result.postHoc && result.postHoc.length > 0 && (
                          <div className="space-y-2">
                            <h5 className="text-sm font-medium text-gray-700">事后检验</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead className="bg-gray-50">
                                  <tr>
                                    <th className="px-4 py-2 text-left">组 1</th>
                                    <th className="px-4 py-2 text-left">组 2</th>
                                    <th className="px-4 py-2 text-right">p 值</th>
                                    <th className="px-4 py-2 text-center">显著</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {result.postHoc.map((item, index) => (
                                    <tr key={`${item.group1}-${item.group2}-${index}`} className="border-t border-gray-100">
                                      <td className="px-4 py-2">{item.group1}</td>
                                      <td className="px-4 py-2">{item.group2}</td>
                                      <td className="px-4 py-2 text-right">{formatOptionalNumber(item.pValue)}</td>
                                      <td className="px-4 py-2 text-center">
                                        {item.significant ? '是' : '否'}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {result.testType === 'correlation' && (
                      <div className="space-y-3">
                        <h4 className="text-sm font-medium text-gray-700">相关性矩阵</h4>
                        <div className="text-xs text-gray-500">
                          方法：{(result.rawData as any)?.method || 'pearson'}
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="px-4 py-2 text-left">变量</th>
                                {Object.keys((result.rawData as any)?.matrix || {}).map((col) => (
                                  <th key={col} className="px-4 py-2 text-right">{col}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries((result.rawData as any)?.matrix || {}).map(([rowKey, rowValue]) => (
                                <tr key={rowKey} className="border-t border-gray-100">
                                  <td className="px-4 py-2">{rowKey}</td>
                                  {Object.values(rowValue as Record<string, number>).map((value, index) => (
                                    <td key={`${rowKey}-${index}`} className="px-4 py-2 text-right">
                                      {formatOptionalNumber(value)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 mt-4">
                    <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200">
                      <Download className="w-4 h-4" />
                      导出结果
                    </button>
                    <button
                      onClick={() => removeResult(result.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-600 bg-red-50 rounded-lg hover:bg-red-100"
                    >
                      <Trash2 className="w-4 h-4" />
                      删除
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AnalysisPage;
