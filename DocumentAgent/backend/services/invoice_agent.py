"""
基于 Deep Agents 的发票审核系统
采用「主 Agent 三阶段编排 + 4 个维度 Sub-Agent + Skills 真正生效」架构：

  - 三阶段编排：完整性（串行优先）→ 格式（串行）→ 计算 ∥ 业务（并行）
  - 每个维度 Sub-Agent 通过 FilesystemBackend 读取对应 SKILL.md 正文作为校验依据
    （修复了此前 skills 悬空未加载的根因）
  - 主 Agent 汇总各 Sub-Agent 的单层 JSON 数组，组装 FinalValidationReport
    （response_format 主路径 + Python 解析兜底，保证四维分项始终存在）

对外接口（create_invoice_agent / validate_invoice_with_agent_sync）保持不变，对 FastAPI/前端零改动。
"""

import os
import sys
import re
import json
import asyncio
from typing import Optional
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from deepagents import create_deep_agent, SubAgent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_openai import ChatOpenAI

from models.validation import (
    FinalValidationReport,
    AgentValidationReport,
    ValidationResult,
    ValidationLevel
)
from tools.invoice_tools import verify_invoice_calculation


# ==================== 路径与 Backend 配置 ====================

# backend 目录：本文件位于 <root>/backend/services/，上两级即 <root>/backend
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 关键修复：配置 FilesystemBackend，使 POSIX 虚拟路径 /skills/... 映射到磁盘 <root>/backend/skills/...
# virtual_mode=True 时：/skills/completeness/SKILL.md -> BACKEND_ROOT/skills/completeness/SKILL.md
BACKEND = FilesystemBackend(root_dir=BACKEND_ROOT, virtual_mode=True)

# skills 源：框架（deepagents SkillsMiddleware._list_skills）只扫描 source 路径的
# 「直接子目录」中带 SKILL.md 的目录作为可用 skill。
# 因此若传 /skills（含 completeness/format/calculation/business 四个子目录），
# 每个 Sub-Agent 都会被注入全部 4 个 skill 的元数据、并在启动时 download+解析全部 4 个 SKILL.md，
# 造成无关 token 与解析开销。
#
# 优化：为每个维度建一个「单 skill 包装目录」（如 /skills/completeness_only/completeness/SKILL.md），
# 各 Sub-Agent 只传自己维度的包装目录，从而在 system prompt 只注入本维度 skill 元数据、
# 只 download+解析本维度 SKILL.md（正文仍由各自写死的 read_file 读取，与 skills 参数无关）。
# 包装目录内容在模块加载时由 _sync_skill_wrappers() 从真实 skill 目录同步（已存在则跳过），零维护。
SKILLS_SOURCE = {
    "completeness": ["/skills/completeness_only"],
    "format": ["/skills/format_only"],
    "calculation": ["/skills/calculation_only"],
    "business": ["/skills/business_only"],
}


def _sync_skill_wrappers() -> None:
    """把每个真实 skill 目录同步到对应的单 skill 包装目录。

    框架要求 source 下直接子目录含 SKILL.md，故包装目录结构为：
        /skills/<dim>_only/<dim>/SKILL.md (+ references/)
    使用 copytree（dirs_exist_ok），仅首次或内容变化时落盘，之后跳过，开销可忽略。
    """
    import shutil

    for dim in ("completeness", "format", "calculation", "business"):
        src = os.path.join(BACKEND_ROOT, "skills", dim)
        # 包装目录：<skills>/<dim>_only/<dim>/，使 source=/skills/<dim>_only 下恰有一个含 SKILL.md 的子目录
        wrapper_parent = os.path.join(BACKEND_ROOT, "skills", f"{dim}_only")
        dst = os.path.join(wrapper_parent, dim)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        # 仅复制 SKILL.md 与 references/（保持与真实 skill 目录内容一致）
        for entry in ("SKILL.md", "references"):
            src_entry = os.path.join(src, entry)
            if not os.path.exists(src_entry):
                continue
            dst_entry = os.path.join(dst, entry)
            if os.path.isdir(src_entry):
                shutil.copytree(src_entry, dst_entry, dirs_exist_ok=True)
            else:
                shutil.copy2(src_entry, dst_entry)


# ==================== Sub-Agent 行为契约（system_prompt） ====================

# 各 Sub-Agent 必读的规则文件路径（写死路径，配合 FilesystemBackend 直接 read_file）
SKILL_FILES = {
    "completeness": "/skills/completeness/SKILL.md",
    "format": "/skills/format/SKILL.md",
    "calculation": "/skills/calculation/SKILL.md",
    "business": "/skills/business/SKILL.md",
}

# 统一的输出字段说明（对齐 ValidationResult 的字段）
OUTPUT_CONTRACT = """只输出一个 JSON 数组作为你的最终且唯一的消息。数组每个元素是一个校验结果对象，字段如下：
  {
    "agent_name": "<本维度 Agent 名称>",
    "level": "error" | "warning" | "info",
    "category": "<本维度中文类别>",
    "message": "校验结果描述",
    "field": "字段名（无则为 null）",
    "expected": "期望情况（无则为 null）",
    "actual": "实际情况（无则为 null）",
    "suggestion": "修正建议（无则为 null）"
  }
不要输出任何额外解释文字、不要使用 markdown 代码块包裹、不要输出数组以外的任何内容。
即使某类检查无异常，也必须至少产出一条 info 级结果（如"已检查，未发现异常"）。"""


def _build_subagent_prompt(dim_key: str, dim_name: str, dim_category: str, extra: str = "") -> str:
    return f"""你是发票「{dim_name}」专项子代理。请严格按照以下步骤工作：

1. 使用 read_file 工具读取规则文件：{SKILL_FILES[dim_key]}，获取完整校验规则正文（这是你唯一的校验依据）。
2. 依据规则对用户提供的发票 JSON 数据进行本维度校验。
{extra}
{OUTPUT_CONTRACT.replace('<本维度 Agent 名称>', dim_name + 'Agent').replace('<本维度中文类别>', dim_category)}
"""


COMPLETENESS_PROMPT = _build_subagent_prompt(
    "completeness", "完整性校验", "完整性校验",
    extra="3. 根据发票类型（含\"专用\"→专用发票，否则普通发票）判断必填字段，检查必填字段与建议字段是否齐全。\n",
)

FORMAT_PROMPT = _build_subagent_prompt(
    "format", "格式校验", "格式校验",
    extra="3. 验证发票代码、发票号码、纳税人识别号、开票日期、金额等字段的格式是否符合规范。\n",
)

CALCULATION_PROMPT = _build_subagent_prompt(
    "calculation", "计算校验", "计算校验",
    extra=(
        "3. 必须使用 verify_invoice_calculation 工具获取确定性计算结果，再将每条结果映射为上述输出格式"
        "（status=PASS→info；FAIL→按结果 level；SKIP→info）。禁止自行心算。\n"
        "4. 若依赖字段缺失或非数字（应由 completeness/format 判错），跳过对应勾稽项并输出一条 info："
        "\"因前置字段缺失或格式异常，未执行[具体项]计算校验\"，不要重复报 error/warning。\n"
    ),
)

BUSINESS_PROMPT = _build_subagent_prompt(
    "business", "业务规则校验", "业务规则校验",
    extra=(
        "3. 验证税率合规性、发票类型与字段匹配（如专用发票买卖税号相同→warning）、金额合理性等业务逻辑。\n"
        "4. 若前置字段缺失（应由 completeness 判错），跳过对应业务项并输出一条 info："
        "\"因前置字段缺失，未执行[具体项]业务校验\"，不要重复报 error。\n"
    ),
)


# ==================== Sub-Agent 定义 ====================

def _build_subagents(model) -> list[SubAgent]:
    # 每个 Sub-Agent 都继承主模型实例（resolve_model 对 ChatOpenAI 返回自身），
    # 加载全部 skill 元数据（skills=["/skills"]），并由各自 system_prompt 约束只读取对应维度。
    return [
        {
            "name": "completeness",
            "description": "发票完整性校验：检查必填字段与建议字段是否齐全。应在其它维度之前优先执行（硬前置）。",
            "system_prompt": COMPLETENESS_PROMPT,
            "skills": SKILLS_SOURCE["completeness"],
            "tools": [],
            "model": model,
        },
        {
            "name": "format",
            "description": "发票格式校验：验证发票代码/号码/税号/日期/金额的格式。依赖完整性结论，应在完整性之后执行。",
            "system_prompt": FORMAT_PROMPT,
            "skills": SKILLS_SOURCE["format"],
            "tools": [],
            "model": model,
        },
        {
            "name": "calculation",
            "description": "发票计算校验：验证金额、税额、价税合计计算是否正确，使用 verify_invoice_calculation 工具。可与业务校验并行。",
            "system_prompt": CALCULATION_PROMPT,
            "skills": SKILLS_SOURCE["calculation"],
            "tools": [verify_invoice_calculation],
            "model": model,
        },
        {
            "name": "business",
            "description": "发票业务规则校验：验证税率合规性、发票类型与字段匹配、金额合理性等业务逻辑。可与计算校验并行。",
            "system_prompt": BUSINESS_PROMPT,
            "skills": SKILLS_SOURCE["business"],
            "tools": [],
            "model": model,
        },
    ]


# ==================== 主 Agent 编排 system_prompt ====================

ORCHESTRATOR_PROMPT = """你是一个发票审核总编排 Agent。你不直接做字段级校验，而是把审核工作分派给 4 个专项子代理，最后把它们的产出汇总成一份 FinalValidationReport。

你拥有 task 工具，可调用以下 4 个专项子代理（通过 subagent_type 指定）：
- completeness：完整性校验（必填/建议字段是否齐全）
- format：格式校验（发票代码/号码/税号/日期/金额格式）
- calculation：计算校验（金额/税额/价税合计计算是否正确）
- business：业务规则校验（税率合规、类型匹配、金额合理性等）

## 严格按三阶段执行
阶段 A（完整性，先执行并等待其返回）：调用 task，subagent_type=completeness，把完整发票 JSON 作为任务描述交给它。
阶段 B（格式，串行，参考阶段 A 结论）：调用 task，subagent_type=format，把完整发票 JSON 交给它。
阶段 C（计算与业务，并行）：在【同一条消息中】同时发起两个 task 调用——subagent_type=calculation 与 subagent_type=business，把完整发票 JSON 交给它们，并行等待两份返回。

注意：不要调用名为 general-purpose 的子代理。

## 汇总
收集四个子代理返回的单层 JSON 数组（每数组含若干校验结果对象）后，将其归纳重组为 FinalValidationReport：
- invoice_id：发票代码_发票号码（若缺失则用 "UNKNOWN"）
- validation_time：当前时间（YYYY-MM-DD HH:MM:SS）
- agent_reports：四个子代理的报告列表，每个包含：
    - agent_name（与子代理对应："完整性校验Agent" / "格式校验Agent" / "计算校验Agent" / "业务规则校验Agent"）
    - execution_time（填 0.0）
    - results（该子代理返回的结果数组原样归入）
- overall_status：存在任意 error → "FAILED"；无 error 但有 warning → "WARNING"；否则 "PASSED"
- summary：一句话中文总结审核结论

只能使用上述 4 个专项子代理完成任务，并严格按阶段顺序执行。
"""


# ==================== Deep Agent 创建 ====================

def create_invoice_agent(
    model: str = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    debug: bool = False
):
    """
    创建发票审核 Deep Agent（主 Agent 三阶段编排 + 4 个维度 Sub-Agent）

    Args:
        model: 模型名称（如 "Qwen/Qwen3.6-27B"）
        api_key: API 密钥（可选，默认从环境变量读取）
        base_url: API 基础 URL（可选，默认从环境变量读取）
        debug: 是否启用调试模式

    Returns:
        CompiledStateGraph: 配置好的 Deep Agent
    """
    # 读取配置（发票服务现改用阿里云 DashScope，与合同审核一致，避免硅基流动开源模型编排超时）
    # 同步单 skill 包装目录，确保各 Sub-Agent 的 skills source 指向只含本维度的目录
    _sync_skill_wrappers()

    if api_key is None:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if base_url is None:
        base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if model is None:
        model = "qwen3.7-max-2026-05-20"

    # 直接创建 ChatOpenAI 实例，使用标准 chat.completions API
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=120,        # 单次 LLM HTTP 调用最多 120s，避免 hang
        max_retries=2,      # 失败重试 2 次
        extra_body={"enable_thinking": False},  # 关闭深度思考，避免 thinking 阶段静默超时
    )

    agent = create_deep_agent(
        model=llm,
        tools=[],                       # 主 Agent 只编排，不直接校验
        skills=None,                   # 主 Agent 不需要 skills 元数据；Sub-Agent 各自加载
        backend=BACKEND,               # 关键：让 /skills 映射到磁盘，修复 skills 悬空未生效
        subagents=_build_subagents(llm),
        system_prompt=ORCHESTRATOR_PROMPT,
        response_format=FinalValidationReport,
        debug=debug,
        name="invoice-auditor"
    )

    return agent


# ==================== 结果解析（主路径 + 兜底） ====================

def _extract_first_json(text: str):
    """从文本中提取第一个 JSON 对象或数组（容错：忽略包裹文字/代码块）。

    使用括号配对扫描，避免贪婪正则误取多个 JSON 段。
    """
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # 括号配对扫描，找到第一个完整闭合的 JSON 对象
    obj = _scan_balanced(text, '{', '}')
    if obj is not None:
        try:
            return json.loads(obj)
        except Exception:
            pass
    # 尝试数组
    arr = _scan_balanced(text, '[', ']')
    if arr is not None:
        try:
            return json.loads(arr)
        except Exception:
            pass
    return None


def _scan_balanced(text: str, open_ch: str, close_ch: str) -> Optional[str]:
    """扫描文本中第一个括号配对完整的片段（含字符串字面量感知）。"""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


CATEGORY_MAP = {
    "完整性校验": "完整性校验Agent",
    "格式校验": "格式校验Agent",
    "计算校验": "计算校验Agent",
    "业务规则校验": "业务规则校验Agent",
}


def _rebuild_from_messages(result, invoice_data) -> FinalValidationReport:
    """兜底：从消息流中提取各维度 Sub-Agent 返回的单层 JSON 数组，重组为 FinalValidationReport。"""
    messages = result.get("messages", [])
    by_category: dict[str, list] = {}

    for msg in messages:
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        data = _extract_first_json(content)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("category") in CATEGORY_MAP:
                    by_category.setdefault(item["category"], []).append(item)

    agent_reports = []
    for category, agent_name in CATEGORY_MAP.items():
        results_raw = by_category.get(category, [])
        results = []
        for r in results_raw:
            try:
                results.append(ValidationResult(
                    agent_name=r.get("agent_name", agent_name),
                    level=ValidationLevel(r.get("level", "info")),
                    category=r.get("category", category),
                    message=r.get("message", ""),
                    field=r.get("field"),
                    expected=r.get("expected"),
                    actual=r.get("actual"),
                    suggestion=r.get("suggestion"),
                ))
            except Exception:
                continue
        if not results:
            results.append(ValidationResult(
                agent_name=agent_name,
                level=ValidationLevel.INFO,
                category=category,
                message="未获取到该维度校验结果（子代理无返回）。",
            ))
        agent_reports.append(AgentValidationReport(
            agent_name=agent_name,
            execution_time=0.0,
            results=results,
        ))

    invoice_id = f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}"
    total_error = sum(r.error_count for r in agent_reports)
    total_warning = sum(r.warning_count for r in agent_reports)
    overall = "FAILED" if total_error > 0 else ("WARNING" if total_warning > 0 else "PASSED")
    summary = f"兜底重组：共 {total_error} 个错误、{total_warning} 个警告。"
    return FinalValidationReport(
        invoice_id=invoice_id,
        validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        agent_reports=agent_reports,
        overall_status=overall,
        summary=summary,
    )


def _parse_result(result, invoice_data) -> FinalValidationReport:
    """优先 structured_response，其次最后一条 AI 消息的 JSON，最后从消息流重组。"""
    # 主路径：response_format 结构化输出
    sr = result.get("structured_response")
    if sr:
        if isinstance(sr, FinalValidationReport):
            return sr
        if isinstance(sr, dict):
            try:
                return FinalValidationReport(**sr)
            except Exception as e:
                print(f"[warn] structured_response 解析失败，尝试兜底: {e}")

    # 兜底 1：最后一条 AI 消息中的 FinalValidationReport JSON
    messages = result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip().startswith("{"):
            data = _extract_first_json(content)
            if isinstance(data, dict) and ("agent_reports" in data or "overall_status" in data):
                try:
                    return FinalValidationReport(**data)
                except Exception:
                    pass

    # 兜底 2：从消息流重组各维度数组
    return _rebuild_from_messages(result, invoice_data)


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
    """异步调用 Agent（三阶段编排 + 解析兜底）"""
    import json as _json

    # 如果没有提供 Agent，创建一个新的
    if agent is None:
        agent = create_invoice_agent(model=model)

    # 构建用户消息
    user_message = f"""请审核以下发票数据：

```json
{_json.dumps(invoice_data, ensure_ascii=False, indent=2)}
```

请按编排流程执行完整性、格式、计算和业务规则校验，并输出 FinalValidationReport 格式的结果。
"""

    # 调用 Agent
    try:
        # 240s 硬超时（发票有 4 个 Sub-Agent + 主 Agent 编排，比合同慢，留够余量）
        result = await asyncio.wait_for(
            agent.ainvoke({
                "messages": [{"role": "user", "content": user_message}]
            }),
            timeout=240
        )
    except asyncio.TimeoutError:
        print(f"发票 Agent 审核超时（>240s）")
        return FinalValidationReport(
            invoice_id=f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}",
            validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            overall_status="ERROR",
            summary="Agent 审核超时（240s），请重试或人工复核。"
        )
    except Exception as e:
        print(f"Agent 调用失败: {e}")
        return FinalValidationReport(
            invoice_id=f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}",
            validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            overall_status="ERROR",
            summary=f"Agent 调用失败: {str(e)[:200]}"
        )

    # 解析结果：主路径 response_format + 双级兜底
    report = _parse_result(result, invoice_data)

    # 统一覆盖为真实当前时间（LLM 生成的 validation_time 不可靠）
    report.validation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return report


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

    print("=== 测试 Deep Agent 发票审核（三阶段 Sub-Agent 编排）===")
    print(f"Backend root: {BACKEND_ROOT}")

    # 创建 Agent
    print("\n创建 Agent...")
    agent = create_invoice_agent(debug=True)
    print("Agent 创建成功!")

    # 执行校验
    print("\n执行校验...")
    report = validate_invoice_with_agent_sync(test_invoice, agent)
    print(f"\n校验结果:")
    print(f"  发票ID: {report.invoice_id}")
    print(f"  状态: {report.overall_status}")
    print(f"  总结: {report.summary}")
    for ar in report.agent_reports:
        print(f"  - {ar.agent_name}: errors={ar.error_count}, warnings={ar.warning_count}, info={ar.info_count}")
