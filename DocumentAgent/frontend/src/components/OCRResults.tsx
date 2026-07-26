import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface OCRResultsProps {
  data: any;
  contractData?: any;
  activeMenu?: string;
  isProcessing: boolean;
  onStartContractReview?: () => void;
}

export function OCRResults({ data, contractData, activeMenu = '票据审查', isProcessing, onStartContractReview }: OCRResultsProps) {
  const [selectedField, setSelectedField] = useState<string | null>(null);

  // 审查清单状态 - 专业版合同审核规则
  const [checklist, setChecklist] = useState<Array<{id: number, text: string, checked: boolean, category?: string}>>([
    // 一、文本规范性审核
    { id: 1, text: '1.1 错别字与形近字检查（形近字、同音字、笔误、多字、漏字）', checked: true, category: '文本规范性' },
    { id: 2, text: '1.2 标点符号规范性（句号、逗号、顿号、分号、冒号、括号引号配对）', checked: true, category: '文本规范性' },
    { id: 3, text: '1.3 语法结构检查（主谓宾搭配、成分完整性、避免歧义性表述）', checked: true, category: '文本规范性' },

    // 二、合同专业性审核 (核心)
    { id: 4, text: '2.1 法律术语规范性（"违约金"非"罚款"、"解除合同"非"取消合同"）', checked: true, category: '专业性审核' },
    { id: 5, text: '2.2 权利义务对等性（甲乙方权利义务明确、对等，避免显失公平）', checked: true, category: '专业性审核' },
    { id: 6, text: '2.3 金额与数字准确性（大写小写一致、重要金额必须大写+小写）', checked: true, category: '专业性审核' },
    { id: 7, text: '2.4 时间条款明确性（合同期限明确、避免"尽快"、"及时"等模糊词）', checked: true, category: '专业性审核' },

    // 三、逻辑一致性审核
    { id: 8, text: '3.1 条款前后一致性（同一概念表述一致、数字金额一致、甲乙方名称一致）', checked: true, category: '逻辑一致性' },
    { id: 9, text: '3.2 条款间逻辑矛盾（不同条款是否矛盾、违约金与赔偿损失关系明确）', checked: true, category: '逻辑一致性' },
    { id: 10, text: '3.3 引用条款准确性（条款编号引用准确、附件编号存在、法律法规引用准确）', checked: true, category: '逻辑一致性' },

    // 四、合规性与风险审核 (P0级)
    { id: 11, text: '4.1 法律合规性（是否违反法律强制性规定、是否存在无效条款）', checked: true, category: '合规性风险' },
    { id: 12, text: '4.2 敏感词汇检查（避免歧视性语言、避免绝对化承诺）', checked: true, category: '合规性风险' },
    { id: 13, text: '4.3 必备条款完整性（主体信息、标的物、价款、履行期限、违约责任、争议解决）', checked: true, category: '合规性风险' },

    // 五、表述清晰度审核
    { id: 14, text: '5.1 歧义性表述（多义词导致歧义、"和"/"或"/"及"/"与"连接词准确性）', checked: true, category: '表述清晰度' },
    { id: 15, text: '5.2 冗余与重复（不必要的重复、冗余修饰语、过长条款）', checked: true, category: '表述清晰度' },
  ]);
  const [selectAll, setSelectAll] = useState(true);

  const handleSelectAll = (checked: boolean) => {
    setSelectAll(checked);
    setChecklist(checklist.map(item => ({ ...item, checked })));
  };

  const handleItemCheck = (id: number) => {
    const newChecklist = checklist.map(item =>
      item.id === id ? { ...item, checked: !item.checked } : item
    );
    setChecklist(newChecklist);
    setSelectAll(newChecklist.every(item => item.checked));
  };

  const checkedCount = checklist.filter(item => item.checked).length;

  if (isProcessing) {
    return (
      <div className="w-96 glass-effect-dark border-l border-white/50 p-6 flex items-center justify-center shadow-premium">
        <div className="text-gray-400 text-center">
          <div className="mb-4 text-gray-700">
            {activeMenu === '合同审查' ? '正在进行合同文档解析...' : '正在识别文档...'}
          </div>
          <div className="relative">
            <div className="w-16 h-16 border-4 border-blue-200 border-t-transparent rounded-full animate-spin mx-auto"></div>
            <div className="w-16 h-16 border-4 border-purple-200 border-t-transparent rounded-full animate-spin mx-auto absolute top-0 left-1/2 -translate-x-1/2" style={{ animationDirection: 'reverse', animationDuration: '1s' }}></div>
          </div>
          <div className="mt-6 text-sm space-y-2">
            <div className="flex items-center justify-center gap-2 text-blue-600">
              <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-pulse"></div>
              正在分析文档结构
            </div>
            <div className="flex items-center justify-center gap-2 text-purple-600">
              <div className="w-1.5 h-1.5 bg-purple-600 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
              {activeMenu === '合同审查' ? '正在提取合同信息' : '正在提取文字信息'}
            </div>
            <div className="flex items-center justify-center gap-2 text-pink-600">
              <div className="w-1.5 h-1.5 bg-pink-600 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
              正在验证数据准确性
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!data && !contractData) {
    return (
      <div className="w-96 glass-effect-dark border-l border-white/50 p-6 flex items-center justify-center shadow-premium">
        <div className="text-gray-400 text-center">
          <div className="mb-4">
            <div className="w-16 h-16 bg-gradient-to-br from-blue-100 to-purple-100 rounded-2xl flex items-center justify-center mx-auto">
              <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
          <div className="mb-2 text-gray-700">等待识别</div>
          <div className="text-sm">上传文档后将自动开始识别</div>
        </div>
      </div>
    );
  }

  // 如果是合同审查，显示审查清单
  if (activeMenu === '合同审查' && contractData) {
    return (
      <div className="w-96 glass-effect-dark border-l border-white/50 flex flex-col shadow-premium">
        <div className="p-4 border-b border-white/30">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-lg gradient-text">审查清单</h3>
              <p className="text-xs text-gray-500">智能生成</p>
            </div>
            <button className="p-2 hover:bg-white/60 rounded-lg transition-all duration-300 hover:scale-110 group">
              <svg className="w-4 h-4 text-gray-600 group-hover:text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
              </svg>
            </button>
          </div>

          {/* 全选 */}
          <div className="flex items-center justify-between py-2 px-3 bg-blue-50 rounded-lg">
            <label className="flex items-center gap-2 cursor-pointer group">
              <input
                type="checkbox"
                checked={selectAll}
                onChange={(e) => handleSelectAll(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <span className="text-sm font-medium text-gray-700 group-hover:text-blue-600 transition-colors">
                全部规则 ({checklist.length})
              </span>
            </label>
            <div className="text-xs text-gray-600">
              已选 <span className="font-semibold text-blue-600">{checkedCount}</span>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-2">
            {checklist.map((item) => (
              <div
                key={item.id}
                onClick={() => handleItemCheck(item.id)}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all duration-200 ${
                  item.checked
                    ? 'bg-blue-50 border-blue-200 hover:bg-blue-100'
                    : 'bg-white border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="checkbox"
                  checked={item.checked}
                  onChange={() => {}}
                  className="w-4 h-4 mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                />
                <div className="flex-1">
                  <span className={`text-xs ${item.checked ? 'text-gray-900' : 'text-gray-500'}`}>
                    {item.id}. {item.text}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="p-4 border-t border-white/30 flex flex-col gap-2">
          <button
            onClick={onStartContractReview}
            className="w-full px-4 py-2.5 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 text-white rounded-xl hover:from-blue-600 hover:via-purple-600 hover:to-pink-600 transition-all duration-300 shadow-lg hover:shadow-xl hover:scale-105 flex items-center justify-center gap-2 text-sm font-medium"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            发起审查
          </button>
          <div className="flex items-center justify-center gap-2 text-xs text-gray-600">
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 rounded font-medium">
              PRO
            </span>
            自定义审查规则
          </div>
        </div>
      </div>
    );
  }

  // 默认显示发票数据
  return (
    <div className="w-96 glass-effect-dark border-l border-white/50 flex flex-col shadow-premium">
      <div className="p-4 border-b border-white/30 flex items-center justify-between">
        <h3 className="text-lg gradient-text">识别结果</h3>
        <div className="flex gap-2">
          <button className="p-2 hover:bg-white/60 rounded-lg transition-all duration-300 hover:scale-110 group">
            <svg className="w-4 h-4 text-gray-600 group-hover:text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
            </svg>
          </button>
          <button className="p-2 hover:bg-white/60 rounded-lg transition-all duration-300 hover:scale-110 group">
            <svg className="w-4 h-4 text-gray-600 group-hover:text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
            </svg>
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-3">
          <div className="p-4 bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl border border-green-200 shadow-md hover:shadow-lg transition-all duration-300">
            <div className="text-xs text-green-600 mb-1 flex items-center gap-1">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              发票验证状态
            </div>
            <div className="text-sm text-green-700">✓ 发票基本无问题</div>
          </div>

          {Object.entries(data).map(([key, value], index) => {
            // 跳过 line_items，稍后单独处理
            if (key === 'line_items') return null;

            // 字段名中英文映射
            const fieldNameMap: Record<string, string> = {
              'invoice_type': '发票类型',
              'province': '省份',
              'invoice_code': '发票代码',
              'invoice_number': '发票号码',
              'issue_date': '开票日期',
              'check_code': '校验码',
              'purchaser_name': '购买方名称',
              'purchaser_tax_id': '购买方纳税人识别号',
              'purchaser_address': '购买方地址电话',
              'purchaser_bank': '购买方开户行及账号',
              'seller_name': '销售方名称',
              'seller_tax_id': '销售方纳税人识别号',
              'seller_address': '销售方地址电话',
              'seller_bank': '销售方开户行及账号',
              'total_amount': '合计金额',
              'total_tax': '合计税额',
              'total_amount_with_tax': '价税合计',
              'amount_in_words': '价税合计(大写)',
              'payee': '收款人',
              'checker': '复核人',
              'drawer': '开票人',
              'remarks': '备注'
            };

            const displayName = fieldNameMap[key] || key;

            // 格式化显示值
            let displayValue: string;
            if (value === null || value === undefined) {
              displayValue = '-';
            } else if (typeof value === 'object') {
              displayValue = JSON.stringify(value, null, 2);
            } else {
              displayValue = String(value);
            }

            return (
              <div
                key={key}
                className={`border-b border-white/30 pb-3 cursor-pointer hover:bg-white/40 p-3 rounded-xl transition-all duration-300 hover:shadow-md ${
                  selectedField === key ? 'bg-gradient-to-r from-blue-50 to-purple-50 border-blue-200 shadow-md scale-105' : ''
                }`}
                onClick={() => setSelectedField(selectedField === key ? null : key)}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                <div className="text-xs text-gray-500 mb-1 flex items-center justify-between">
                  <span className={selectedField === key ? 'text-blue-600' : ''}>{displayName}</span>
                  {selectedField === key && (
                    <svg className="w-3 h-3 text-blue-500 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
                <div className="text-sm break-words whitespace-pre-wrap">{displayValue}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t border-white/30">
        <div className="p-3">
          <button className="w-full text-sm px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all duration-300 shadow-md hover:shadow-lg hover:scale-105 flex items-center justify-center gap-2">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
            </svg>
            购买方信息
          </button>
        </div>
      </div>
    </div>
  );
}