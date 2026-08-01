import { ArrowLeft, CheckCircle, AlertCircle, XCircle, Download, FileText, Info } from 'lucide-react';
import { useState } from 'react';
import { ValidationReport, AgentReport, ValidationResult } from '../services/api';

/**
 * 生成格式化的审查报告文本（用于导出）
 */
function formatReportText(report: ValidationReport): string {
  const lines: string[] = [];
  lines.push('═══════════════════════════════════════');
  lines.push('       发票审查报告');
  lines.push('═══════════════════════════════════════');
  lines.push('');
  lines.push(`发票ID：${report.invoice_id}`);
  lines.push(`审查时间：${report.validation_time}`);
  lines.push(`总体状态：${report.overall_status}`);
  lines.push(`总结：${report.summary}`);
  lines.push('');
  lines.push('───────────────────────────────────────');

  for (const ar of report.agent_reports) {
    lines.push('');
    lines.push(`【${ar.agent_name}】  执行时间：${ar.execution_time.toFixed(2)}s`);
    lines.push('─'.repeat(40));
    for (const r of ar.results) {
      const levelTag = r.level === 'error' ? '[错误]' : r.level === 'warning' ? '[警告]' : '[信息]';
      lines.push(`  ${levelTag} ${r.category}`);
      lines.push(`    ${r.message}`);
      if (r.field) lines.push(`    字段：${r.field}`);
      if (r.expected != null) lines.push(`    期望：${JSON.stringify(r.expected)}`);
      if (r.actual != null) lines.push(`    实际：${JSON.stringify(r.actual)}`);
      if (r.suggestion) lines.push(`    建议：${r.suggestion}`);
    }
  }

  lines.push('');
  lines.push('═══════════════════════════════════════');
  return lines.join('\n');
}

interface ReviewResultsProps {
  onBack: () => void;
  activeMenu: string;
  validationReport: ValidationReport | null;
}

export function ReviewResults({ onBack, activeMenu, validationReport }: ReviewResultsProps) {
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('全部');

  /** 导出报告：下载格式化文本文件 */
  const handleExportReport = () => {
    if (!validationReport) return;
    const text = formatReportText(validationReport);
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `发票审查报告_${validationReport.invoice_id}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /** 生成PDF：调用浏览器打印（可另存为PDF） */
  const handleGeneratePDF = () => {
    window.print();
  };

  if (!validationReport) {
    return (
      <div className="h-full flex items-center justify-center glass-effect">
        <div className="text-center">
          <div className="text-gray-400 mb-4">暂无审查结果</div>
          <button
            onClick={onBack}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all"
          >
            返回
          </button>
        </div>
      </div>
    );
  }

  // 将后端数据转换为显示格式
  const reviewItems = validationReport.agent_reports.map((agent: AgentReport) => {
    const hasErrors = agent.results.some((r: ValidationResult) => r.level === 'error');
    const hasWarnings = agent.results.some((r: ValidationResult) => r.level === 'warning');
    // 只有没有错误和警告才算通过（info 级别的提示也算通过）
    const isPassed = !hasErrors && !hasWarnings;

    let statusType: 'success' | 'warning' | 'error';
    let status: string;
    let inventoryText: string;

    if (hasErrors) {
      statusType = 'error';
      status = '需要审查';
      inventoryText = `发现 ${agent.results.filter(r => r.level === 'error').length} 个错误`;
    } else if (hasWarnings) {
      statusType = 'warning';
      status = `${Math.round((1 - agent.results.filter(r => r.level === 'warning').length / 10) * 100)}% 合格`;
      inventoryText = `发现 ${agent.results.filter(r => r.level === 'warning').length} 个警告`;
    } else {
      statusType = 'success';
      status = '100% 合格';
      inventoryText = agent.results.length > 0 ? `${agent.results.length} 个提示` : '通过所有检查';
    }

    // 提取关键信息
    const firstResult = agent.results[0];
    const allNotes = agent.results.map((r: ValidationResult) => r.message).join('; ');

    return {
      name: agent.agent_name,
      quantity: agent.results.length,
      status: status,
      statusType: statusType,
      model: firstResult?.field || '-',
      price: '-',
      inventory: inventoryText,
      action: agent.results.length > 0 ? '查看详情' : '',
      note: allNotes.substring(0, 50) + (allNotes.length > 50 ? '...' : ''),
      details: agent.results,
      executionTime: agent.execution_time
    };
  });

  const getStatusBadge = (statusType: string, status: string) => {
    if (statusType === 'success') {
      return (
        <div className="inline-flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 rounded text-xs">
          <CheckCircle className="w-3 h-3" />
          {status}
        </div>
      );
    } else if (statusType === 'warning') {
      return (
        <div className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-50 text-yellow-700 rounded text-xs">
          <AlertCircle className="w-3 h-3" />
          {status}
        </div>
      );
    } else {
      return (
        <div className="inline-flex items-center gap-1 px-2 py-1 bg-red-50 text-red-700 rounded text-xs">
          <XCircle className="w-3 h-3" />
          {status}
        </div>
      );
    }
  };

  const filteredItems = filterStatus === '全部'
    ? reviewItems
    : reviewItems.filter(item => {
        if (filterStatus === '合格') return item.statusType === 'success';
        if (filterStatus === '警告') return item.statusType === 'warning';
        if (filterStatus === '需审查') return item.statusType === 'error';
        return true;
      });

  const stats = {
    total: reviewItems.length,
    success: reviewItems.filter(item => item.statusType === 'success').length,
    warning: reviewItems.filter(item => item.statusType === 'warning').length,
    error: reviewItems.filter(item => item.statusType === 'error').length,
  };

  return (
    <div className="h-full flex flex-col glass-effect print-area">
      <div className="p-6 border-b border-white/30 glass-effect-dark">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-all duration-300 hover:scale-105 hover:gap-3"
        >
          <ArrowLeft className="w-4 h-4" />
          返回
        </button>
        <div className="flex items-center justify-between">
          <h2 className="text-xl gradient-text">审查结果 - {activeMenu}</h2>
          <div className="flex gap-2">
            <button onClick={handleExportReport} className="flex items-center gap-2 px-4 py-2 glass-effect border border-white/30 rounded-xl hover:bg-white/90 transition-all duration-300 hover:scale-105 shadow-md hover:shadow-lg">
              <Download className="w-4 h-4" />
              导出报告
            </button>
            <button onClick={handleGeneratePDF} className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-xl hover:from-blue-600 hover:to-purple-600 transition-all duration-300 hover:scale-105 shadow-lg hover:shadow-xl">
              <FileText className="w-4 h-4" />
              生成PDF
            </button>
          </div>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="p-6 border-b border-white/30 bg-gradient-to-r from-blue-50/50 to-purple-50/50">
        <div className="grid grid-cols-4 gap-4">
          <div className="glass-effect-dark p-4 rounded-xl border border-white/30 hover:scale-105 transition-all duration-300 shadow-md hover:shadow-lg">
            <div className="text-2xl mb-1 gradient-text">{stats.total}</div>
            <div className="text-sm text-gray-500">总计审查项</div>
          </div>
          <div className="glass-effect-dark p-4 rounded-xl border border-green-200 hover:scale-105 transition-all duration-300 shadow-md hover:shadow-lg bg-gradient-to-br from-green-50 to-emerald-50">
            <div className="text-2xl text-green-600 mb-1">{stats.success}</div>
            <div className="text-sm text-gray-500">合格项</div>
          </div>
          <div className="glass-effect-dark p-4 rounded-xl border border-yellow-200 hover:scale-105 transition-all duration-300 shadow-md hover:shadow-lg bg-gradient-to-br from-yellow-50 to-amber-50">
            <div className="text-2xl text-yellow-600 mb-1">{stats.warning}</div>
            <div className="text-sm text-gray-500">警告项</div>
          </div>
          <div className="glass-effect-dark p-4 rounded-xl border border-red-200 hover:scale-105 transition-all duration-300 shadow-md hover:shadow-lg bg-gradient-to-br from-red-50 to-pink-50">
            <div className="text-2xl text-red-600 mb-1">{stats.error}</div>
            <div className="text-sm text-gray-500">需审查项</div>
          </div>
        </div>
      </div>

      {/* 筛选器 */}
      <div className="px-6 py-3 border-b border-white/30 flex items-center gap-2 glass-effect">
        <span className="text-sm text-gray-600">筛选:</span>
        {['全部', '合格', '警告', '需审查'].map(filter => (
          <button
            key={filter}
            onClick={() => setFilterStatus(filter)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-all duration-300 hover:scale-105 ${
              filterStatus === filter
                ? 'bg-gradient-to-r from-blue-500 to-purple-500 text-white shadow-md'
                : 'glass-effect text-gray-700 hover:bg-white/90'
            }`}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="glass-effect-dark rounded-xl border border-white/30 overflow-hidden shadow-premium-lg">
          <table className="w-full">
            <thead className="bg-gradient-to-r from-blue-50/50 to-purple-50/50 border-b border-white/30">
              <tr>
                <th className="px-4 py-3 text-left text-xs text-gray-500">代理名称</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500">审查状态</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500">问题数量</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500">执行时间</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500">备注</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/30">
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center">
                    <div className="text-gray-400 text-sm">
                      未返回结构化审查分项，请查看下方「审查说明」。
                    </div>
                  </td>
                </tr>
              ) : (
              filteredItems.map((item, index) => (
                <>
                  <tr
                    key={index}
                    onClick={() => setSelectedRow(selectedRow === index ? null : index)}
                    className={`cursor-pointer transition-all duration-300 ${
                      item.statusType === 'error' ? 'bg-gradient-to-r from-red-50 to-pink-50' :
                      item.statusType === 'success' ? 'bg-gradient-to-r from-green-50 to-emerald-50' :
                      selectedRow === index ? 'bg-gradient-to-r from-blue-50 to-purple-50 scale-[1.02]' : 'hover:bg-white/40'
                    }`}
                  >
                    <td className="px-4 py-4">
                      <div className={`text-sm font-medium ${
                        item.statusType === 'error' ? 'text-red-700' :
                        item.statusType === 'success' ? 'text-green-700' :
                        'text-gray-700'
                      }`}>
                        {item.name}
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      {getStatusBadge(item.statusType, item.status)}
                    </td>
                    <td className="px-4 py-4">
                      {item.statusType === 'error' ? (
                        <div className="flex items-center gap-1 text-red-600 text-sm font-medium">
                          <XCircle className="w-4 h-4" />
                          {item.inventory}
                        </div>
                      ) : item.statusType === 'warning' ? (
                        <div className="flex items-center gap-1 text-yellow-600 text-sm font-medium">
                          <AlertCircle className="w-4 h-4" />
                          {item.inventory}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-green-600 text-sm font-medium">
                          <CheckCircle className="w-4 h-4" />
                          {item.inventory}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <div className={`text-sm ${
                        item.statusType === 'error' ? 'text-red-600' :
                        item.statusType === 'success' ? 'text-green-600' :
                        'text-gray-600'
                      }`}>
                        {item.executionTime?.toFixed(2)}s
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      {item.note ? (
                        <div className={`text-xs ${
                          item.statusType === 'error' ? 'text-red-600 font-medium' :
                          item.statusType === 'warning' ? 'text-yellow-600' :
                          'text-gray-500'
                        }`}>
                          {item.note}
                        </div>
                      ) : (
                        <div className="text-xs text-gray-400">-</div>
                      )}
                    </td>
                  </tr>

                  {/* 展开的详细信息 */}
                  {selectedRow === index && item.details && item.details.length > 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-4 bg-gray-50/50">
                        <div className="space-y-3">
                          <div className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                            <Info className="w-4 h-4 text-blue-500" />
                            问题详情:
                          </div>
                          {item.details.map((result: ValidationResult, resultIndex: number) => {
                            // 判断是否为通过的检查项（根据 level 和消息中的否定词）
                            const hasNegation = result.message.includes('不正确') ||
                                               result.message.includes('不符合') ||
                                               result.message.includes('不通过') ||
                                               result.message.includes('不匹配') ||
                                               result.message.includes('不一致') ||
                                               result.message.includes('错误') ||
                                               result.message.includes('失败') ||
                                               result.message.includes('缺失') ||
                                               result.message.includes('无效');

                            const isPassedCheck = result.level === 'info' && !hasNegation;

                            // 根据 level 和通过/失败设置颜色
                            const bgColor = isPassedCheck ? 'bg-green-50' :
                                          result.level === 'error' ? 'bg-red-50' : 'bg-yellow-50';
                            const borderColor = isPassedCheck ? 'border-green-500' :
                                              result.level === 'error' ? 'border-red-500' : 'border-yellow-500';
                            const textColor = isPassedCheck ? 'text-green-700' :
                                            result.level === 'error' ? 'text-red-700' : 'text-yellow-700';
                            const iconColor = isPassedCheck ? 'text-green-600' :
                                            result.level === 'error' ? 'text-red-600' : 'text-yellow-600';

                            return (
                              <div
                                key={resultIndex}
                                className={`p-4 rounded-lg border-l-4 ${bgColor} ${borderColor}`}
                              >
                                <div className="flex items-start gap-3">
                                  <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-2">
                                      {isPassedCheck ? (
                                        <CheckCircle className={`w-4 h-4 ${iconColor}`} />
                                      ) : result.level === 'error' ? (
                                        <XCircle className={`w-4 h-4 ${iconColor}`} />
                                      ) : (
                                        <AlertCircle className={`w-4 h-4 ${iconColor}`} />
                                      )}
                                      <span className={`text-sm font-semibold ${textColor}`}>
                                        {result.category}
                                      </span>
                                    </div>
                                    <div className={`text-sm mb-2 font-medium ${textColor}`}>{result.message}</div>
                                    {result.field && (
                                      <div className="text-xs text-gray-600 mb-1">
                                        字段: <span className="font-mono bg-white px-2 py-0.5 rounded">{result.field}</span>
                                      </div>
                                    )}
                                    {result.expected !== undefined && result.expected !== null && (
                                      <div className="text-xs text-gray-600 mb-1">
                                        期望值: <span className="font-mono bg-white px-2 py-0.5 rounded">{JSON.stringify(result.expected)}</span>
                                      </div>
                                    )}
                                    {result.actual !== undefined && result.actual !== null && (
                                      <div className="text-xs text-gray-600 mb-1">
                                        实际值: <span className="font-mono bg-white px-2 py-0.5 rounded">{JSON.stringify(result.actual)}</span>
                                      </div>
                                    )}
                                    {result.suggestion && (
                                      <div className="text-xs text-blue-700 mt-2 bg-blue-100 px-3 py-2 rounded">
                                        💡 建议: {result.suggestion}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                          <div className="text-xs text-gray-500 mt-3">
                            执行时间: {item.executionTime?.toFixed(2)}s
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))
              )}
            </tbody>
          </table>
        </div>

        {/* 审查说明 */}
        <div className="mt-6 glass-effect-dark rounded-xl p-6 border border-white/30 shadow-md">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-gray-800 mb-2">审查说明</div>
              <div className="text-sm text-gray-600 space-y-1">
                <p>• 审查状态: <span className="font-semibold">{validationReport.overall_status}</span></p>
                <p>• {validationReport.summary}</p>
                <p>• 审查时间: {new Date(validationReport.validation_time).toLocaleString('zh-CN')}</p>
                <p>• 发票ID: {validationReport.invoice_id}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
