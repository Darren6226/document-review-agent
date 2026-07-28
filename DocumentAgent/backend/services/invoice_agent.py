"""
基于 Deep Agents 的发票审核系统
使用 Skills 机制实现模块化的校验流程
"""

import os
import sys
from typing import Optional
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from models.validation import (
    FinalValidationReport,
    AgentValidationReport,
    ValidationResult,
    ValidationLevel
)


# ==================== Skills 路径配置 ====================

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")

SKILL_PATHS = [
    "/skills/completeness",
    "/skills/format",
    "/skills/calculation",
    "/skills/business"
]


# ==================== System Prompt ====================

SYSTEM_PROMPT = """你是一个专业的中国增值税发票审核助手。

## 你的职责

根据提供的发票数据，执行以下校验：
1. **完整性校验** - 检查必填字段是否完整
2. **格式校验** - 验证发票代码、号码、税号等格式
3. **计算校验** - 验证金额、税额计算是否正确
4. **业务规则校验** - 验证税率、日期等业务逻辑

## 校验流程

1. 首先判断发票类型（专用/普通）
2. 覆盖完整性 / 格式 / 计算 / 业务规则四个维度进行校验，并在报告中按此顺序排列（非强制串行阻塞，单一推理过程即可）
3. 四个维度每个都**至少产出一条报告**（即使仅 INFO 级"已检查，未发现异常"），确保覆盖完整
4. 汇总所有校验结果
5. 生成最终报告

## 输出要求

请严格按照 FinalValidationReport 的格式输出结果，包含：
- invoice_id: 发票标识（发票代码_发票号码）
- validation_time: 校验时间
- overall_status: 总体状态（PASSED/FAILED/WARNING）
- summary: 总结说明
- agent_reports: 各维度的校验报告
"""


# ==================== Deep Agent 创建 ====================

def create_invoice_agent(
    model: str = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    debug: bool = False
):
    """
    创建发票审核 Deep Agent

    Args:
        model: 模型名称（如 "Qwen/Qwen3.6-27B"）
        api_key: API 密钥（可选，默认从环境变量读取）
        base_url: API 基础 URL（可选，默认从环境变量读取）
        debug: 是否启用调试模式

    Returns:
        CompiledStateGraph: 配置好的 Deep Agent
    """
    # 读取配置
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
    if base_url is None:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
    if model is None:
        model = "Qwen/Qwen3.6-27B"

    # 直接创建 ChatOpenAI 实例，使用标准 chat.completions API
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0
    )

    # 创建 Agent，传入 llm 实例而非字符串
    agent = create_deep_agent(
        model=llm,
        skills=SKILL_PATHS,
        system_prompt=SYSTEM_PROMPT,
        response_format=FinalValidationReport,
        debug=debug,
        name="invoice-auditor"
    )

    return agent


# ==================== 校验执行函数 ====================

def validate_invoice_with_agent_sync(
    invoice_data: dict,
    agent=None,
    model: str = None
) -> FinalValidationReport:
    """
    同步版本的发票校验 - 在新的 event loop 中运行

    注意：此函数应通过 asyncio.to_thread() 调用以避免 event loop 冲突

    Args:
        invoice_data: 发票数据字典
        agent: 预创建的 Agent（可选）
        model: 模型名称

    Returns:
        FinalValidationReport: 校验报告
    """
    import asyncio

    # 创建新的 event loop 执行异步调用（不设置为当前线程的 loop，避免冲突）
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _invoke_agent(agent, invoice_data, model)
        )
    finally:
        loop.close()


async def _invoke_agent(agent, invoice_data: dict, model: str = None):
    """异步调用 Agent"""
    import json

    # 如果没有提供 Agent，创建一个新的
    if agent is None:
        agent = create_invoice_agent(model=model)

    # 构建用户消息
    user_message = f"""请审核以下发票数据：

```json
{json.dumps(invoice_data, ensure_ascii=False, indent=2)}
```

请执行完整性、格式、计算和业务规则校验，并输出 FinalValidationReport 格式的结果。
"""

    # 调用 Agent
    try:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": user_message}]
        })
    except Exception as e:
        print(f"Agent 调用失败: {e}")
        return FinalValidationReport(
            invoice_id=f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}",
            validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            overall_status="ERROR",
            summary=f"Agent 调用失败: {str(e)[:200]}"
        )

    # 解析结果
    if "structured_response" in result:
        return result["structured_response"]
    else:
        last_message = result["messages"][-1]
        content = last_message.content if hasattr(last_message, 'content') else str(last_message)

        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                report_data = json.loads(json_match.group(0))
                return FinalValidationReport(**report_data)
            except Exception as e:
                print(f"解析报告失败: {e}")

        return FinalValidationReport(
            invoice_id=f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}",
            validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            overall_status="ERROR",
            summary=f"Agent 返回结果解析失败: {content[:200]}..."
        )


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 测试数据
    test_invoice = {
        "invoice_type": "增值税专用发票",
        "invoice_code": "3100153130",
        "invoice_number": "14641426",
        "issue_date": "2016-06-02",
        "purchaser_name": "百度时代网络技术(北京)有限公司",
        "purchaser_tax_id": "110108787751579",
        "seller_name": "上海爱信诺航天信息有限公司",
        "seller_tax_id": "310115687812026",
        "total_amount": 12580.00,
        "total_tax": 754.80,
        "total_amount_with_tax": 13334.80,
        "payee": "张三",
        "checker": "李四",
        "drawer": "王五"
    }

    print("=== 测试 Deep Agent 发票审核 ===")
    print(f"Skills 路径: {SKILLS_DIR}")
    print(f"Skill 路径列表: {SKILL_PATHS}")

    # 创建 Agent
    print("\n创建 Agent...")
    agent = create_invoice_agent(model="openai:Qwen/Qwen3.6-27B", debug=True)
    print("Agent 创建成功!")

    # 执行校验
    print("\n执行校验...")
    report = validate_invoice_with_agent_sync(test_invoice, agent)
    print(f"\n校验结果:")
    print(f"  发票ID: {report.invoice_id}")
    print(f"  状态: {report.overall_status}")
    print(f"  总结: {report.summary}")
