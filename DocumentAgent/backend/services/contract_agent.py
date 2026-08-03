"""
基于 Deep Agents 的合同审核系统。

体现 Harness Engineering v2 的核心架构：
  - 确定性下沉：金额/日期/条款引用/甲乙方名称由代码管线判定（步骤 2-3）
  - 类型识别 + 动态 Skill：轻量 LLM 识别合同类型，按需加载专属规则（步骤 4-5）
  - 单 Agent + VFS + Planner：不引入 Sub-Agent，合同写入 VFS，Planner 自规划审核顺序
  - 半结构化规划：system_prompt 给必审维度清单作为约束，具体顺序由 Agent 自主决定

对外接口：audit_contract_with_agent_sync(text) -> ContractAuditReport
"""

import os
import sys
import re
import json
import uuid
import asyncio
import time
from typing import Optional
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# 直接基于 create_agent 构建，避免 create_deep_agent 强制注入的 SubAgentMiddleware（task 子代理工具）
# 设计意图：单 Agent + VFS + Planner，不引入 Sub-Agent；task 子代理会拉起同样带 task 的子代理，
# 在手动 new_event_loop() 的线程中容易进入不收敛的异步路径并永久挂起（即前端无限转圈）。
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import create_summarization_middleware
from langchain_openai import ChatOpenAI

from models.validation import (
    ContractAuditReport,
    ContractIssue,
    DeterministicFinding,
    IssueSeverity,
    BasisType,
    ContractType,
)
from tools.contract_tools import (
    extract_amounts,
    extract_dates,
    extract_clauses,
    extract_parties,
    verify_amount_pair,
    verify_date_parseable,
    verify_clause_reference,
    verify_party_consistency,
)
from services.contract_deterministic import run_deterministic_audit, summarize_findings
from services.contract_classifier import classify_contract, get_skill_filename


# ==================== 路径与 Backend 配置 ====================

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# FilesystemBackend：POSIX 虚拟路径 /contracts/xxx.md -> BACKEND_ROOT/contracts/xxx.md
BACKEND = FilesystemBackend(root_dir=BACKEND_ROOT, virtual_mode=True)

# 合同文件保存目录（映射到 VFS /contracts/）
CONTRACTS_DIR = os.path.join(BACKEND_ROOT, "contracts")
os.makedirs(CONTRACTS_DIR, exist_ok=True)

# Skills 源
SKILLS_SOURCE = ["/skills/contract_audit"]


# ==================== Agent 工具集 ====================

# 确定性工具：提取层 + 校验层（供 Agent 按需调用）
CONTRACT_TOOLS = [
    extract_amounts,
    extract_dates,
    extract_clauses,
    extract_parties,
    verify_amount_pair,
    verify_date_parseable,
    verify_clause_reference,
    verify_party_consistency,
]


# ==================== System Prompt（半结构化规划，不写死流程） ====================

CONTRACT_AUDIT_SYSTEM_PROMPT = """你是资深合同法律审核专家，具有 10 年以上合同审查经验。

## 工作方式

你是一个自主规划的审核 Agent。每次审核任务你会收到：
1. 合同文本的 VFS 路径（用 read_file 读取）
2. 合同类型（据此 read_file 加载专属审核规则）
3. 确定性管线的校验汇总（作为已知事实，不要重复判定）

你拥有任务规划（todo list）能力，请先制定审核计划，再按计划执行。注意：本环境没有子代理 / task 委派工具，请直接调用下方工具自主完成全部审核。

## 必审维度（顺序自定，但不可遗漏）

你必须覆盖以下 5 个通用维度：

1. **法律术语规范性**（rule_id 前缀 `LEGAL.term`）
   - 法律术语准确性："违约金"非"罚款"、"解除合同"非"取消合同"、"定金"非"订金"
   - 避免口语化表述
   - 术语前后一致性

2. **权利义务对等性**（rule_id 前缀 `RIGHTS.duty`）
   - 甲乙方权利义务是否明确、对等
   - "应当"、"必须"、"有权"、"可以"的使用是否对等
   - 避免显失公平条款

3. **条款逻辑矛盾**（rule_id 前缀 `LOGIC.contradiction`）
   - 不同条款间是否存在矛盾
   - 排他性条款是否冲突
   - 违约金与赔偿损失关系是否明确

4. **法律合规性**（rule_id 前缀 `COMPLIANCE.law`）
   - 是否违反法律强制性规定
   - 是否存在无效条款（免责条款不得免除己方责任）
   - 违约金是否过高（超过实际损失 30%）
   - 必备条款是否完整

5. **歧义性表述**（rule_id 前缀 `CLARITY.ambiguity`）
   - 多义词导致歧义
   - 连接词"和/或/及/与"准确性
   - 标点影响理解

此外，根据合同类型，read_file 加载专属规则，覆盖类型专属维度。

## 确定性边界（不要重复判定）

以下校验已由代码管线完成，你**不要重复判定**，但可在语义层面补充：
- 金额大小写一致性（DETERM.amount_case）
- 日期合法性（DETERM.date_valid）
- 条款引用准确性（DETERM.clause_ref）
- 甲乙方名称一致性（DETERM.party_consistency）

如果确定性管线发现了 FAIL 项，你可以在 issues 中引用它（basis_type=hybrid，deterministic_ref 填 finding_id），补充语义解释和法律风险说明。

## 工具使用纪律（重要：避免过度调用）

**核心原则：已读取的内容在对话历史中，无需重复读取。收集到足够信息后立即输出，不要再调用工具。**

工具调用预算：**总共不超过 12 次**。典型分配：
- `read_file` ×3：合同文本、SKILL.md、类型专属规则（各读一次，不重复）
- `grep` ×3-5：按维度搜索关键词（每个维度最多 1 次，合并多个关键词到一次 grep）
- `verify_*` ×2-4：对存疑元素做确定性校验（可选，确定性管线已跑过）

**禁止行为**：
- ❌ 重复 read_file 同一文件（内容已在对话历史中，回看即可）
- ❌ 每个维度都 grep（只对需要定位的关键词 grep，如"违约金"、"罚款"、"定金"）
- ❌ 调用 extract_* 后又调用 verify_*（确定性管线已在 user message 给出结果）
- ❌ 收集完信息后继续搜索（应立即转入输出阶段）

**收敛时机**：当你已读完合同 + 规则，并完成必要的 grep/verify 后，**立即输出 ContractAuditReport**，不要再调用任何工具。issues 基于你已掌握的信息生成，不需要穷尽搜索。

- `read_file`: 读取合同文本、SKILL.md、类型专属规则、参考文档（每个文件只读一次）
- `grep`: 在合同中搜索特定关键词（如"违约金|罚款|定金|订金"合并一次搜索）
- `extract_amounts/dates/clauses/parties`: 提取结构化数据（可选，确定性管线已有结果时不用）
- `verify_amount_pair/date_parseable/clause_reference/party_consistency`: 对存疑元素校验（可选）

## Skill 加载策略

1. 先 `read_file("/skills/contract_audit/SKILL.md")` 获取通用规则
2. 根据合同类型，按需加载专属规则（user message 会告诉你加载哪个文件）
3. 如需查阅法律术语表或高风险条款清单，按需加载 references/ 下的文件

## 输出要求

最终输出一个 JSON 对象，包含以下字段：
{
  "contract_id": "合同标识（从 user message 获取）",
  "contract_type": "labor|sales|lease|loan|general",
  "validation_time": "审核时间（留空，由代码填充）",
  "deterministic_findings": [],  // 留空，由代码填充
  "issues": [
    {
      "rule_category": "规则类别",
      "issue_type": "问题类型",
      "description": "问题详细描述",
      "original": "原文中有问题的片段（逐字复制，不要修正）；缺失类问题填'无'",
      "suggestion": "修改建议",
      "severity": "high|medium|low",
      "legal_risk": "法律风险说明（high 必填）",
      "evidence_location": "原文定位，如'第三条第二款'",
      "rule_id": "规则编号，如 LEGAL.term.1",
      "basis_type": "llm_judgment|deterministic|hybrid",
      "deterministic_ref": null,
      "verified": false,
      "verification_note": ""
    }
  ],
  "overall_risk_level": "high|medium|low|none",
  "summary": "审核总结"
}

## 严重程度定义
- **high**: 必须修正 - 可能导致合同无效或重大损失（必须填 legal_risk）
- **medium**: 建议修正 - 可能引发争议
- **low**: 可优化 - 规范性问题

## 整体风险等级
- **high**: 存在 high 级问题
- **medium**: 存在 medium 级问题但无 high
- **low**: 仅有 low 级问题
- **none**: 无问题
"""


# ==================== Agent 创建 ====================

def _create_llm(
    model: str = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> ChatOpenAI:
    """创建合同审核用 LLM（Agent 模式与单次调用模式共用）。

    qwen3.7-max 是带深度思考（thinking）的推理模型，thinking 阶段常 >120s 无 chunk，
    会击穿 stream_chunk_timeout 并被记为「审核未完成」。这里通过
    extra_body={"enable_thinking": False} 显式关闭深度思考，让模型直接输出结果，
    既大幅缩短首 token 延迟、避免静默超时，也契合「合同审核要快且确定」的场景。
    若该接入点不支持该参数会被忽略，不影响其它逻辑。
    """
    # 读取配置（合同服务使用阿里云 DashScope）
    if api_key is None:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if base_url is None:
        base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if model is None:
        model = "qwen3.7-max-2026-05-20"
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        # 方案 A：放宽超时上限以容纳长合同
        # 单次 HTTP 调用总超时从 180s 提到 600s，流式分块超时从 90s 提到 300s，
        # 避免长合同（300+ 行）在 thinking 关闭后首 token 仍偏慢时被一刀切超时中断。
        timeout=600,                # 单次 HTTP 调用超时（含等待首 token 的总时长）
        max_retries=3,              # 失败重试 3 次
        stream_chunk_timeout=300,   # 流式分块超时（相邻两个 chunk 的最大间隔）
        extra_body={"enable_thinking": False},  # 关闭深度思考，避免 thinking 阶段静默超时
    )


def create_contract_agent(
    model: str = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    debug: bool = False
):
    """创建合同审核 Deep Agent（单 Agent + VFS + Planner）。

    Args:
        model: 模型名称
        api_key: API 密钥
        base_url: API 基础 URL
        debug: 是否启用调试模式

    Returns:
        CompiledStateGraph: 配置好的 Deep Agent
    """
    llm = _create_llm(model, api_key, base_url)

    # 注意：不挂载 SubAgentMiddleware（即不使用 create_deep_agent），
    # 因此本 agent 没有 task / 子代理工具。这符合"单 Agent + VFS + Planner"设计，
    # 也避免了子代理在手动事件循环中递归拉起、永久挂起导致前端无限转圈的问题。
    middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=BACKEND),
        SkillsMiddleware(backend=BACKEND, sources=SKILLS_SOURCE),
        create_summarization_middleware(llm, BACKEND),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
    ]

    agent = create_agent(
        llm,
        system_prompt=CONTRACT_AUDIT_SYSTEM_PROMPT,
        tools=CONTRACT_TOOLS,
        middleware=middleware,
        response_format=ContractAuditReport,
        debug=debug,
        name="contract-auditor",
    ).with_config(
        {
            "recursion_limit": 1000,
            "metadata": {"ls_integration": "contract-auditor"},
        }
    )

    return agent


# ==================== VFS 合同保存 ====================

def _save_contract_to_vfs(text: str) -> tuple[str, str]:
    """把合同文本保存到 VFS 映射目录。

    Args:
        text: 合同文本内容

    Returns:
        tuple[str, str]: (contract_id, vfs_path)
    """
    contract_id = str(uuid.uuid4())[:8]
    disk_path = os.path.join(CONTRACTS_DIR, f"{contract_id}.md")
    vfs_path = f"/contracts/{contract_id}.md"

    with open(disk_path, "w", encoding="utf-8") as f:
        f.write(text)

    return contract_id, vfs_path


def _cleanup_contract_from_vfs(contract_id: str):
    """审核完成后清理 VFS 中的合同文件。"""
    try:
        disk_path = os.path.join(CONTRACTS_DIR, f"{contract_id}.md")
        if os.path.exists(disk_path):
            os.remove(disk_path)
    except Exception:
        pass


def _read_skill_file(filename: str) -> str:
    """从磁盘读取 skills/contract_audit/ 下的文件内容。

    用于在构建 user message 时预加载规则，省掉 Agent 的 read_file 调用。
    """
    if not filename:
        return ""
    skill_path = os.path.join(BACKEND_ROOT, "skills", "contract_audit", filename)
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"  [warn] 读取 Skill 文件失败 {filename}: {e}")
        return ""


# ==================== User Message 构建 ====================

def _build_user_message(
    contract_id: str,
    vfs_path: str,
    contract_text: str,
    contract_type: ContractType,
    type_confidence: float,
    type_reason: str,
    deterministic_summary: dict,
    skill_content: str,
    type_rule_content: str
) -> str:
    """构建 user message，直接注入合同全文 + 规则，省掉 Agent 的 read_file 调用。"""

    # 确定性结果汇总
    det_total = deterministic_summary.get("total", 0)
    det_passed = deterministic_summary.get("passed", 0)
    det_failed = deterministic_summary.get("failed", 0)
    failed_details = deterministic_summary.get("failed_details", [])

    failed_text = "无" if not failed_details else "\n".join(
        f"  - {d['finding_id']} ({d['category']}): {d['detail']} @ {d['location']}"
        for d in failed_details
    )

    return f"""请审核以下合同：

## 合同信息
- 合同 ID: {contract_id}
- 合同类型: {contract_type.value}（置信度: {type_confidence:.0%}，原因: {type_reason}）
- 合同 VFS 路径: {vfs_path}（仅供 grep 搜索用，合同全文已在下方，**无需 read_file**）

## 确定性管线校验结果（已知事实，不要重复判定）
- 确定性校验总数: {det_total}（通过 {det_passed}，失败 {det_failed}）
- 失败项明细:
{failed_text}

## 审核步骤（精简版，目标工具调用 ≤5 次）
1. 阅读下方"合同全文"和"审核规则"（**已直接提供，不要 read_file**）
2. 如需定位特定关键词，用 grep 搜索 VFS 中的合同（可选，最多 2 次）
3. 按必审维度（法律术语/权利义务/逻辑矛盾/合规性/歧义）逐一审核，每发现一个问题输出一个 issue
4. 汇总为 ContractAuditReport 格式输出（**收集完信息后立即输出，不要继续调用工具**）

## 合同全文
---
{contract_text}
---

## 审核规则（通用 SKILL）
{skill_content}

## 审核规则（{contract_type.value} 类型专属）
{type_rule_content if type_rule_content else "本合同为通用类型，无专属规则。"}

## 注意事项
- 每个问题的 original 字段必须精确引用原文（用于验证回路校验）
- evidence_location 必须填写（如"第三条第二款"、"第X行"）
- severity=high 时必须填写 legal_risk
- 不要重复确定性管线已发现的问题（除非补充语义解释，此时 basis_type=hybrid，deterministic_ref 填 finding_id）
- contract_id 填 "{contract_id}"
- contract_type 填 "{contract_type.value}"
- validation_time 和 deterministic_findings 留空，由代码填充
"""


# ==================== 结果解析 ====================

def _extract_first_json(text: str):
    """从文本中提取第一个 JSON 对象或数组。

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


def _parse_result(
    result,
    contract_id: str,
    contract_type: ContractType,
    deterministic_findings: list[DeterministicFinding]
) -> ContractAuditReport:
    """解析 Agent 结果，用确定性 findings 覆盖对应字段。"""

    issues: list[ContractIssue] = []

    # 主路径：structured_response
    sr = result.get("structured_response")
    if sr:
        if isinstance(sr, ContractAuditReport):
            issues = sr.issues
        elif isinstance(sr, dict):
            try:
                report = ContractAuditReport(**sr)
                issues = report.issues
            except Exception as e:
                print(f"[warn] structured_response 解析失败，尝试兜底: {e}")

    # 兜底：从最后一条 AI 消息中解析
    if not issues:
        messages = result.get("messages", [])
        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                data = _extract_first_json(content)
                if isinstance(data, dict) and "issues" in data:
                    try:
                        for issue_data in data.get("issues", []):
                            issues.append(_build_issue(issue_data))
                        break
                    except Exception:
                        continue

    # 用代码填充确定性字段（不信任 LLM 生成的）
    report = ContractAuditReport(
        contract_id=contract_id,
        contract_type=contract_type,
        validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        deterministic_findings=deterministic_findings,
        issues=issues,
        overall_risk_level=_calc_risk_level(issues),
        summary=_build_summary(issues, deterministic_findings),
    )

    return report


def _build_issue(data: dict) -> ContractIssue:
    """从 dict 构建 ContractIssue，容错处理。"""
    severity_map = {
        "high": IssueSeverity.HIGH,
        "medium": IssueSeverity.MEDIUM,
        "low": IssueSeverity.LOW,
    }
    basis_map = {
        "llm_judgment": BasisType.LLM_JUDGMENT,
        "deterministic": BasisType.DETERMINISTIC,
        "hybrid": BasisType.HYBRID,
    }

    return ContractIssue(
        rule_category=data.get("rule_category", ""),
        issue_type=data.get("issue_type", ""),
        issue_category=data.get("issue_category", "other"),
        description=data.get("description", ""),
        original=data.get("original", ""),
        suggestion=data.get("suggestion", ""),
        severity=severity_map.get(data.get("severity", "medium"), IssueSeverity.MEDIUM),
        legal_risk=data.get("legal_risk", ""),
        evidence_location=data.get("evidence_location", ""),
        rule_id=data.get("rule_id", ""),
        basis_type=basis_map.get(data.get("basis_type", "llm_judgment"), BasisType.LLM_JUDGMENT),
        deterministic_ref=data.get("deterministic_ref"),
        verified=False,
        verification_note="",
    )


def _calc_risk_level(issues: list[ContractIssue]) -> str:
    """根据 issues 计算整体风险等级。"""
    if any(i.severity == IssueSeverity.HIGH for i in issues):
        return "high"
    if any(i.severity == IssueSeverity.MEDIUM for i in issues):
        return "medium"
    if any(i.severity == IssueSeverity.LOW for i in issues):
        return "low"
    return "none"


def _build_summary(issues: list[ContractIssue], findings: list[DeterministicFinding]) -> str:
    """构建审核总结。"""
    high = len([i for i in issues if i.severity == IssueSeverity.HIGH])
    medium = len([i for i in issues if i.severity == IssueSeverity.MEDIUM])
    low = len([i for i in issues if i.severity == IssueSeverity.LOW])

    # 确定性校验失败：按类别聚合，避免把"逐条展开"的条数伪装成"问题数量"
    # 同时把"留空待填"类（金额/日期完整性）与实质性校验失败分开表述，避免误导
    det_failed = [f for f in findings if not f.passed]
    by_category: dict[str, int] = {}
    for f in det_failed:
        by_category[f.rule_category] = by_category.get(f.rule_category, 0) + 1
    det_total = len(findings)
    det_fail = len(det_failed)
    # 占位符类的 rule_category 为"金额完整性"/"日期完整性"（见 contract_deterministic.py）
    placeholder_cats = {"金额完整性", "日期完整性"}
    placeholder_fail = sum(c for cat, c in by_category.items() if cat in placeholder_cats)
    substance_fail = det_fail - placeholder_fail

    parts = []
    if high:
        parts.append(f"{high} 个高风险问题")
    if medium:
        parts.append(f"{medium} 个中风险问题")
    if low:
        parts.append(f"{low} 个低风险问题")

    # 确定性校验：仅当存在失败项时，按"类别数 + 条数 + 待补项"结构化表述
    if det_fail:
        cat_desc = "、".join(f"{cat}{c}项" for cat, c in by_category.items())
        summary = (
            f"确定性校验 {det_total} 项，失败 {det_fail} 项"
            f"（涉及 {len(by_category)} 类：{cat_desc}）"
        )
        if placeholder_fail:
            summary += f"，其中待补项（留空未填）{placeholder_fail} 项"
        # 纯模板未填：所有确定性失败均来自留空占位符（金额/日期完整性），
        # 弱化提示，避免把"未填写金额的草稿"误判为实质性条款错误
        if placeholder_fail == det_fail:
            summary += "。本报告基于未填写金额的草稿合同，上述失败项均为留空待补，并非实质性条款错误"
        parts.append(summary)

    if not parts:
        return "审核通过，未发现问题。"

    return "审核完成，发现：" + "，".join(parts) + "。"


# ==================== 双向验证回路（查幻觉 + 查遗漏） ====================

def _longest_shared_fragment(a: str, b: str) -> int:
    """返回 a 与 b 的最长共有连续子串长度（用于中文引用的近似匹配）。

    仅在较短串 a 上滑动窗口，找到第一个落在 b 中的最长窗口即返回（早期退出）。
    最坏复杂度 O(len(a)^2 * len(b))，但合同引用通常仅十几字，开销可忽略。
    """
    if not a or not b:
        return 0
    for w in range(min(len(a), len(b)), 0, -1):
        for i in range(len(a) - w + 1):
            if a[i:i + w] in b:
                return w
    return 0


def _split_original_fragments(original: str) -> list[str]:
    """将 LLM 引用的 original 拆分为有信息量的片段。

    背景：LLM 引用表格/跨行内容时，常把多个表格单元格、多行文本拼合成一段
    （如'二、乙方薪资结算至 年月日；计__元\\n\\n二、_方支付_方经济补偿金__元；'），
    这些字在原文中都存在，但并非连续子串，导致整段包含匹配失败而误判为幻觉。
    因此这里按标点/换行拆分，并剔除占位符、纯数字、无中文片段，保留有语义的片段，
    只要这些片段各自都能在原文中找到，就认为引用已 grounded。

    Args:
        original: LLM 输出的 original 字段

    Returns:
        list[str]: 拆分后的语义片段（已去空白/占位符）
    """
    if not original:
        return []

    # 去除占位符（__、_方、_x 等），避免把占位符当语义内容
    cleaned = re.sub(r'_{1,2}[^_\n，,。；;、：:\s]{0,3}', '', original)
    # 按标点/换行/空白拆分为片段
    parts = re.split(r'[\n，,。；;、：:\s]+', cleaned)

    fragments = []
    for part in parts:
        p = part.strip()
        # 过滤：空串、过短（<2字）、无中文（纯数字/符号/占位残留）
        if len(p) < 2:
            continue
        if not re.search(r'[\u4e00-\u9fa5]', p):
            continue
        fragments.append(p)
    return fragments


def _is_grounded_by_fragments(original: str, original_text: str) -> tuple[bool, float]:
    """判断 original 是否由大量可在原文中找到的片段组成。

    用于处理 LLM 引用表格/跨行内容时整段不连续、但关键内容都在原文中的场景，
    作为「整段包含匹配」失败后的降级验证，避免把真实存在的问题误判为幻觉。

    Args:
        original: LLM 引用的 original 字段
        original_text: 合同原文

    Returns:
        tuple[bool, float]: (是否 grounded，长片段命中率 0-1)
    """
    fragments = _split_original_fragments(original)
    if not fragments:
        return False, 0.0

    # 只统计有语义的长片段（≥4 字），避免 2-3 字泛词（"乙方"、"金额"等）虚高命中率
    long_fragments = [f for f in fragments if len(f) >= 4]
    if not long_fragments:
        return False, 0.0

    hit = 0
    for frag in long_fragments:
        if frag in original_text:
            hit += 1

    rate = hit / len(long_fragments)
    # 只要过半长片段都能在原文中找到，即视为引用已 grounded（容忍跨行/表格重组）
    return rate >= 0.5, rate


def verify_issues(
    issues: list[ContractIssue],
    original_text: str,
    deterministic_findings: list[DeterministicFinding]
) -> tuple[list[ContractIssue], list[DeterministicFinding]]:
    """双向验证回路：查幻觉 + 查遗漏。

    体现 Harness Engineering 信条 3「验证内建」：
    - 查幻觉：每个 issue 的 original 字段是否在原文中（字符串包含匹配 + 空格容错）
    - 查遗漏：确定性 FAIL 项是否被 LLM 的 issues 覆盖（明确引用 or 关键词匹配）

    Args:
        issues: LLM 输出的 issue 列表
        original_text: 合同原文
        deterministic_findings: 确定性管线结果

    Returns:
        tuple: (更新后的 issues，更新后的 deterministic_findings)
    """
    # 已知确定性 finding id 集合，用于识别"引用确定性结果"的 issue
    known_finding_ids = {f.finding_id for f in deterministic_findings}

    # 1. 查幻觉：original 字段是否在原文中
    for issue in issues:
        # 缺失类问题分两种：
        #  A. issue_category=clause_missing：合同缺少必备条款，original="无" 是合法的
        #  B. issue_category=clause_invalid/term_error：声称合同有某条款但 original="无" → 逻辑矛盾，幻觉
        _omission_markers = ("无", "缺失", "未约定", "未提及", "N/A", "不适用")
        if issue.original and issue.original.strip() in _omission_markers:
            # 只有 issue_category=clause_missing 才允许 original 为空
            if issue.issue_category == "clause_missing":
                issue.verified = True
                issue.verification_note = "缺失类问题，无需原文引用"
            else:
                issue.verified = False
                issue.verification_note = f"[幻觉风险] 声称合同存在条款但无法提供原文（issue_category={issue.issue_category}），可能为模型虚构"
            continue

        # 引用确定性管线结果的 issue（basis_type=deterministic/hybrid 且 deterministic_ref 命中）：
        # 其 original 往往是确定性管线的"摘要文本"（如'甲方名称不一致：...'），并非逐字原文，
        # 按"已知事实"视为已验证，避免把合法的确定性 FAIL 误判为幻觉 / 未验证
        if (issue.deterministic_ref in known_finding_ids
                and issue.basis_type in (BasisType.DETERMINISTIC, BasisType.HYBRID)):
            issue.verified = True
            issue.verification_note = "引用确定性校验结果（已知事实）"
            continue

        if not issue.original:
            issue.verified = False
            issue.verification_note = "original 字段为空，无法验证"
            continue

        # 精确匹配
        if issue.original in original_text:
            issue.verified = True
            issue.verification_note = ""
            continue

        # 容错：去除空白后匹配（处理换行/多空格差异）
        normalized_original = re.sub(r'\s+', '', issue.original)
        normalized_text = re.sub(r'\s+', '', original_text)
        if normalized_original in normalized_text:
            issue.verified = True
            issue.verification_note = ""
            continue

        # 模糊匹配：LLM 可能对原文做了小幅改写（如把"如甲方未按时支付工资，应向乙方支付"
        # 改写为"如甲方违约，需支付"），但关键术语（如"罚款5000元"）仍逐字出现在原文中。
        # 若 original 与原文存在足够长的共有片段（≥ max(5, 长度/2)），视为引用已 grounded，
        # 避免把真实存在的术语类问题误判为幻觉 / 未验证。
        shared = _longest_shared_fragment(normalized_original, normalized_text)
        min_shared = max(5, len(normalized_original) // 2)
        if shared >= min_shared:
            issue.verified = True
            issue.verification_note = f"原文近似匹配（共有片段 {shared} 字），已容忍小幅改写"
        else:
            # 语义定位匹配：LLM 引用表格/跨行内容时整段可能不连续，但关键片段都能在原文中找到，
            # 此时不应误判为幻觉，也不应降级严重程度。
            grounded, frag_rate = _is_grounded_by_fragments(issue.original, original_text)
            if grounded:
                issue.verified = True
                issue.verification_note = (
                    f"关键内容已在原文中逐段定位（长片段命中率 {frag_rate:.0%}），"
                    f"已容忍表格/跨行导致的文本重组"
                )
            else:
                issue.verified = False
                # LLM 纯判定类 issue 在原文中找不到引用 → 很可能是模型幻觉
                if issue.basis_type == BasisType.LLM_JUDGMENT:
                    issue.verification_note = (
                        f"[幻觉风险] 原文未找到对应内容（长片段命中率 {frag_rate:.0%}），"
                        f"可能为模型虚构 | original: {issue.original[:50]}..."
                    )
                    # 幻觉 issue 的严重程度不可信，降级为 low
                    issue.severity = IssueSeverity.LOW
                else:
                    issue.verification_note = f"original 在原文中未找到: {issue.original[:50]}..."

    # 2. 查遗漏：确定性 FAIL 项是否被 LLM 覆盖
    failed_findings = [f for f in deterministic_findings if not f.passed]

    for finding in failed_findings:
        covered = False

        # 方式 1：明确引用（deterministic_ref 指向 finding_id）
        for issue in issues:
            if issue.deterministic_ref == finding.finding_id:
                covered = True
                break

        # 方式 2：关键词匹配（issue 内容与 finding 相关）
        if not covered:
            keywords = _extract_keywords_from_finding(finding)
            if keywords:
                for issue in issues:
                    issue_text = (
                        (issue.description or "") + " " +
                        (issue.original or "") + " " +
                        (issue.rule_category or "")
                    ).lower()
                    if any(kw.lower() in issue_text for kw in keywords):
                        covered = True
                        break

        finding.covered_by_llm = covered

    return issues, deterministic_findings


def _extract_keywords_from_finding(finding: DeterministicFinding) -> list[str]:
    """从 finding 中提取关键词，用于判断 LLM 是否覆盖了该 FAIL 项。"""
    keywords = []

    if finding.rule_id == "DETERM.amount_case":
        keywords.extend(["金额", "大小写", "数额"])
        if finding.field:
            nums = re.findall(r'[\d,.]+', finding.field)
            keywords.extend(nums)

    elif finding.rule_id == "DETERM.amount_empty":
        # 金额留空待填的占位符（如"计_元"）
        keywords.extend(["金额", "未填写", "留空", "待填", "空白", "占位"])
        if finding.field:
            # field 形如 "_元"、"计 元"，取"元"前的占位特征词
            keywords.append(finding.field.replace('_', '').replace(' ', ''))

    elif finding.rule_id == "DETERM.date_valid":
        keywords.extend(["日期", "时间", "生效", "到期"])
        if finding.field:
            keywords.append(finding.field)

    elif finding.rule_id == "DETERM.date_empty":
        # 日期留空待填的占位符（如"年 月 日"）
        keywords.extend(["日期", "未填写", "留空", "待填", "空白", "占位", "年月日"])

    elif finding.rule_id == "DETERM.clause_ref":
        keywords.extend(["条款", "引用", "参照", "详见"])
        if finding.field:
            keywords.append(finding.field)

    elif finding.rule_id == "DETERM.party_consistency":
        keywords.extend(["甲方", "乙方", "名称", "主体"])

    return keywords


# ==================== 单次 LLM 深度分析（方案 D：替代 Agent 循环） ====================

SINGLE_CALL_SYSTEM_PROMPT = """你是资深合同法律审核专家，具有 10 年以上合同审查经验。

## 核心原则：有依据就报，没依据不编

**每个 issue 必须有原文依据。** 在报告一个问题前，先确保能在合同中找到对应的条款和具体字句作为证据。
- ✅ 原文有"罚款5000元" → 报告"罚款应改为违约金"
- ❌ 原文没有任何"罚款"字样 → 禁止凭空编造"罚款应改为违约金"
不要根据"这类合同常见问题"凭先验知识脑补原文中不存在的条款。同时，凡是有原文依据的问题都要报出来，不要偷懒漏审。

你将一次性收到：合同全文、审核规则（通用 + 类型专属）、确定性管线校验结果。
请**逐条对照审核规则与合同原文**，只报告原文中真实存在的问题。不需要调用任何工具，所有信息已在上下文中。

## 确定性边界（不要重复判定）

以下校验已由代码完成，**不要重复判定**，但可在语义层面补充：
- 金额大小写一致性（DETERM.amount_case）
- 日期合法性（DETERM.date_valid）
- 条款引用准确性（DETERM.clause_ref）
- 甲乙方名称一致性（DETERM.party_consistency）

如确定性管线有 FAIL 项，可在 issues 中引用（basis_type=hybrid，deterministic_ref 填 finding_id），补充语义解释和法律风险。

## 强制自检（输出前逐项核对，缺一不可）

在输出 issues 之前，请逐项完成以下自检并**在思考后回答**：

**【自检 0】必备条款适用性判断（clause_missing 专用，最重要）**
审核规则中列出的"必备条款"列表并非对所有文档都适用。在报告 clause_missing 之前，**必须**先判断：
1. 这份文档的**性质**是什么？（是签署劳动合同，还是解除/变更/终止/续签协议？是采购合同还是服务合同？是主合同还是补充协议？）
2. 规则中列出的"必备条款"是否是**这类文档**真的需要包含的？
   - ❌ 错误示例：解除劳动合同协议书被要求包含"试用期条款"——解除协议不需要约定试用期
   - ❌ 错误示例：变更劳动合同协议书被要求包含"竞业限制条款"——变更协议不需要重新约定竞业限制
   - ❌ 错误示例：补充协议被要求包含"工资支付周期"——补充协议不需要重复主合同的全部条款
   - ✅ 正确做法：根据文档的具体目的，只报告**这类文档真正应该包含但缺失**的必备条款
3. 如果不确定某条款是否真的"必备"，选择**不报告**，不要冒险编造缺失问题。

**【自检 1】原文搜索确认**
对每一个准备报告的 issue，在合同原文中搜索 original 字段的关键词：
- 如果搜索不到 → **删除此 issue，不要报告**
- 如果搜索到了 → 确认 original 字段是原文逐字片段，没有改写，继续

**【自检 2】规则覆盖检查**
逐维度确认：法律术语规范/权利义务对等/条款逻辑矛盾/法律合规性/歧义性表述
每个维度如果合同中没有对应问题 → 该维度不报 issue，不要为了凑数编造

**【自检 3】original 是逐字复制，不是改写**
- ❌ 错误示例：原文"应向乙方支付罚款"，original 写成"需支付罚款"（少了"应向乙方"）
- ✅ 正确示例：原文"应向乙方支付罚款5000元"，original 就是"应向乙方支付罚款5000元"
- 如果合同中没有某句话，就不能编一句类似的作为 original

**【自检 4】严重程度合理**
- high 的 issue 确认 legal_risk 已填写

如自检发现任何一个 issue 不满足上述条件，先删除或修正，再输出最终结果。

## 输出格式

输出一个 JSON 对象。**每个 issue 必须填写 issue_category 字段**，用于区分问题性质：
- `clause_invalid`: 合同中有某条款，但该条款无效/有问题 → **original 必须引用该条款原文，不能填"无"**
- `clause_missing`: 合同缺少必备条款 → original 填"无"是合法的，evidence_location 说明应该在哪个位置
- `term_error`: 合同中有术语/表述错误（如"罚款"应为"违约金"） → **original 必须引用原文，不能填"无"**
- `other`: 其他类型问题

{
  "issues": [
    {
      "rule_category": "规则类别",
      "issue_type": "问题类型",
      "issue_category": "clause_invalid|clause_missing|term_error|other",
      "description": "问题详细描述",
      "original": "原文中有问题的片段（逐字复制，不要修正、不要改写）；仅 clause_missing 类可填'无'",
      "suggestion": "修改建议",
      "severity": "high|medium|low",
      "legal_risk": "法律风险说明（high 必填）",
      "evidence_location": "原文定位，如'第三条第二款'",
      "rule_id": "规则编号，如 LEGAL.term.1",
      "basis_type": "llm_judgment|deterministic|hybrid",
      "deterministic_ref": null
    }
  ]
}

## 严重程度定义
- **high**: 必须修正 - 可能导致合同无效或重大损失（必须填 legal_risk）
- **medium**: 建议修正 - 可能引发争议
- **low**: 可优化 - 规范性问题

## 纪律
- 有依据就报：每报告一个 issue 前，确认原文中存在 original 字段所引用的字句；找不到就不报，绝不编造
- 逐字引用：original 必须是原文子串，不能改写、不能概括、不能"意思相近"
- 缺失类问题：合同缺少必备条款时，original 填"无"，description 说明缺少什么
- 逐条对照：审核规则已在下方提供，发现任何有原文依据的问题都要报告，不要遗漏
"""


def _build_filtered_audit_dimensions(selected_rules: list[str]) -> str:
    """根据选中的规则ID列表，构建过滤后的审核维度提示。"""

    # 规则ID到维度描述的映射
    RULE_DESCRIPTIONS = {
        "1": "1.1 错别字与形近字检查（形近字、同音字、笔误、多字、漏字）",
        "2": "1.2 标点符号规范性（句号、逗号、顿号、分号、冒号、括号引号配对）",
        "3": "1.3 语法结构检查（主谓宾搭配、成分完整性、避免歧义性表述）",
        "4": '2.1 法律术语规范性（“违约金”非“罚款”、“解除合同”非“取消合同”）',
        "5": "2.2 权利义务对等性（甲乙方权利义务明确、对等，避免显失公平）",
        "6": "2.3 金额与数字准确性（大写小写一致、重要金额必须大写+小写）",
        "7": '2.4 时间条款明确性（合同期限明确、避免"尽快"、"及时"等模糊词）',
        "8": "3.1 条款前后一致性（同一概念表述一致、数字金额一致、甲乙方名称一致）",
        "9": "3.2 条款间逻辑矛盾（不同条款是否矛盾、违约金与赔偿损失关系明确）",
        "10": "3.3 引用条款准确性（条款编号引用准确、附件编号存在、法律法规引用准确）",
        "11": "4.1 法律合规性（是否违反法律强制性规定、是否存在无效条款）",
        "12": "4.2 敏感词汇检查（避免歧视性语言、避免绝对化承诺）",
        "13": "4.3 必备条款完整性（主体信息、标的物、价款、履行期限、违约责任、争议解决）",
        "14": '5.1 歧义性表述（多义词导致歧义、"和"/"或"/"及"/"与"连接词准确性）',
        "15": "5.2 冗余与重复（不必要的重复、冗余修饰语、过长条款）",
    }

    if not selected_rules:
        # 未选择规则，返回全部维度
        return "\n".join(f"- {desc}" for desc in RULE_DESCRIPTIONS.values())

    # 根据选中的规则ID过滤维度
    filtered_dims = []
    for rule_id in selected_rules:
        if rule_id in RULE_DESCRIPTIONS:
            filtered_dims.append(f"- {RULE_DESCRIPTIONS[rule_id]}")

    return "\n".join(filtered_dims) if filtered_dims else "全部维度（未识别到有效规则ID）"


def _build_single_call_user_message(
    contract_text: str,
    contract_type: ContractType,
    type_confidence: float,
    type_reason: str,
    deterministic_summary: dict,
    skill_content: str,
    type_rule_content: str,
    selected_rules: list[str] = None
) -> str:
    """构建单次调用的 user message：规则在中间，合同全文在末尾（高注意力区）。"""

    det_total = deterministic_summary.get("total", 0)
    det_passed = deterministic_summary.get("passed", 0)
    det_failed = deterministic_summary.get("failed", 0)
    failed_details = deterministic_summary.get("failed_details", [])

    failed_text = "无" if not failed_details else "\n".join(
        f"  - {d['finding_id']} ({d['category']}): {d['detail']} @ {d['location']}"
        for d in failed_details
    )

    # 根据选中的规则构建过滤后的审核维度
    audit_dimensions = _build_filtered_audit_dimensions(selected_rules)

    return f"""## 合同类型
{contract_type.value}（置信度: {type_confidence:.0%}，原因: {type_reason}）

## 确定性管线校验结果（已知事实，不要重复判定）
- 确定性校验总数: {det_total}（通过 {det_passed}，失败 {det_failed}）
- 失败项明细:
{failed_text}

## 审核规则（通用，来自 SKILL.md）
{skill_content}

## 审核规则（{contract_type.value} 类型专属）
{type_rule_content if type_rule_content else "本合同为通用类型，无专属规则。"}

## 本次审核维度（用户自定义选择）
{audit_dimensions}

## 合同全文（请逐条深度分析，对照上方审核规则）
---
{contract_text}
---
"""


async def _audit_with_single_call(
    llm,
    contract_text: str,
    contract_type: ContractType,
    type_confidence: float,
    type_reason: str,
    deterministic_summary: dict,
    skill_content: str,
    type_rule_content: str,
    start_time: float,
    selected_rules: list[str] = None,
    on_token: callable = None,
) -> list[ContractIssue]:
    """单次 LLM 深度分析：合同全文 + 规则 → issues 列表。

    替代 Agent 多轮工具调用，LLM 注意力 100% 集中在条款分析上。
    预期：0 次工具调用，1 次 LLM 调用，~15s 完成。

    方案 B（流式）支持：传入 on_token 回调即可在 LLM 输出每个 chunk 时实时收到，
    用于前端「正在分析…」的逐步渲染；不传则退化为原来的同步等待模式。
    """
    user_message = _build_single_call_user_message(
        contract_text, contract_type, type_confidence, type_reason,
        deterministic_summary, skill_content, type_rule_content, selected_rules
    )

    print(f"    [single-call] 调用 LLM 单次深度分析（stream={'yes' if on_token else 'no'}）...")
    # 方案 A：单次调用总超时从 180s 放宽到 600s，避免长合同被一刀切中断
    try:
        content = ""
        if on_token is not None:
            # 流式模式：边收边累积，并实时回调 token
            async for chunk in llm.astream([
                {"role": "system", "content": SINGLE_CALL_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]):
                delta = getattr(chunk, "content", "") or ""
                if delta:
                    content += delta
                    on_token(delta)
        else:
            response = await asyncio.wait_for(
                llm.ainvoke([
                    {"role": "system", "content": SINGLE_CALL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ]),
                timeout=600,
            )
            content = response.content if hasattr(response, 'content') else str(response)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_time
        print(f"    [single-call] LLM 调用超时（{elapsed:.0f}s）")
        # 超时不是「审核通过」，抛出带原因的信号，由上层标记为 llm_timeout
        raise TimeoutError(
            f"LLM 深度分析超时（{elapsed:.0f}s），本次审核结果不可信，请重试或检查模型配置"
        )
    except Exception as e:
        elapsed = time.monotonic() - start_time
        print(f"    [single-call] LLM 调用失败（{elapsed:.0f}s）: {e}")
        raise RuntimeError(f"LLM 深度分析调用失败: {e}")

    # 解析 LLM 输出
    data = _extract_first_json(content)

    if not data or not isinstance(data, dict):
        print(f"    [single-call] 无法解析 JSON 输出，原始内容前200字符: {content[:200]}")
        return []

    issues_data = data.get("issues", [])
    issues = []
    for issue_data in issues_data:
        try:
            issues.append(_build_issue(issue_data))
        except Exception as e:
            print(f"    [single-call] 解析 issue 失败: {e}")

    elapsed = time.monotonic() - start_time
    print(f"    [single-call] 完成：{len(issues)} 个问题（t={elapsed:.1f}s）")
    return issues


# ==================== 带日志的流式执行 ====================

async def _run_agent_stream(agent, user_message: str, tool_calls: list, start_time: float):
    """通过 astream_events 流式执行 Agent。

    同时完成两件事：
    1. 实时记录 LLM 实际选择的每一个工具（含 task 子代理），用于定位卡顿根因；
    2. 捕获根图（parent_id 为 None）的 on_chain_end 事件输出作为最终状态，
       其结构与 ainvoke 返回值一致（含 structured_response / messages），可直接喂给 _parse_result。
    """
    final_state = None
    # 显式传 config 透传 recursion_limit。.with_config 设置的 recursion_limit=1000
    # 不会被 astream_events 自动继承（LangGraph 默认 25），导致 Agent 调用 ~20 次工具后
    # 触发 "Recursion limit of 25 reached" 异常。这里显式传入以确保生效。
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": user_message}]},
        version="v2",
        config={"recursion_limit": 1000},
    ):
        etype = event.get("event")
        if etype == "on_tool_start":
            name = event.get("name")
            if name:
                tool_calls.append(name)
                elapsed = time.monotonic() - start_time
                print(f"    [tool #{len(tool_calls)}] {name}  (t={elapsed:.1f}s)")
        elif etype == "on_chain_end":
            # 根图结束事件携带完整最终状态（与 ainvoke 返回等价）
            if event.get("parent_id") is None:
                final_state = event.get("data", {}).get("output")
    return final_state


# ==================== 主入口 ====================

# 规则ID到审核维度的映射（前端checklist ID -> system prompt中的维度）
RULE_ID_TO_DIMENSION = {
    "1": "text_norm",      # 1.1 错别字与形近字检查
    "2": "text_norm",      # 1.2 标点符号规范性
    "3": "text_norm",      # 1.3 语法结构检查
    "4": "legal_term",     # 2.1 法律术语规范性
    "5": "rights_duty",    # 2.2 权利义务对等性
    "6": "amount_accuracy", # 2.3 金额与数字准确性
    "7": "time_clause",    # 2.4 时间条款明确性
    "8": "logic_consistency", # 3.1 条款前后一致性
    "9": "logic_contradiction", # 3.2 条款间逻辑矛盾
    "10": "clause_ref",    # 3.3 引用条款准确性
    "11": "legal_compliance", # 4.1 法律合规性
    "12": "sensitive_words", # 4.2 敏感词汇检查
    "13": "clause_completeness", # 4.3 必备条款完整性
    "14": "ambiguity",     # 5.1 歧义性表述
    "15": "redundancy",    # 5.2 冗余与重复
}

def audit_contract_with_agent_sync(
    text: str,
    agent=None,
    model: str = None,
    selected_rules: list[str] = None
) -> ContractAuditReport:
    """合同审核主入口（同步版本）。

    流程：
    1. 确定性管线：金额/日期/条款引用/甲乙方名称校验（零 LLM）
    2. 合同类型识别：轻量 LLM 调用
    3. 合同写入 VFS（保留，兼容 Agent 模式）
    4. 单次 LLM 深度分析：合同全文 + 规则注入 → issues（方案 D，替代 Agent 循环）
    5. 验证回路：查幻觉 + 查遗漏
    6. 组装 ContractAuditReport

    Args:
        text: 合同文本内容（markdown）
        agent: 预创建的 Agent（单次调用模式不使用，保留兼容）
        model: 模型名称
        selected_rules: 可选，选中的规则ID列表（如 ["1", "2", "3"]），为空则使用全部规则

    Returns:
        ContractAuditReport: 审核报告
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_invoke_agent(text, agent, model, selected_rules))
    finally:
        loop.close()


async def _invoke_agent(text: str, agent, model: str = None, selected_rules: list[str] = None) -> ContractAuditReport:
    """异步执行合同审核全流程。"""

    # 步骤 1：确定性管线（零 LLM）
    print("[1/5] 确定性管线校验中...")
    deterministic_findings = run_deterministic_audit(text)
    det_summary = summarize_findings(deterministic_findings)
    print(f"  确定性校验: {det_summary['total']} 项，通过 {det_summary['passed']}，失败 {det_summary['failed']}")

    # 步骤 2：合同类型识别（轻量 LLM）
    print("[2/5] 合同类型识别中...")
    contract_type, confidence, type_reason = classify_contract(text)
    print(f"  类型: {contract_type.value}（置信度: {confidence:.0%}）")

    # 步骤 3：合同写入 VFS（供 grep 搜索用）
    print("[3/5] 合同写入 VFS...")
    contract_id, vfs_path = _save_contract_to_vfs(text)
    print(f"  VFS 路径: {vfs_path}")

    # 步骤 3.5：预加载 SKILL 和类型规则内容（直接注入 user message，省掉 Agent read_file）
    skill_content = _read_skill_file("SKILL.md") or ""
    type_rule_file = get_skill_filename(contract_type)
    type_rule_content = _read_skill_file(type_rule_file) if type_rule_file else ""
    print(f"  预加载规则: SKILL.md ({len(skill_content)} 字符), {type_rule_file or '无'} ({len(type_rule_content)} 字符)")

    # 步骤 4：单次 LLM 深度分析（方案 D：替代 Agent 多轮工具调用）
    # 0 次工具调用，1 次 LLM 调用，LLM 注意力 100% 集中在条款分析上
    print("[4/5] 单次 LLM 深度分析中...")
    llm = _create_llm(model=model)
    _start = time.monotonic()
    issues = []
    audit_status = "success"
    audit_status_msg = ""
    try:
        issues = await _audit_with_single_call(
            llm, text, contract_type, confidence, type_reason,
            det_summary, skill_content, type_rule_content, _start, selected_rules
        )
        print(f"  LLM 输出: {len(issues)} 个问题")
    except TimeoutError as e:
        # LLM 超时：分析未完成，结果不可信，绝不能当成「审核通过」
        audit_status = "llm_timeout"
        audit_status_msg = str(e)
        print(f"  [WARN] 深度分析超时，标记为 llm_timeout：{e}")
    except Exception as e:
        audit_status = "error"
        audit_status_msg = str(e)
        print(f"  [WARN] 深度分析异常，标记为 error：{e}")

    # 组装报告（deterministic_findings 和 validation_time 由代码填充）
    if audit_status == "success":
        summary = _build_summary(issues, deterministic_findings)
    else:
        # 重要：在 summary 中明确指出「分析未完成」，避免被误解为「合同没问题」
        summary = (
            f"⚠️ 审核未完成（{audit_status}）：{audit_status_msg}。"
            f"当前结论不可信，请重新发起审核。"
        )
    report = ContractAuditReport(
        contract_id=contract_id,
        contract_type=contract_type,
        validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        deterministic_findings=deterministic_findings,
        issues=issues,
        overall_risk_level=_calc_risk_level(issues),
        summary=summary,
        status=audit_status,
        status_message=audit_status_msg,
    )

    # 步骤 5：验证回路（步骤 7 完整实现）
    print("[5/5] 验证回路校验中...")
    report.issues, report.deterministic_findings = verify_issues(
        report.issues, text, report.deterministic_findings
    )

    # 更新统计字段
    # 注意：超时/异常（status != success）时绝不覆盖告警 summary 与 risk_level，
    # 否则会把「分析未完成」重新粉饰成「审核通过，未发现问题」，再次误导用户。
    if report.status == "success":
        report.overall_risk_level = _calc_risk_level(report.issues)
        report.summary = _build_summary(report.issues, report.deterministic_findings)
    else:
        # 保持超时/异常告警文案与 status 不变；risk_level 标记 unknown 以反映「不可信」
        report.overall_risk_level = "unknown"
    report.validation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 清理 VFS
    _cleanup_contract_from_vfs(contract_id)

    print(f"  验证完成: {report.unverified_count} 个未验证 issue")
    print(f"  最终结果: {report.overall_risk_level} - {report.summary}")

    return report


async def audit_contract_stream(
    text: str,
    model: str = None,
    selected_rules: list[str] = None,
):
    """方案 B：流式合同审核生成器（async generator）。

    逐步向外产出事件（JSON 文本行，前端按 SSE/逐行解析）：
      {"type": "stage",  "stage": "...", "message": "..."}   # 阶段进度
      {"type": "token",  "content": "..."}                    # LLM 实时增量 token
      {"type": "done",   "report": {...}}                     # 最终完整报告
      {"type": "error",  "message": "..."}                    # 致命错误（非 LLM 超时）

    LLM 分析阶段通过 on_token 回调实时推送 token，避免长合同等待期间前端白屏 /
    误以为卡死；其余阶段（确定性校验、类型识别、验证回路）推送 stage 进度。
    """
    import json as _json

    def _emit(obj: dict) -> str:
        return _json.dumps(obj, ensure_ascii=False)

    # 步骤 1：确定性管线（零 LLM）
    yield _emit({"type": "stage", "stage": "deterministic", "message": "正在执行确定性校验（金额/日期/条款/甲乙方）..."})
    deterministic_findings = run_deterministic_audit(text)
    det_summary = summarize_findings(deterministic_findings)
    print(f"  确定性校验: {det_summary['total']} 项，通过 {det_summary['passed']}，失败 {det_summary['failed']}")

    # 步骤 2：合同类型识别（轻量 LLM）
    yield _emit({"type": "stage", "stage": "classify", "message": "正在识别合同类型..."})
    contract_type, confidence, type_reason = classify_contract(text)
    print(f"  类型: {contract_type.value}（置信度: {confidence:.0%}）")

    # 步骤 3：合同写入 VFS
    contract_id, vfs_path = _save_contract_to_vfs(text)

    # 步骤 3.5：预加载规则
    skill_content = _read_skill_file("SKILL.md") or ""
    type_rule_file = get_skill_filename(contract_type)
    type_rule_content = _read_skill_file(type_rule_file) if type_rule_file else ""

    # 步骤 4：单次 LLM 深度分析（流式）
    # 方案 B：在生成器内直接 astream，每收到一个 chunk 立即 yield token 事件，
    # 实现前端「实时生成中」的逐步渲染，避免长合同等待时白屏/误判卡死。
    yield _emit({"type": "stage", "stage": "llm", "message": "AI 正在深度分析合同条款（实时生成中）..."})
    llm = _create_llm(model=model)
    _start = time.monotonic()
    issues = []
    audit_status = "success"
    audit_status_msg = ""
    try:
        user_message = _build_single_call_user_message(
            text, contract_type, confidence, type_reason,
            det_summary, skill_content, type_rule_content, selected_rules
        )
        content = ""
        _buf = ""
        async for chunk in llm.astream([
            {"role": "system", "content": SINGLE_CALL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]):
            delta = getattr(chunk, "content", "") or ""
            if not delta:
                continue
            content += delta
            _buf += delta
            # 每累积约 24 字 flush 一次，兼顾实时性与传输粒度
            if len(_buf) >= 24:
                yield _emit({"type": "token", "content": _buf})
                _buf = ""
        if _buf:
            yield _emit({"type": "token", "content": _buf})

        # 解析 LLM 输出
        data = _extract_first_json(content)
        if data and isinstance(data, dict):
            for issue_data in data.get("issues", []):
                try:
                    issues.append(_build_issue(issue_data))
                except Exception as e:
                    print(f"    [single-call] 解析 issue 失败: {e}")
        else:
            print(f"    [single-call] 无法解析 JSON 输出，原始内容前200字符: {content[:200]}")
        print(f"  LLM 输出: {len(issues)} 个问题")
    except TimeoutError as e:
        audit_status = "llm_timeout"
        audit_status_msg = str(e)
        print(f"  [WARN] 深度分析超时，标记为 llm_timeout：{e}")
    except Exception as e:
        audit_status = "error"
        audit_status_msg = str(e)
        print(f"  [WARN] 深度分析异常，标记为 error：{e}")

    # 组装报告
    if audit_status == "success":
        summary = _build_summary(issues, deterministic_findings)
    else:
        summary = (
            f"⚠️ 审核未完成（{audit_status}）：{audit_status_msg}。"
            f"当前结论不可信，请重新发起审核。"
        )
    report = ContractAuditReport(
        contract_id=contract_id,
        contract_type=contract_type,
        validation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        deterministic_findings=deterministic_findings,
        issues=issues,
        overall_risk_level=_calc_risk_level(issues),
        summary=summary,
        status=audit_status,
        status_message=audit_status_msg,
    )

    # 步骤 5：验证回路
    yield _emit({"type": "stage", "stage": "verify", "message": "正在执行验证回路（查幻觉/查遗漏）..."})
    report.issues, report.deterministic_findings = verify_issues(
        report.issues, text, report.deterministic_findings
    )

    if report.status == "success":
        report.overall_risk_level = _calc_risk_level(report.issues)
        report.summary = _build_summary(report.issues, report.deterministic_findings)
    else:
        report.overall_risk_level = "unknown"
    report.validation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    _cleanup_contract_from_vfs(contract_id)

    # 最终推送完整报告
    yield _emit({"type": "done", "report": report.model_dump()})


# ==================== 测试 ====================

if __name__ == "__main__":
    test_contract = """
劳动合同

甲方：北京某某科技有限公司
统一社会信用代码：91110000XXXXXXXXXX
乙方：张三
身份证号：110101199001011234

第一条 合同期限
本合同自2024年1月1日起生效，至2027年12月31日止，期限为三年。

第二条 工资待遇
乙方月工资为人民币伍仟元整（5000元），甲方应于每月15日前以银行转账方式支付上月工资。

第三条 违约责任
如甲方未按时支付工资，应向乙方支付罚款5000元。
如乙方违约，应赔偿甲方因此造成的实际经济损失。

第四条 保密义务
乙方应保守甲方的商业秘密，本合同终止后仍然有效。

甲方（签章）：北京某某科技有限公司
乙方（签字）：张三
签订日期：2024年1月1日
"""

    print("=" * 60)
    print("合同审核 Deep Agent 测试")
    print("=" * 60)

    report = audit_contract_with_agent_sync(test_contract)

    print(f"\n{'=' * 60}")
    print(f"审核结果:")
    print(f"  合同 ID: {report.contract_id}")
    print(f"  合同类型: {report.contract_type.value}")
    print(f"  整体风险: {report.overall_risk_level}")
    print(f"  总结: {report.summary}")
    print(f"  确定性校验: {len(report.deterministic_findings)} 项（失败 {report.deterministic_fail_count}）")
    print(f"  问题数: {len(report.issues)}（high={report.high_severity_count}, medium={report.medium_severity_count}, low={report.low_severity_count}）")
    print(f"  未验证: {report.unverified_count}")
    print(f"  LLM 覆盖率: {report.llm_coverage_rate}")

    # 打印 issues 详情（诊断未验证原因）
    print(f"\n{'=' * 60}")
    print("Issues 详情:")
    for i, issue in enumerate(report.issues, 1):
        verified_mark = "✓" if issue.verified else "✗"
        print(f"\n[{i}] {verified_mark} {issue.severity} | {issue.rule_id} | {issue.rule_category}")
        print(f"    description: {issue.description}")
        print(f"    original:    {issue.original}")
        print(f"    location:    {issue.evidence_location}")
        if not issue.verified:
            print(f"    note:        {issue.verification_note}")
