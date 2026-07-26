import { ArrowLeft, CheckCircle } from 'lucide-react';
import { useState } from 'react';

interface ChecklistItem {
  id: number;
  text: string;
  checked: boolean;
}

interface ContractReviewChecklistProps {
  onBack: () => void;
}

export function ContractReviewChecklist({ onBack }: ContractReviewChecklistProps) {
  const [checklist, setChecklist] = useState<ChecklistItem[]>([
    // 一、文本规范性审核
    { id: 1, text: '1.1 错别字与形近字检查（形近字、同音字、笔误、多字、漏字）', checked: true },
    { id: 2, text: '1.2 标点符号规范性（句号、逗号、顿号、分号、冒号、括号引号配对）', checked: true },
    { id: 3, text: '1.3 语法结构检查（主谓宾搭配、成分完整性、避免歧义性表述）', checked: true },

    // 二、合同专业性审核 (核心)
    { id: 4, text: '2.1 法律术语规范性（"违约金"非"罚款"、"解除合同"非"取消合同"）', checked: true },
    { id: 5, text: '2.2 权利义务对等性（甲乙方权利义务明确、对等，避免显失公平）', checked: true },
    { id: 6, text: '2.3 金额与数字准确性（大写小写一致、重要金额必须大写+小写）', checked: true },
    { id: 7, text: '2.4 时间条款明确性（合同期限明确、避免"尽快"、"及时"等模糊词）', checked: true },

    // 三、逻辑一致性审核
    { id: 8, text: '3.1 条款前后一致性（同一概念表述一致、数字金额一致、甲乙方名称一致）', checked: true },
    { id: 9, text: '3.2 条款间逻辑矛盾（不同条款是否矛盾、违约金与赔偿损失关系明确）', checked: true },
    { id: 10, text: '3.3 引用条款准确性（条款编号引用准确、附件编号存在、法律法规引用准确）', checked: true },

    // 四、合规性与风险审核 (P0级)
    { id: 11, text: '4.1 法律合规性（是否违反法律强制性规定、是否存在无效条款）', checked: true },
    { id: 12, text: '4.2 敏感词汇检查（避免歧视性语言、避免绝对化承诺）', checked: true },
    { id: 13, text: '4.3 必备条款完整性（主体信息、标的物、价款、履行期限、违约责任、争议解决）', checked: true },

    // 五、表述清晰度审核
    { id: 14, text: '5.1 歧义性表述（多义词导致歧义、"和"/"或"/"及"/"与"连接词准确性）', checked: true },
    { id: 15, text: '5.2 冗余与重复（不必要的重复、冗余修饰语、过长条款）', checked: true },
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

  return (
    <div className="h-full flex flex-col glass-effect">
      {/* 头部 */}
      <div className="p-6 border-b border-white/30 glass-effect-dark">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-all duration-300 hover:scale-105 hover:gap-3"
        >
          <ArrowLeft className="w-4 h-4" />
          返回
        </button>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl gradient-text mb-1">审查清单</h2>
            <p className="text-sm text-gray-500">智能生成</p>
          </div>
          <button className="px-6 py-2.5 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 text-white rounded-xl hover:from-blue-600 hover:via-purple-600 hover:to-pink-600 transition-all duration-300 shadow-lg hover:shadow-xl hover:scale-105 flex items-center gap-2">
            <CheckCircle className="w-4 h-4" />
            重新发起审查
          </button>
        </div>
      </div>

      {/* 全选和计数 */}
      <div className="px-6 py-4 border-b border-white/30 flex items-center justify-between bg-gradient-to-r from-blue-50/50 to-purple-50/50">
        <div className="flex items-center gap-3">
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
        </div>
        <div className="text-sm text-gray-600">
          已选择 <span className="font-semibold text-blue-600">{checkedCount}</span> 项
        </div>
      </div>

      {/* 审查清单 */}
      <div className="flex-1 overflow-auto p-6">
        <div className="space-y-2">
          {checklist.map((item) => (
            <div
              key={item.id}
              onClick={() => handleItemCheck(item.id)}
              className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-300 ${
                item.checked
                  ? 'bg-blue-50 border-blue-200 hover:bg-blue-100 hover:shadow-md'
                  : 'bg-white border-gray-200 hover:bg-gray-50 hover:shadow-sm'
              }`}
            >
              <input
                type="checkbox"
                checked={item.checked}
                onChange={() => {}}
                className="w-4 h-4 mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <div className="flex-1">
                <span className={`text-sm ${item.checked ? 'text-gray-900' : 'text-gray-500'}`}>
                  {item.id}. {item.text}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 底部保存按钮 */}
      <div className="p-6 border-t border-white/30 glass-effect-dark flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-100 text-blue-700 rounded-lg font-medium">
            <span className="text-xs">PRO</span>
          </span>
          自定义审查规则
        </div>
        <button className="px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all duration-300 shadow-lg hover:shadow-xl hover:scale-105 font-medium">
          保存至新清单
        </button>
      </div>
    </div>
  );
}
