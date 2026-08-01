"""
合同类型识别服务。

体现 Harness Engineering 优化 1「合同类型识别 + 动态 Skill 加载」：
- 轻量 LLM 调用，识别合同类型（劳动/买卖/租赁/借款/通用）
- 结果用于动态加载对应类型的专属 Skill（progressive disclosure）

这是整个审核流程的第一步，确定类型后才能加载正确的审核规则。
识别失败时降级为 GENERAL，保证流程不中断。
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from models.validation import ContractType


# ==================== Prompt ====================

CLASSIFIER_SYSTEM_PROMPT = """你是合同类型识别专家。你的任务是判断给定合同文本属于以下哪一类型：

- labor：劳动合同（雇主与员工之间，涉及工资、社保、工时、解除条件、竞业限制等）
- sales：买卖合同（买方与卖方之间，涉及标的物交付、价款、验收、风险转移等）
- lease：租赁合同（出租方与承租方之间，涉及租金、租期、维修责任、优先续租权等）
- loan：借款合同（出借方与借款方之间，涉及本金、利率、还款方式、担保等）
- general：通用/其他（无法归入上述四类的合同，如服务合同、合作协议等）

判断依据（按优先级）：
1. 合同标题是最强信号（如"劳动合同"、"房屋租赁合同"、"借款协议"）
2. 合同主体关系（雇主-员工 / 买方-卖方 / 出租-承租 / 出借-借款）
3. 核心条款内容（工资 / 价款 / 租金 / 利率）

只返回 JSON，格式：{{"type": "labor|sales|lease|loan|general", "confidence": 0.0-1.0, "reason": "简短原因"}}"""

CLASSIFIER_USER_PROMPT = """请判断以下合同文本的类型：

{text}

只返回 JSON，不要其他文字。"""


# ==================== 类型识别函数 ====================

def classify_contract(text: str, llm: Optional[ChatOpenAI] = None) -> tuple[ContractType, float, str]:
    """识别合同类型。

    Args:
        text: 合同文本内容
        llm: 可选的 LLM 实例（默认创建新的）

    Returns:
        tuple[ContractType, float, str]: (合同类型, 置信度 0-1, 原因说明)
    """
    if llm is None:
        llm = _create_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", CLASSIFIER_SYSTEM_PROMPT),
        ("user", CLASSIFIER_USER_PROMPT)
    ])

    # 只取前 2000 字符做类型识别（标题和开头通常足够判断类型）
    truncated_text = text[:2000] if len(text) > 2000 else text

    chain = prompt | llm | JsonOutputParser()

    try:
        result = chain.invoke({"text": truncated_text})
        type_str = result.get("type", "general")
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "")

        # 映射到 ContractType 枚举
        type_map = {
            "labor": ContractType.LABOR,
            "sales": ContractType.SALES,
            "lease": ContractType.LEASE,
            "loan": ContractType.LOAN,
            "general": ContractType.GENERAL,
        }
        contract_type = type_map.get(type_str, ContractType.GENERAL)

        return contract_type, confidence, reason

    except Exception as e:
        print(f"[warn] 合同类型识别失败，降级为 GENERAL: {e}")
        return ContractType.GENERAL, 0.0, f"识别失败: {e}"


def _create_llm() -> ChatOpenAI:
    """创建 LLM 实例（轻量配置，类型识别不需要大 token）。"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")

    if not api_key:
        raise ValueError("请设置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY 环境变量")

    return ChatOpenAI(
        model="Qwen/Qwen3.6-27B",
        temperature=0,
        max_tokens=200,  # 类型识别只需要很短的输出
        timeout=30,
        openai_api_key=api_key,
        openai_api_base=base_url
    )


# ==================== 类型对应的 Skill 文件名 ====================

TYPE_SKILL_MAP = {
    ContractType.LABOR: "labor.md",
    ContractType.SALES: "sales.md",
    ContractType.LEASE: "lease.md",
    ContractType.LOAN: "loan.md",
    ContractType.GENERAL: None,  # 通用类型不加载专属 skill
}


def get_skill_filename(contract_type: ContractType) -> Optional[str]:
    """根据合同类型返回对应的专属 Skill 文件名。

    通用类型返回 None（只使用通用规则 SKILL.md）。
    """
    return TYPE_SKILL_MAP.get(contract_type)
