"""
基于真实数据的发票智能校验系统
使用 LangChain 实现多 Agent 协作的发票校验流程

适用于中国增值税专用发票和普通发票
参考真实发票数据 (发票代码: 3100153130, 发票号码: 14641426)

校验维度:
1. 完整性校验 - 验证必填字段是否完整
2. 格式校验 - 验证发票代码、号码、税号等格式
3. 计算校验 - 验证金额、税额计算是否正确
4. 业务规则校验 - 验证税率、日期等业务逻辑
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


# ==================== 数据模型 ====================

class ValidationLevel(str, Enum):
    """校验级别"""
    ERROR = "error"      # 错误 - 必须修正
    WARNING = "warning"  # 警告 - 建议关注
    INFO = "info"        # 信息 - 仅供参考


class ValidationResult(BaseModel):
    """单个校验结果"""
    agent_name: str = Field(..., description="执行校验的 Agent 名称")
    level: ValidationLevel = Field(..., description="校验级别")
    category: str = Field(..., description="校验类别")
    message: str = Field(..., description="校验消息")
    field: Optional[str] = Field(None, description="相关字段")
    expected: Optional[Any] = Field(None, description="期望值")
    actual: Optional[Any] = Field(None, description="实际值")
    suggestion: Optional[str] = Field(None, description="修正建议")


class AgentValidationReport(BaseModel):
    """Agent 校验报告"""
    agent_name: str = Field(..., description="Agent 名称")
    execution_time: float = Field(..., description="执行时间(秒)")
    results: List[ValidationResult] = Field(default_factory=list, description="校验结果列表")

    @property
    def error_count(self) -> int:
        return len([r for r in self.results if r.level == ValidationLevel.ERROR])

    @property
    def warning_count(self) -> int:
        return len([r for r in self.results if r.level == ValidationLevel.WARNING])

    @property
    def info_count(self) -> int:
        return len([r for r in self.results if r.level == ValidationLevel.INFO])


class FinalValidationReport(BaseModel):
    """最终校验报告"""
    invoice_id: str = Field(..., description="发票标识")
    validation_time: str = Field(..., description="校验时间")
    agent_reports: List[AgentValidationReport] = Field(default_factory=list, description="各 Agent 报告")
    overall_status: str = Field(..., description="总体状态: PASSED/FAILED/WARNING")
    summary: str = Field(..., description="总结")

    @property
    def total_errors(self) -> int:
        return sum(r.error_count for r in self.agent_reports)

    @property
    def total_warnings(self) -> int:
        return sum(r.warning_count for r in self.agent_reports)

    @property
    def total_info(self) -> int:
        return sum(r.info_count for r in self.agent_reports)


# ==================== 校验规则配置 ====================

# 中国增值税专用发票必填字段 (13个核心字段)
REQUIRED_FIELDS_SPECIAL = {
    'invoice_type': '发票类型',
    'invoice_code': '发票代码',
    'invoice_number': '发票号码',
    'issue_date': '开票日期',
    'purchaser_name': '购买方名称',
    'purchaser_tax_id': '购买方纳税人识别号',
    'seller_name': '销售方名称',
    'seller_tax_id': '销售方纳税人识别号',
    'total_amount': '合计金额',
    'total_tax': '合计税额',
    'total_amount_with_tax': '价税合计',
    'payee': '收款人',
    'drawer': '开票人'
}

# 普通发票必填字段 (可选校验码)
REQUIRED_FIELDS_NORMAL = {
    **REQUIRED_FIELDS_SPECIAL,
    'check_code': '校验码'
}

# 建议字段
RECOMMENDED_FIELDS = {
    'purchaser_address': '购买方地址电话',
    'purchaser_bank': '购买方开户行及账号',
    'seller_address': '销售方地址电话',
    'seller_bank': '销售方开户行及账号',
    'line_items': '商品明细',
    'checker': '复核人'
}

# 中国增值税标准税率
VALID_TAX_RATES = [0.00, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13]


# ==================== 工具函数 ====================

def validate_tax_id(tax_id: str) -> bool:
    """
    验证纳税人识别号格式

    规则:
    - 企业: 15/18/20位数字或字母
    - 统一社会信用代码: 18位
    """
    if not tax_id:
        return False

    # 去除空格和特殊字符
    tax_id = tax_id.strip()

    # 允许15/18/20位的数字或字母组合
    if len(tax_id) in [15, 18, 20]:
        return bool(re.match(r'^[A-Z0-9]+$', tax_id))

    return False


def validate_invoice_code(code: str) -> bool:
    """验证发票代码格式 (10位数字)"""
    if not code:
        return False
    return bool(re.match(r'^\d{10}$', code))


def validate_invoice_number(number: str) -> bool:
    """验证发票号码格式 (8位数字)"""
    if not number:
        return False
    return bool(re.match(r'^\d{8}$', number))


# ==================== 校验 Agent ====================

class CompletenessValidationAgent:
    """完整性校验 Agent - 验证必填字段是否完整"""

    def __init__(self):
        self.name = "完整性校验Agent"

    def validate(self, invoice_data: dict) -> AgentValidationReport:
        """验证数据完整性"""
        import time

        start_time = time.time()
        results = []

        # 判断发票类型
        invoice_type = invoice_data.get('invoice_type', '')
        is_special = '专用' in invoice_type

        # 选择对应的必填字段
        required_fields = REQUIRED_FIELDS_SPECIAL if is_special else REQUIRED_FIELDS_NORMAL

        # 检查必填字段
        missing_required = []
        for field, field_name in required_fields.items():
            value = invoice_data.get(field)

            # 特殊处理: 金额字段允许为0
            if field in ['total_amount', 'total_tax', 'total_amount_with_tax']:
                if value is None or value == '':
                    missing_required.append(field_name)
                    results.append(ValidationResult(
                        agent_name=self.name,
                        level=ValidationLevel.ERROR,
                        category="完整性校验",
                        message=f"必填字段 [{field_name}] 缺失",
                        field=field,
                        suggestion=f"请补充{field_name}信息"
                    ))
            else:
                if not value or value == '':
                    missing_required.append(field_name)
                    results.append(ValidationResult(
                        agent_name=self.name,
                        level=ValidationLevel.ERROR,
                        category="完整性校验",
                        message=f"必填字段 [{field_name}] 缺失",
                        field=field,
                        suggestion=f"请补充{field_name}信息"
                    ))

        # 检查建议字段
        missing_recommended = []
        for field, field_name in RECOMMENDED_FIELDS.items():
            value = invoice_data.get(field)
            if not value or (isinstance(value, list) and len(value) == 0):
                missing_recommended.append(field_name)
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.WARNING,
                    category="完整性校验",
                    message=f"建议字段 [{field_name}] 缺失",
                    field=field,
                    suggestion=f"建议补充{field_name}以提高发票完整性"
                ))

        # 如果所有必填字段都存在
        if not missing_required:
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.INFO,
                category="完整性校验",
                message=f"所有 {len(required_fields)} 个必填字段完整",
                suggestion=f"{'专用发票' if is_special else '普通发票'}核心信息齐全"
            ))

        execution_time = time.time() - start_time
        return AgentValidationReport(
            agent_name=self.name,
            execution_time=execution_time,
            results=results
        )


class FormatValidationAgent:
    """格式校验 Agent - 验证发票格式是否正确"""

    def __init__(self):
        self.name = "格式校验Agent"

    def validate(self, invoice_data: dict) -> AgentValidationReport:
        """验证发票格式"""
        import time

        start_time = time.time()
        results = []

        # 1. 发票代码格式校验 (10位数字)
        invoice_code = invoice_data.get('invoice_code')
        if invoice_code:
            if validate_invoice_code(invoice_code):
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="格式校验",
                    message="发票代码格式正确",
                    field="invoice_code",
                    actual=invoice_code
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="格式校验",
                    message="发票代码格式不正确",
                    field="invoice_code",
                    expected="10位数字 (如: 3100153130)",
                    actual=invoice_code,
                    suggestion="发票代码应为10位纯数字"
                ))

        # 2. 发票号码格式校验 (8位数字)
        invoice_number = invoice_data.get('invoice_number')
        if invoice_number:
            if validate_invoice_number(invoice_number):
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="格式校验",
                    message="发票号码格式正确",
                    field="invoice_number",
                    actual=invoice_number
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="格式校验",
                    message="发票号码格式不正确",
                    field="invoice_number",
                    expected="8位数字 (如: 14641426)",
                    actual=invoice_number,
                    suggestion="发票号码应为8位纯数字"
                ))

        # 3. 购买方纳税人识别号校验
        purchaser_tax_id = invoice_data.get('purchaser_tax_id')
        if purchaser_tax_id:
            if validate_tax_id(purchaser_tax_id):
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="格式校验",
                    message="购买方纳税人识别号格式正确",
                    field="purchaser_tax_id"
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="格式校验",
                    message="购买方纳税人识别号格式不正确",
                    field="purchaser_tax_id",
                    expected="15/18/20位数字或字母",
                    actual=purchaser_tax_id,
                    suggestion="纳税人识别号应为15/18/20位的数字或字母组合"
                ))

        # 4. 销售方纳税人识别号校验
        seller_tax_id = invoice_data.get('seller_tax_id')
        if seller_tax_id:
            if validate_tax_id(seller_tax_id):
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="格式校验",
                    message="销售方纳税人识别号格式正确",
                    field="seller_tax_id"
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="格式校验",
                    message="销售方纳税人识别号格式不正确",
                    field="seller_tax_id",
                    expected="15/18/20位数字或字母",
                    actual=seller_tax_id,
                    suggestion="纳税人识别号应为15/18/20位的数字或字母组合"
                ))

        # 5. 日期格式校验 (应该已经被标准化为 YYYY-MM-DD)
        issue_date = invoice_data.get('issue_date')
        if issue_date:
            try:
                date_obj = datetime.strptime(issue_date, '%Y-%m-%d')

                # 检查是否未来日期
                if date_obj > datetime.now():
                    results.append(ValidationResult(
                        agent_name=self.name,
                        level=ValidationLevel.WARNING,
                        category="格式校验",
                        message="开票日期为未来日期",
                        field="issue_date",
                        actual=issue_date,
                        suggestion="请确认开票日期是否正确"
                    ))
                else:
                    results.append(ValidationResult(
                        agent_name=self.name,
                        level=ValidationLevel.INFO,
                        category="格式校验",
                        message="开票日期格式正确",
                        field="issue_date"
                    ))
            except ValueError:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="格式校验",
                    message="开票日期格式不正确",
                    field="issue_date",
                    expected="YYYY-MM-DD (如: 2016-06-02)",
                    actual=issue_date,
                    suggestion="日期应为标准格式: YYYY-MM-DD"
                ))

        execution_time = time.time() - start_time
        return AgentValidationReport(
            agent_name=self.name,
            execution_time=execution_time,
            results=results
        )


class CalculationValidationAgent:
    """计算校验 Agent - 验证金额、税额计算是否正确"""

    def __init__(self):
        self.name = "计算校验Agent"

    def validate(self, invoice_data: dict) -> AgentValidationReport:
        """验证计算逻辑"""
        import time

        start_time = time.time()
        results = []

        total_amount = float(invoice_data.get('total_amount', 0))
        total_tax = float(invoice_data.get('total_tax', 0))
        total_with_tax = float(invoice_data.get('total_amount_with_tax', 0))

        # 1. 价税合计验证: 合计金额 + 合计税额 = 价税合计
        calculated_total = round(total_amount + total_tax, 2)
        diff = abs(calculated_total - total_with_tax)

        if diff > 0.02:  # 允许2分钱误差
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.ERROR,
                category="计算校验",
                message="价税合计计算不正确",
                field="total_amount_with_tax",
                expected=calculated_total,
                actual=total_with_tax,
                suggestion=f"合计金额 ({total_amount:.2f}) + 合计税额 ({total_tax:.2f}) = {calculated_total:.2f}, 但价税合计为 {total_with_tax:.2f}"
            ))
        else:
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.INFO,
                category="计算校验",
                message=f"价税合计计算正确: {total_amount:.2f} + {total_tax:.2f} = {total_with_tax:.2f}",
                field="total_amount_with_tax"
            ))

        # 2. 行项目金额校验
        line_items = invoice_data.get('line_items', [])
        if line_items and len(line_items) > 0:
            items_total_amount = sum(float(item.get('amount', 0)) for item in line_items)
            items_total_tax = sum(float(item.get('tax_amount', 0)) for item in line_items)

            # 金额合计校验
            amount_diff = abs(round(items_total_amount, 2) - total_amount)
            if amount_diff > 0.02:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.WARNING,
                    category="计算校验",
                    message="行项目金额合计与发票总金额不一致",
                    field="line_items",
                    expected=total_amount,
                    actual=round(items_total_amount, 2),
                    suggestion=f"行项目金额合计为 ¥{items_total_amount:.2f}, 但发票合计金额为 ¥{total_amount:.2f}"
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="计算校验",
                    message=f"行项目金额合计正确: ¥{items_total_amount:.2f}",
                    field="line_items"
                ))

            # 税额合计校验
            tax_diff = abs(round(items_total_tax, 2) - total_tax)
            if tax_diff > 0.02:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.WARNING,
                    category="计算校验",
                    message="行项目税额合计与发票总税额不一致",
                    field="line_items",
                    expected=total_tax,
                    actual=round(items_total_tax, 2),
                    suggestion=f"行项目税额合计为 ¥{items_total_tax:.2f}, 但发票合计税额为 ¥{total_tax:.2f}"
                ))
            else:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.INFO,
                    category="计算校验",
                    message=f"行项目税额合计正确: ¥{items_total_tax:.2f}",
                    field="line_items"
                ))

            # 3. 每个行项目的税额计算校验: 金额 × 税率 = 税额
            for idx, item in enumerate(line_items):
                amount = float(item.get('amount', 0))
                tax_rate = float(item.get('tax_rate', 0))
                tax_amount = float(item.get('tax_amount', 0))
                item_name = item.get('name', f'行项目{idx+1}')

                expected_tax = round(amount * tax_rate, 2)
                item_diff = abs(expected_tax - tax_amount)

                if tax_amount and item_diff > 0.02:
                    results.append(ValidationResult(
                        agent_name=self.name,
                        level=ValidationLevel.WARNING,
                        category="计算校验",
                        message=f"【{item_name}】税额计算可能有误",
                        field=f"line_items[{idx}].tax_amount",
                        expected=expected_tax,
                        actual=tax_amount,
                        suggestion=f"金额 ({amount:.2f}) × 税率 ({tax_rate*100:.0f}%) = {expected_tax:.2f}, 但实际税额为 {tax_amount:.2f}"
                    ))

        execution_time = time.time() - start_time
        return AgentValidationReport(
            agent_name=self.name,
            execution_time=execution_time,
            results=results
        )


class BusinessRuleValidationAgent:
    """业务规则校验 Agent - 验证业务逻辑规则"""

    def __init__(self, llm: Optional[ChatOpenAI] = None):
        self.name = "业务规则校验Agent"
        self.llm = llm

    def validate(self, invoice_data: dict) -> AgentValidationReport:
        """验证业务规则"""
        import time

        start_time = time.time()
        results = []

        # 1. 税率合规性校验
        line_items = invoice_data.get('line_items', [])
        for idx, item in enumerate(line_items):
            tax_rate = float(item.get('tax_rate', 0))
            item_name = item.get('name', f'行项目{idx+1}')

            # 查找最接近的标准税率
            closest_rate = min(VALID_TAX_RATES, key=lambda x: abs(x - tax_rate))
            rate_diff = abs(tax_rate - closest_rate)

            if rate_diff > 0.001:  # 允许0.1%的误差
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.WARNING,
                    category="业务规则校验",
                    message=f"【{item_name}】税率可能不符合规范",
                    field=f"line_items[{idx}].tax_rate",
                    expected=f"标准税率: {', '.join(f'{r*100:.0f}%' for r in VALID_TAX_RATES)}",
                    actual=f"{tax_rate*100:.2f}%",
                    suggestion=f"中国增值税标准税率为: 0%, 1%, 3%, 5%, 6%, 9%, 13%"
                ))

        # 2. 发票类型与字段匹配校验
        invoice_type = invoice_data.get('invoice_type', '')
        is_special = '专用' in invoice_type

        if is_special:
            # 专用发票必须有购买方税号
            if not invoice_data.get('purchaser_tax_id'):
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="业务规则校验",
                    message="增值税专用发票必须有购买方纳税人识别号",
                    field="purchaser_tax_id",
                    suggestion="专用发票要求购买方必须提供纳税人识别号"
                ))

            # 专用发票必须有三员(收款人、复核人、开票人)
            payee = invoice_data.get('payee')
            checker = invoice_data.get('checker')
            drawer = invoice_data.get('drawer')

            if not payee:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="业务规则校验",
                    message="增值税专用发票必须有收款人",
                    field="payee",
                    suggestion="请填写收款人信息"
                ))

            if not drawer:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.ERROR,
                    category="业务规则校验",
                    message="增值税专用发票必须有开票人",
                    field="drawer",
                    suggestion="请填写开票人信息"
                ))

        # 3. 金额合理性校验
        total_with_tax = float(invoice_data.get('total_amount_with_tax', 0))

        if total_with_tax < 0:
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.ERROR,
                category="业务规则校验",
                message="发票金额不能为负数",
                field="total_amount_with_tax",
                actual=total_with_tax,
                suggestion="请检查发票金额是否正确"
            ))
        elif total_with_tax > 10000000:  # 超过1000万
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.WARNING,
                category="业务规则校验",
                message="发票金额异常大 (超过1000万)",
                field="total_amount_with_tax",
                actual=f"¥{total_with_tax:,.2f}",
                suggestion="请确认大额发票是否正确"
            ))

        # 4. 如果有 LLM,使用 AI 进行深度业务规则校验
        if self.llm:
            try:
                llm_results = self._validate_with_llm(invoice_data)
                results.extend(llm_results)
            except Exception as e:
                results.append(ValidationResult(
                    agent_name=self.name,
                    level=ValidationLevel.WARNING,
                    category="业务规则校验",
                    message=f"AI 业务规则校验执行出错: {str(e)}",
                    suggestion="请手动检查业务规则"
                ))

        # 如果没有发现问题
        if not results:
            results.append(ValidationResult(
                agent_name=self.name,
                level=ValidationLevel.INFO,
                category="业务规则校验",
                message="未发现明显的业务逻辑问题"
            ))

        execution_time = time.time() - start_time
        return AgentValidationReport(
            agent_name=self.name,
            execution_time=execution_time,
            results=results
        )

    def _validate_with_llm(self, invoice_data: dict) -> List[ValidationResult]:
        """使用 LLM 进行智能业务规则校验"""
        results = []

        prompt = f"""你是一个专业的中国增值税发票审核专家。请分析以下发票数据,检查是否存在业务逻辑问题:

发票数据:
{json.dumps(invoice_data, ensure_ascii=False, indent=2)}

请重点检查:
1. 购买方和销售方是否为同一主体(自己开票给自己)
2. 商品或服务描述是否清晰合理
3. 单价、数量、金额是否合理匹配
4. 是否存在明显的数据异常

请以 JSON 格式返回校验结果,格式如下:
{{
  "issues": [
    {{
      "level": "error|warning|info",
      "message": "问题描述",
      "field": "相关字段",
      "suggestion": "修正建议"
    }}
  ]
}}

如果没有发现问题,返回空的 issues 数组。只返回 JSON,不要其他说明。
"""

        response = self.llm.invoke([
            SystemMessage(content="你是一个专业的发票审核专家,擅长发现发票中的业务逻辑问题。"),
            HumanMessage(content=prompt)
        ])

        # 提取 JSON
        response_text = response.content
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

        if json_match:
            llm_result = json.loads(json_match.group(0))
            issues = llm_result.get('issues', [])

            for issue in issues:
                level_str = issue.get('level', 'info').lower()
                level = ValidationLevel.ERROR if level_str == 'error' else \
                        ValidationLevel.WARNING if level_str == 'warning' else \
                        ValidationLevel.INFO

                results.append(ValidationResult(
                    agent_name=self.name,
                    level=level,
                    category="业务规则校验",
                    message=issue.get('message', ''),
                    field=issue.get('field'),
                    suggestion=issue.get('suggestion')
                ))

        return results


# ==================== 协调 Agent ====================

class ValidationOrchestratorAgent:
    """校验协调 Agent - 负责编排所有校验流程"""

    def __init__(self, llm: Optional[ChatOpenAI] = None):
        self.llm = llm

        # 初始化所有校验 Agent (按顺序执行)
        self.agents = [
            CompletenessValidationAgent(),       # 1. 先检查完整性
            FormatValidationAgent(),             # 2. 再检查格式
            CalculationValidationAgent(),        # 3. 然后检查计算
            BusinessRuleValidationAgent(llm),    # 4. 最后检查业务规则
        ]

    def orchestrate(self, invoice_data: dict) -> FinalValidationReport:
        """编排执行所有校验"""
        print("\n" + "="*60)
        print("开始发票校验流程")
        print("="*60)

        agent_reports = []

        # 依次执行各个 Agent
        for agent in self.agents:
            print(f"\n>>> 执行 {agent.name}...")
            report = agent.validate(invoice_data)
            agent_reports.append(report)

            # 输出简要结果
            print(f"    ✓ 完成 (耗时: {report.execution_time:.2f}秒)")
            print(f"    - 错误: {report.error_count}, 警告: {report.warning_count}, 信息: {report.info_count}")

        # 生成最终报告
        total_errors = sum(r.error_count for r in agent_reports)
        total_warnings = sum(r.warning_count for r in agent_reports)

        # 确定总体状态
        if total_errors > 0:
            overall_status = "FAILED"
            summary = f"发票校验未通过: 发现 {total_errors} 个错误, {total_warnings} 个警告"
        elif total_warnings > 0:
            overall_status = "WARNING"
            summary = f"发票校验通过但有警告: 发现 {total_warnings} 个警告"
        else:
            overall_status = "PASSED"
            summary = "发票校验完全通过,未发现任何问题"

        # 生成发票ID
        invoice_code = invoice_data.get('invoice_code', 'N/A')
        invoice_number = invoice_data.get('invoice_number', 'N/A')
        invoice_id = f"{invoice_code}_{invoice_number}"

        final_report = FinalValidationReport(
            invoice_id=invoice_id,
            validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            agent_reports=agent_reports,
            overall_status=overall_status,
            summary=summary
        )

        return final_report


# ==================== 主系统 ====================

class InvoiceValidationSystem:
    """发票校验系统 - 整合提取和校验"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
      model_name: str = "Qwen/Qwen3.6-27B",
       enable_llm_validation: bool = False
    ):
        """
        初始化校验系统

        Args:
            api_key: API密钥 (如果不提供，则不使用 LLM 进行业务规则校验)
            base_url: API 地址 (默认从 OPENAI_BASE_URL 环境变量读取，其次使用硅基流动地址)
          model_name: 模型名称
           enable_llm_validation: 是否启用 LLM 业务规则校验
        """
        # 从环境变量获取配置
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        
        self.llm = None

        if enable_llm_validation and self.api_key:
            self.llm = ChatOpenAI(
              model=model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=0.1,
            )

        self.orchestrator = ValidationOrchestratorAgent(self.llm)

    def validate_invoice(self, invoice_data: dict) -> FinalValidationReport:
        """执行完整的发票校验"""
        return self.orchestrator.orchestrate(invoice_data)

    def print_report(self, report: FinalValidationReport):
        """打印校验报告"""
        print("\n" + "="*60)
        print("发票校验报告")
        print("="*60)
        print(f"发票ID: {report.invoice_id}")
        print(f"校验时间: {report.validation_time}")
        print(f"总体状态: {report.overall_status}")
        print(f"总结: {report.summary}")
        print(f"\n统计: 错误 {report.total_errors} | 警告 {report.total_warnings} | 信息 {report.total_info}")

        # 打印各 Agent 详细结果
        for agent_report in report.agent_reports:
            if not agent_report.results:
                continue

            print(f"\n{'─'*60}")
            print(f"【{agent_report.agent_name}】 (耗时: {agent_report.execution_time:.2f}秒)")
            print(f"{'─'*60}")

            for result in agent_report.results:
                icon = "✗" if result.level == ValidationLevel.ERROR else \
                       "⚠" if result.level == ValidationLevel.WARNING else "✓"

                print(f"\n{icon} [{result.level.value.upper()}] {result.message}")
                if result.field:
                    print(f"   字段: {result.field}")
                if result.expected is not None:
                    print(f"   期望: {result.expected}")
                if result.actual is not None:
                    print(f"   实际: {result.actual}")
                if result.suggestion:
                    print(f"   建议: {result.suggestion}")

        print("\n" + "="*60)


# ==================== 使用示例 ====================

def main():
    """使用示例"""

    # 初始化系统 (不使用 LLM 业务规则校验)
    system = InvoiceValidationSystem(
        enable_llm_validation=False  # 设置为 True 并提供 api_key 可启用 LLM 校验
    )

    # 读取已提取的发票数据
    with open("invoice_extracted.json", "r", encoding="utf-8") as f:
        invoice_data = json.load(f)

    # 执行校验
    report = system.validate_invoice(invoice_data)

    # 打印报告
    system.print_report(report)

    # 导出报告
    with open("validation_report.json", "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2, exclude_none=False))

    print(f"\n✓ 校验报告已导出到 validation_report.json")


if __name__ == "__main__":
    main()
