import { useState, useEffect } from 'react';
import { ContractAuditResult } from '../services/api';

interface ContractReviewResultsProps {
  onBack: () => void;
  auditResult: ContractAuditResult | null;
  documentUrl?: string | null;
}

interface AuditIssue {
  id: number;
  rule_category: string;
  issue_type: string;
  description: string;
  original: string;
  suggestion: string;
  severity: 'high' | 'medium' | 'low';
  legal_risk: string;
}

export function ContractReviewResults({ onBack, auditResult, documentUrl }: ContractReviewResultsProps) {
  const [auditResults, setAuditResults] = useState<AuditIssue[]>([]);
  const [activeTab, setActiveTab] = useState<'high' | 'medium' | 'low' | 'pass'>('high');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // 检测是否为PDF文件
  const isPDF = documentUrl?.startsWith('data:application/pdf');

  useEffect(() => {
    if (auditResult && auditResult.issues) {
      const formattedIssues = auditResult.issues.map((issue, index) => ({
        id: index + 1,
        rule_category: issue.rule_category,
        issue_type: issue.issue_type,
        description: issue.description,
        original: issue.original,
        suggestion: issue.suggestion,
        severity: issue.severity,
        legal_risk: issue.legal_risk
      }));
      setAuditResults(formattedIssues);

      // 自动选择第一个有数据的风险等级
      const hasHigh = formattedIssues.some(item => item.severity === 'high');
      const hasMedium = formattedIssues.some(item => item.severity === 'medium');
      const hasLow = formattedIssues.some(item => item.severity === 'low');

      if (hasHigh) {
        setActiveTab('high');
      } else if (hasMedium) {
        setActiveTab('medium');
      } else if (hasLow) {
        setActiveTab('low');
      } else {
        setActiveTab('pass');
      }
    }
  }, [auditResult]);

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const highRiskCount = auditResults.filter(item => item.severity === 'high').length;
  const mediumRiskCount = auditResults.filter(item => item.severity === 'medium').length;
  const lowRiskCount = auditResults.filter(item => item.severity === 'low').length;
  const totalRules = 15;
  const passCount = totalRules - auditResults.length;

  const filteredResults = activeTab === 'pass'
    ? []
    : auditResults.filter(item => item.severity === activeTab);

  // 获取风险等级的显示文本和颜色
  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'high': return '高风险';
      case 'medium': return '中风险';
      case 'low': return '低风险';
      default: return '';
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'bg-red-500';
      case 'medium': return 'bg-orange-500';
      case 'low': return 'bg-yellow-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="h-full flex bg-white">
      {/* 左侧：文档预览 */}
      <div className="flex-1 flex flex-col border-r border-gray-200">
        {/* 顶部工具栏 */}
        <div className="h-12 bg-gray-50 border-b border-gray-200 flex items-center justify-between px-4">
          <button
            onClick={onBack}
            className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            返回
          </button>
          <div className="text-sm text-gray-700">解除、终止劳动合同协议书</div>
          <div className="w-16"></div>
        </div>

        {/* 文档预览区 */}
        <div className="flex-1 overflow-auto bg-gray-50 p-6">
          {documentUrl ? (
            isPDF ? (
              <div className="w-full h-full bg-white shadow-sm rounded">
                <iframe
                  src={documentUrl}
                  className="w-full h-full border-0"
                  title="PDF Preview"
                />
              </div>
            ) : (
              <div className="flex items-center justify-center h-full">
                <img
                  src={documentUrl}
                  alt="Document preview"
                  className="max-w-full max-h-full object-contain bg-white shadow-sm rounded"
                />
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <div className="text-center">
                <svg className="w-16 h-16 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm">文档预览</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 右侧：审查结果 */}
      <div className="w-[450px] flex flex-col bg-white">
        {/* 顶部标签栏 */}
        <div className="h-14 bg-white border-b border-gray-200 flex items-center px-6">
          <div className="flex gap-8">
            <button className="flex items-center gap-2 text-sm font-medium text-blue-600 pb-4 border-b-2 border-blue-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              风险审查
            </button>
            <button className="text-sm text-gray-500 hover:text-gray-700 pb-4 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              主体审查
            </button>
          </div>
          <div className="ml-auto flex gap-2">
            <button className="p-2 hover:bg-gray-100 rounded text-gray-500">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </button>
            <button className="p-2 hover:bg-gray-100 rounded text-gray-500">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>
            <button className="p-2 hover:bg-gray-100 rounded text-gray-500">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </button>
          </div>
        </div>

        {/* 统计标签 */}
        <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setActiveTab('high')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === 'high'
                  ? 'bg-red-100 text-red-700 border border-red-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'high' ? 'bg-red-500' : 'bg-red-300'} rounded-sm`}></span>
              高风险 ({highRiskCount})
            </button>
            <button
              onClick={() => setActiveTab('medium')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === 'medium'
                  ? 'bg-orange-100 text-orange-700 border border-orange-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'medium' ? 'bg-orange-500' : 'bg-orange-300'} rounded-sm`}></span>
              中风险 ({mediumRiskCount})
            </button>
            <button
              onClick={() => setActiveTab('low')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === 'low'
                  ? 'bg-yellow-100 text-yellow-700 border border-yellow-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'low' ? 'bg-yellow-500' : 'bg-yellow-300'} rounded-sm`}></span>
              低风险 ({lowRiskCount})
            </button>
            <button
              onClick={() => setActiveTab('pass')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeTab === 'pass'
                  ? 'bg-green-100 text-green-700 border border-green-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'pass' ? 'bg-green-500' : 'bg-green-300'} rounded-sm`}></span>
              通过 ({passCount})
            </button>
          </div>
        </div>

        {/* 当前分类标题 */}
        {activeTab !== 'pass' && filteredResults.length > 0 && (
          <div className={`px-6 py-2.5 ${getSeverityColor(activeTab)} text-white text-sm font-medium flex items-center gap-2`}>
            <span className="inline-block w-2 h-2 bg-white rounded-sm"></span>
            {getSeverityLabel(activeTab)}
          </div>
        )}

        {/* 问题列表 */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'pass' ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12 px-6">
              <div className="w-20 h-20 bg-green-50 rounded-full flex items-center justify-center mb-4">
                <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-gray-800 mb-2">审查通过</h4>
              <p className="text-sm text-gray-500">这些规则审查无问题</p>
            </div>
          ) : filteredResults.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12 px-6">
              <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mb-4">
                <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h4 className="text-base font-semibold text-gray-800 mb-2">暂无问题</h4>
              <p className="text-sm text-gray-500">该风险等级下没有发现问题</p>
            </div>
          ) : (
            <div>
              {filteredResults.map((item, index) => {
                const isExpanded = expandedId === item.id;

                return (
                  <div key={item.id} className="border-b border-gray-100 last:border-b-0">
                    <div
                      className="px-6 py-4 hover:bg-gray-50 cursor-pointer flex items-start gap-3 group"
                      onClick={() => toggleExpand(item.id)}
                    >
                      <div className="flex-shrink-0">
                        <span className={`inline-block w-5 h-5 ${getSeverityColor(item.severity)} rounded text-white text-xs flex items-center justify-center font-medium`}>
                          {index + 1}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-800 leading-relaxed font-medium">
                          {item.issue_type}
                        </div>
                      </div>
                      <div className="flex-shrink-0 flex items-center gap-2">
                        <span className="text-xs text-gray-400">{index + 1}</span>
                        <svg
                          className={`w-4 h-4 text-gray-400 transition-transform ${
                            isExpanded ? 'rotate-180' : ''
                          }`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="px-6 pb-5 bg-blue-50/50">
                        <div className="pl-8 space-y-4 text-sm">
                          <div className="bg-white rounded-lg p-4 border border-gray-200">
                            <div className="space-y-3">
                              <div>
                                <div className="text-xs text-gray-500 mb-1.5">审查细则类别：{item.rule_category}</div>
                              </div>

                              {item.description && (
                                <div>
                                  <div className="text-xs text-gray-500 mb-1.5">问题描述：</div>
                                  <div className="text-sm text-gray-800 leading-relaxed">{item.description}</div>
                                </div>
                              )}

                              {item.original && (
                                <div>
                                  <div className="text-xs text-gray-500 mb-1.5">原文：</div>
                                  <div className="text-sm text-gray-800 bg-gray-50 p-3 rounded border border-gray-200 leading-relaxed">
                                    {item.original}
                                  </div>
                                </div>
                              )}

                              {item.suggestion && (
                                <div>
                                  <div className="text-xs text-gray-500 mb-1.5">修改建议：</div>
                                  <div className="text-sm text-gray-800 leading-relaxed">{item.suggestion}</div>
                                </div>
                              )}

                              {item.legal_risk && (
                                <div>
                                  <div className="text-xs text-red-600 mb-1.5 font-medium">⚠️ 法律风险：</div>
                                  <div className="text-sm text-red-700 bg-red-50 p-3 rounded border border-red-200 leading-relaxed">
                                    {item.legal_risk}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center justify-between">
                            <div className="text-xs text-gray-500">
                              本条结果存在风险，但基于目前选择的立场，可能不需要过多关注。
                            </div>
                          </div>

                          <div>
                            <a
                              href="#"
                              className="text-blue-600 hover:text-blue-700 text-xs inline-flex items-center gap-1"
                              onClick={(e) => e.preventDefault()}
                            >
                              仍需分析检测点修改建议
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </a>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
