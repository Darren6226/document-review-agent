"""
合同信息提取模块
用于从合同文本中提取关键信息：甲方、乙方、合同金额、履行期限等
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import os
import json


# ============================================
# 数据结构定义
# ============================================

class ContractOverview(BaseModel):
    """合同概览信息"""
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    # 基本信息
    contract_type: str = Field(default="", description="合同类型，如：劳动合同、买卖合同、服务合同等")
    contract_title: str = Field(default="", description="合同标题")

    # 主体信息
    party_a: str = Field(default="", description="甲方（公司/个人名称）")
    party_a_type: str = Field(default="", description="甲方类型：公司/个人")
    party_a_details: str = Field(default="", description="甲方详细信息（如统一社会信用代码、地址等）")

    party_b: str = Field(default="", description="乙方（公司/个人名称）")
    party_b_type: str = Field(default="", description="乙方类型：公司/个人")
    party_b_details: str = Field(default="", description="乙方详细信息（如身份证号、地址等）")

    # 金额信息
    total_amount: str = Field(default="", description="合同总金额（如有）")
    amount_in_words: str = Field(default="", description="金额大写")
    currency: str = Field(default="人民币", description="币种")

    # 时间信息
    effective_date: str = Field(default="", description="合同生效日期")
    expiry_date: str = Field(default="", description="合同到期日期")
    duration: str = Field(default="", description="合同期限/履行期限")
    signing_date: str = Field(default="", description="签订日期")

    # 其他关键信息
    key_terms: List[str] = Field(default_factory=list, description="关键条款摘要（如工资、违约责任等）")
    special_clauses: str = Field(default="", description="特殊条款说明")


# ============================================
# Prompt模板
# ============================================

CONTRACT_EXTRACTION_SYSTEM_PROMPT = """你是一个专业的合同信息提取助手。

你的任务是从合同文本中准确提取**主要合同**的关键信息，包括：
1. 合同类型和标题
2. 甲方、乙方的名称和详细信息
3. 合同金额（总金额、币种）
4. 时间信息（生效日期、到期日期、履行期限）
5. 关键条款摘要（2-5条重要条款即可）

**重要提示：**
- 文档可能包含多个表单或合同模板，请只提取**第一个主要合同**的信息
- 忽略其他附属表单、通知书、意向书等
- 专注于提取合同的核心要素

**提取原则：**
- 必须从原文中精确提取，不要推测或编造
- 如果某项信息在原文中不存在，则保持为空字符串""
- 对于金额，要同时提取数字和大写形式
- 对于日期，保持原文格式
- 甲方通常是用人单位/出卖方/服务提供方（如"AA公司"、公司名称等）
- 乙方通常是员工/买受方/服务接受方（如员工姓名等）

**字段识别指南：**
- contract_type: 合同类型（如"劳动合同"、"解除劳动合同协议书"、"买卖合同"等）
- contract_title: 合同完整标题
- party_a: 甲方名称（精确提取公司/个人名称，如"AA公司"、"北京XX科技有限公司"）
- party_b: 乙方名称（精确提取姓名或公司名）
- total_amount: 合同金额的数字部分（如"5000元"、"¥5000"）
- effective_date: 生效日期（如"2024年1月1日"）
- expiry_date: 到期/终止日期
- key_terms: 提取2-5条最重要的条款内容

**输出要求：**
- 准确性优先于完整性
- 保持原文表述，不要改写
- 只返回要求的字段，不要添加额外字段
"""

CONTRACT_EXTRACTION_USER_PROMPT = """请从以下合同文本中提取关键信息：

{text}

**重要提醒：**
1. 只提取以下字段：contract_type, contract_title, party_a, party_a_type, party_a_details, party_b, party_b_type, party_b_details, total_amount, amount_in_words, currency, effective_date, expiry_date, duration, signing_date, key_terms, special_clauses
2. 不要添加其他额外字段（如各种通知书、意向书的内容）
3. 如果文档中没有某个字段的信息，该字段留空即可（使用空字符串 "" 或空列表 []）
4. 专注于提取第一个主要合同的核心信息

**重要**：必须仅返回纯 JSON 格式，不要包含任何其他文字、markdown 标记或说明。

JSON 格式示例：
{{
  "contract_type": "劳动合同",
  "contract_title": "劳动合同",
  "party_a": "北京某某科技有限公司",
  "party_a_type": "公司",
  "party_a_details": "统一社会信用代码：91110000XXXXXXXXXX",
  "party_b": "张三",
  "party_b_type": "个人",
  "party_b_details": "身份证号：110101199001011234",
  "total_amount": "¥5,000",
  "amount_in_words": "人民币伍仟元整",
  "currency": "人民币",
  "effective_date": "2024年1月1日",
  "expiry_date": "2027年12月31日",
  "duration": "三年",
  "signing_date": "2024年1月1日",
  "key_terms": ["工资待遇：月工资人民币伍仟元整", "合同期限：2024年1月1日至2027年12月31日"],
  "special_clauses": ""
}}

请开始提取并直接返回 JSON。
"""


# ============================================
# 合同信息提取函数
# ============================================

def create_extraction_chain():
    """创建合同信息提取 Chain"""

    # API 配置 - 优先从环境变量读取，支持硅基流动等兼容 OpenAI API 的服务
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")

    if not api_key:
        raise ValueError("请设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY 环境变量")

    # 创建 Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", CONTRACT_EXTRACTION_SYSTEM_PROMPT),
        ("user", CONTRACT_EXTRACTION_USER_PROMPT)
    ])

    # 创建 LLM
    # 注意：硅基流动模型名称格式为 "Qwen/Qwen2.5-7B-Instruct" 等
    llm = ChatOpenAI(
        model="Qwen/Qwen3.6-27B",
        temperature=0,  # 信息提取需要确定性，温度设为 0
        max_tokens=4000,
        timeout=120,  # 添加超时设置
        openai_api_key=api_key,
        openai_api_base=base_url
    )

    # 使用 JsonOutputParser 而不是 with_structured_output
    # 因为某些模型不支持 with_structured_output
    output_parser = JsonOutputParser()

    # 创建 Chain
    extraction_chain = prompt | llm | output_parser

    return extraction_chain


def extract_contract_info(text: str) -> ContractOverview:
    """
    从合同文本中提取关键信息

    Args:
        text: 合同文本内容

    Returns:
        ContractOverview: 提取的合同概览信息
    """
    chain = create_extraction_chain()

    try:
        result = chain.invoke({"text": text})

        # 检查是否成功解析
        if result is None:
            print("⚠️ JSON 解析返回 None，使用默认的空对象")
            return ContractOverview()

        # 将字典转换为 ContractOverview 对象
        return ContractOverview(**result)

    except Exception as e:
        print(f"⚠️ 信息提取失败: {e}")
        print("使用默认的空对象")
        return ContractOverview()


def extract_contract_info_dict(text: str) -> dict:
    """
    从合同文本中提取关键信息（返回字典格式）

    Args:
        text: 合同文本内容

    Returns:
        dict: 提取的合同概览信息
    """
    result = extract_contract_info(text)
    return result.model_dump()


# ============================================
# 测试代码
# ============================================

if __name__ == "__main__":
    # 测试文本（使用更完整的劳动合同示例）
    test_contract = """
    劳动合同

    甲方：北京某某科技有限公司
    统一社会信用代码：91110000XXXXXXXXXX
    地址：北京市海淀区中关村大街1号
    法定代表人：张总

    乙方：张三
    身份证号：110101199001011234
    住址：北京市朝阳区望京街道100号

    一、合同期限
    本合同自2024年1月1日起生效，至2027年12月31日止，期限为三年。
    乙方应于本合同签订后三日内到岗报到。

    二、工资待遇
    乙方月工资为人民币伍仟元整（¥5,000），甲方应于每月15日前以银行转账方式支付上月工资。

    三、违约责任
    如甲方未按时支付工资，应向乙方支付违约金。
    如乙方违约，应赔偿甲方因此造成的实际经济损失。

    四、其他
    本合同一式两份，甲乙双方各执一份。

    甲方（签章）：北京某某科技有限公司
    乙方（签字）：张三
    签订日期：2024年1月1日
    """

    print("="*80)
    print("测试合同信息提取")
    print("="*80)

    try:
        result = extract_contract_info(test_contract)

        print("\n【提取结果】")
        print("-"*80)
        print(f"合同类型: {result.contract_type}")
        print(f"合同标题: {result.contract_title}")
        print(f"\n甲方: {result.party_a}")
        print(f"甲方类型: {result.party_a_type}")
        print(f"甲方详情: {result.party_a_details}")
        print(f"\n乙方: {result.party_b}")
        print(f"乙方类型: {result.party_b_type}")
        print(f"乙方详情: {result.party_b_details}")
        print(f"\n合同金额: {result.total_amount}")
        print(f"金额大写: {result.amount_in_words}")
        print(f"币种: {result.currency}")
        print(f"\n生效日期: {result.effective_date}")
        print(f"到期日期: {result.expiry_date}")
        print(f"履行期限: {result.duration}")
        print(f"签订日期: {result.signing_date}")
        print(f"\n关键条款: {result.key_terms}")
        print(f"特殊条款: {result.special_clauses}")

        print("\n" + "="*80)
        print("✅ 测试成功！")
        print("="*80)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
