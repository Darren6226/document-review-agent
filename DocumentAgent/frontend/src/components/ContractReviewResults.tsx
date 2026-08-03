import { useState, useEffect, useRef } from 'react';
import { ContractAuditResult, ContractAuditIssue } from '../services/api';

interface ContractReviewResultsProps {
  onBack: () => void;
  auditResult: ContractAuditResult | null;
  documentUrl?: string | null;
  // 方案 B：流式实时分析状态
  streaming?: boolean;
  liveStage?: string;
  liveToken?: string;
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
  // 证据链字段
  evidence_location: string;
  rule_id: string;
  basis_type: 'llm_judgment' | 'deterministic' | 'hybrid';
  deterministic_ref?: string | null;
  // 验证状态
  verified: boolean;
  verification_note: string;
}

const BASIS_TYPE_LABEL: Record<string, string> = {
  llm_judgment: 'LLM 判定',
  deterministic: '确定性判定',
  hybrid: '混合判定',
};

export function ContractReviewResults({ onBack, auditResult, documentUrl, streaming, liveStage, liveToken }: ContractReviewResultsProps) {
  const [auditResults, setAuditResults] = useState<AuditIssue[]>([]);
  const [activeTab, setActiveTab] = useState<'high' | 'medium' | 'low' | 'pass' | 'unverified'>('high');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // 标记是否已经执行过初始自动选中，避免用户手动切换后被 useEffect 重置
  const initialAutoSetDone = useRef(false);

  // 检测是否为PDF文件
  const isPDF = documentUrl?.startsWith('data:application/pdf');

  useEffect(() => {
    if (auditResult && auditResult.issues) {
      const formattedIssues = auditResult.issues.map((issue: ContractAuditIssue, index) => ({
        id: index + 1,
        rule_category: issue.rule_category,
        issue_type: issue.issue_type,
        description: issue.description,
        original: issue.original,
        suggestion: issue.suggestion,
        severity: issue.severity,
        legal_risk: issue.legal_risk,
        evidence_location: issue.evidence_location,
        rule_id: issue.rule_id,
        basis_type: issue.basis_type,
        deterministic_ref: issue.deterministic_ref,
        verified: issue.verified,
        verification_note: issue.verification_note,
      }));
      setAuditResults(formattedIssues);

      // 仅在首次加载数据时自动选择第一个有数据的风险等级，
      // 防止用户手动切换 tab 后被重复重置
      if (!initialAutoSetDone.current) {
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
        initialAutoSetDone.current = true;
      }
    }
  }, [auditResult]);

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const highRiskCount = auditResults.filter(item => item.severity === 'high').length;
  const mediumRiskCount = auditResults.filter(item => item.severity === 'medium').length;
  const lowRiskCount = auditResults.filter(item => item.severity === 'low').length;
  const verifiedCount = auditResults.filter(item => item.verified).length;
  const unverifiedCount = auditResults.length - verifiedCount;

  // 审核是否未成功完成（超时/异常）：此时展示的「暂无问题」不可信，必须告警
  const auditFailed = auditResult?.status && auditResult.status !== 'success';

  // 纯模板未填检测：确定性校验失败项全部来自"留空待补"占位符（金额/日期完整性），
  // 且 LLM 未产出任何风险问题，说明这是一份未填写金额的草稿合同
  const findings = auditResult?.deterministic_findings || [];
  const detFailed = findings.filter(f => !f.passed);
  const placeholderCats = new Set(['金额完整性', '日期完整性']);
  const allPlaceholderFail =
    detFailed.length > 0 &&
    detFailed.every(f => placeholderCats.has(f.rule_category));

  const filteredResults = activeTab === 'pass'
    ? auditResults.filter(item => item.verified)
    : activeTab === 'unverified'
    ? auditResults.filter(item => !item.verified)
    : auditResults.filter(item => item.severity === activeTab);

  // 获取风险等级的显示文本和颜色
  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'high': return '高风险';
      case 'medium': return '中风险';
      case 'low': return '低风险';
      case 'unverified': return '未验证';
      default: return '';
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'bg-red-500';
      case 'medium': return 'bg-orange-500';
      case 'low': return 'bg-yellow-500';
      case 'unverified': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="h-full flex bg-white">
      {/* 方案 B：流式实时分析面板（审核未完成、尚无完整报告时展示） */}
      {streaming && !auditResult ? (
        <>
          {/* 左侧：文档预览 */}
          <div className="flex-1 flex flex-col border-r border-gray-200">
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
            </div>
            <div className="flex-1 overflow-auto bg-gray-50 p-6 flex items-center justify-center">
              {documentUrl ? (
                <iframe src={documentUrl} className="w-full h-full border-0 bg-white shadow-sm rounded" title="PDF Preview" />
              ) : (
                <span className="text-gray-400 text-sm">文档预览</span>
              )}
            </div>
          </div>

          {/* 右侧：实时分析进度 */}
          <div className="w-[450px] flex flex-col bg-white">
            <div className="h-14 bg-white border-b border-gray-200 flex items-center px-6">
              <span className="flex items-center gap-2 text-sm font-medium text-blue-600">
                <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                风险审查（分析中）
              </span>
            </div>
            <div className="px-6 py-4 bg-blue-50/60 border-b border-blue-100">
              <div className="flex items-center gap-2 text-sm text-blue-700 font-medium">
                <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                {liveStage || '正在分析...'}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {liveToken ? (
                <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 rounded-lg p-4 border border-gray-200">
                  {liveToken}
                  <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-0.5 align-middle" />
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center text-gray-400">
                  <div className="w-16 h-16 border-2 border-blue-300 border-t-transparent rounded-full animate-spin mb-4" />
                  <p className="text-sm">AI 正在阅读并分析合同条款，请稍候...</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
      <>
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
            <span className="flex items-center gap-2 text-sm font-medium text-blue-600 pb-4 border-b-2 border-blue-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              风险审查
            </span>
          </div>
          <div className="ml-auto w-16"></div>
        </div>

        {/* 分析未完成告警：超时/异常导致结果不可信，必须明确提示用户 */}
        {auditFailed && (
          <div className="px-6 py-3 bg-red-50 border-b border-red-200 flex items-start gap-2.5">
            <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="flex-1">
              <div className="text-sm font-semibold text-red-700">
                {auditResult.status === 'llm_timeout' ? '⚠️ 深度分析超时，本次结论不可信' : '⚠️ 审核未完成，结果不可信'}
              </div>
              <div className="text-xs text-red-600 mt-0.5 leading-relaxed">
                {auditResult.status_message || 'AI 模型未能在规定时间内完成分析。当前显示的「暂无问题」并不代表合同真的没问题。'}
              </div>
              <div className="text-xs text-red-600 mt-1 font-medium">
                建议：请重新上传合同再次发起审核，或检查模型配置后重试。
              </div>
            </div>
          </div>
        )}

        {/* 纯模板未填提示：合同未填写金额/日期等占位符，并非实质性条款错误 */}
        {allPlaceholderFail && (
          <div className="px-6 py-3 bg-amber-50 border-b border-amber-200 flex items-start gap-2.5">
            <svg className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <div className="text-sm font-semibold text-amber-700">
                本报告基于未填写金额的草稿合同
              </div>
              <div className="text-xs text-amber-600 mt-0.5 leading-relaxed">
                以上确定性校验的失败项均为金额/日期留空待补，并非实质性条款错误。请在签署前补全所有留空内容后重新审核。
              </div>
            </div>
          </div>
        )}

        {/* 统计标签 */}
        <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setActiveTab('high')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'high'
                  ? 'bg-red-100 text-red-700 border border-red-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'high' ? 'bg-red-500' : 'bg-red-300'} rounded-sm`}></span>
              高风险 ({highRiskCount})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('medium')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'medium'
                  ? 'bg-orange-100 text-orange-700 border border-orange-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'medium' ? 'bg-orange-500' : 'bg-orange-300'} rounded-sm`}></span>
              中风险 ({mediumRiskCount})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('low')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'low'
                  ? 'bg-yellow-100 text-yellow-700 border border-yellow-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'low' ? 'bg-yellow-500' : 'bg-yellow-300'} rounded-sm`}></span>
              低风险 ({lowRiskCount})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('pass')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'pass'
                  ? 'bg-green-100 text-green-700 border border-green-200'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              <span className={`w-2 h-2 ${activeTab === 'pass' ? 'bg-green-500' : 'bg-green-300'} rounded-sm`}></span>
              已验证 ({verifiedCount})
            </button>
            {unverifiedCount > 0 && (
              <button
                type="button"
                onClick={() => setActiveTab('unverified')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                  activeTab === 'unverified'
                    ? 'bg-red-100 text-red-700 border border-red-200'
                    : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
                }`}
              >
                <span className={`w-2 h-2 ${activeTab === 'unverified' ? 'bg-red-500' : 'bg-red-300'} rounded-sm`}></span>
                未验证 ({unverifiedCount})
              </button>
            )}
          </div>
        </div>

        {/* 当前分类标题（即使该分类暂无数据也展示，确保切换 tab 有可见反馈） */}
        {activeTab !== 'pass' && (
          <div className={`px-6 py-2.5 ${getSeverityColor(activeTab)} text-white text-sm font-medium flex items-center gap-2`}>
            <span className="inline-block w-2 h-2 bg-white rounded-sm"></span>
            {getSeverityLabel(activeTab)}
          </div>
        )}

        {/* 问题列表 */}
        <div className="flex-1 overflow-y-auto">
          {filteredResults.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-12 px-6">
              {auditFailed ? (
                <>
                  <div className="w-20 h-20 bg-red-50 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <h4 className="text-base font-semibold text-red-700 mb-2">分析未完成，结论不可信</h4>
                  <p className="text-sm text-red-600">
                    由于{auditResult.status === 'llm_timeout' ? '模型分析超时' : '审核过程出错'}，本次未生成有效问题列表。
                    当前没有可展示的审查结果，请重新发起审核。
                  </p>
                </>
              ) : (
                <>
                  <div className="w-20 h-20 bg-blue-50 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h4 className="text-base font-semibold text-gray-800 mb-2">
                    {activeTab === 'pass' ? '暂无已验证项' : activeTab === 'unverified' ? '暂无未验证项' : '暂无问题'}
                  </h4>
                  <p className="text-sm text-gray-500">
                    {activeTab === 'pass'
                      ? '当前没有通过验证回路校验的 issue'
                      : activeTab === 'unverified'
                        ? '所有 issue 均已通过验证回路校验'
                        : '该风险等级下没有发现问题'}
                  </p>
                </>
              )}
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

                              {/* 证据链元信息 */}
                              <div className="flex flex-wrap gap-2 text-xs">
                                {item.rule_id && (
                                  <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded border border-gray-200">
                                    规则编号：{item.rule_id}
                                  </span>
                                )}
                                {item.basis_type && (
                                  <span className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded border border-purple-200">
                                    {BASIS_TYPE_LABEL[item.basis_type] || item.basis_type}
                                  </span>
                                )}
                                {item.evidence_location && (
                                  <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded border border-blue-200">
                                    位置：{item.evidence_location}
                                  </span>
                                )}
                                <span
                                  className={`px-2 py-0.5 rounded border ${
                                    item.verified
                                      ? 'bg-green-50 text-green-700 border-green-200'
                                      : 'bg-red-50 text-red-700 border-red-200'
                                  }`}
                                >
                                  {item.verified ? '✓ 已验证' : '⚠ 未验证'}
                                </span>
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

                              {!item.verified && item.verification_note && (
                                <div>
                                  <div className="text-xs text-orange-600 mb-1.5 font-medium">验证说明：</div>
                                  <div className="text-sm text-orange-700 bg-orange-50 p-3 rounded border border-orange-200 leading-relaxed">
                                    {item.verification_note}
                                  </div>
                                </div>
                              )}

                              {item.deterministic_ref && (
                                <div className="text-xs text-gray-500">
                                  引用确定性 finding：{item.deterministic_ref}
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
      </>
      )}
    </div>
  );
}
