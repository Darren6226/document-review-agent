"""发票校验数据模型
使用 Pydantic 定义结构化输出

合同审核数据流（Mermaid 参考图）：
flowchart LR
    A[前端上传 PDF] --> B[/api/contract/overview]
    B --> C[MinerU 解析 PDF]
    C --> D[LLM 提取 ContractOverview]
    D --> E[前端展示概览]
    E --> F[点击审核按钮]
    F --> G[/api/contract/audit]
    G --> H[MinerU 再次解析 PDF]
    H --> I[确定性管线 金额/日期/条款/甲乙方]
    I --> J[合同类型识别 LLM]
    J --> K[合同写入 VFS]
    K --> L[Agent 审核 VFS+Skill+工具]
    L --> M[双向验证回路 查幻觉+查遗漏]
    M --> N[ContractAuditReport]
    N --> O[前端展示结果]
    style A fill:#bbdefb,color:#0d47a1
    style G fill:#bbdefb,color:#0d47a1
    style I fill:#c8e6c9,color:#1a5e20
    style L fill:#fff3e0,color:#e65100
    style M fill:#f3e5f5,color:#7b1fa2
    style N fill:#c8e6c9,color:#1a5e20
"""

from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator


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


# ============================================
# 合同审核数据模型（Harness Engineering v2）
# 体现：三重证据链追溯 + 双向验证回路
# ============================================

class ContractType(str, Enum):
    """合同类型（用于动态加载专属 Skill）"""
    LABOR = "labor"       # 劳动合同
    SALES = "sales"       # 买卖合同
    LEASE = "lease"       # 租赁合同
    LOAN = "loan"         # 借款合同
    GENERAL = "general"   # 通用/其他


class IssueSeverity(str, Enum):
    """问题严重程度"""
    HIGH = "high"       # 必须修正 - 可能导致合同无效或重大损失
    MEDIUM = "medium"   # 建议修正 - 可能引发争议
    LOW = "low"         # 可优化 - 规范性问题


class BasisType(str, Enum):
    """判定依据来源（证据链第三重：判定来源）"""
    LLM_JUDGMENT = "llm_judgment"       # LLM 语义判定
    DETERMINISTIC = "deterministic"     # 确定性代码判定
    HYBRID = "hybrid"                   # 混合判定（确定性发现 + LLM 解释）


class ContractIssue(BaseModel):
    """合同审核问题（带三重证据链：原文位置 + 规则编号 + 判定来源）"""
    # 基本字段
    rule_category: str = Field(..., description="规则类别，如'法律术语规范性'、'金额准确性'")
    issue_type: str = Field(..., description="问题类型，如'法律术语错误'、'大小写不一致'")
    issue_category: str = Field(
        default="other",
        description="问题性质分类，用于验证回路精准分流。"
                    "clause_invalid: 条款存在但无效/有问题（必须提供 original 引用）；"
                    "clause_missing: 合同缺少必备条款（original='无' 是合法的）；"
                    "term_error: 术语/表述错误（必须提供 original 引用）；"
                    "other: 其他类型"
    )
    description: str = Field(..., description="问题详细描述")
    original: str = Field(default="", description="原文中有问题的片段（精确引用）")
    suggestion: str = Field(..., description="修改建议")
    severity: IssueSeverity = Field(..., description="严重程度")
    legal_risk: str = Field(default="", description="法律风险说明（high 必填）")

    # 证据链字段（优化 4）
    evidence_location: str = Field(default="", description="原文定位，如'第三条第二款'、'第47行'")
    rule_id: str = Field(..., description="精确规则编号，如 LABOR.2.1 / SALES.3.2 / DETERM.amount_case")
    basis_type: BasisType = Field(default=BasisType.LLM_JUDGMENT, description="判定依据来源")
    deterministic_ref: Optional[str] = Field(None, description="若基于确定性 finding，引用 finding_id")

    # 验证状态（优化 3：双向验证回路）
    verified: bool = Field(default=False, description="是否通过验证回路校验")
    verification_note: str = Field(default="", description="验证说明（未通过时填写原因）")

    @field_validator(
        "rule_category", "issue_type", "description", "original", "suggestion",
        "legal_risk", "evidence_location", "rule_id", "verification_note",
        mode="before"
    )
    @classmethod
    def _normalize_str(cls, v):
        """数据入口统一兜底：LLM 可能输出 null / 非字符串，直接归一为空串。

        根治此前「legal_risk=null 导致整条 issue 被 pydantic 拒收、最终误判为
        审核通过」的问题——防御放在模型层，所有调用处（_build_issue 等）无需
        各自散落兜底逻辑。
        """
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        return str(v)

    @field_validator("legal_risk", mode="after")
    @classmethod
    def _require_legal_risk_for_high(cls, v, info):
        """业务强约束：severity=high 必须有法律风险说明。

        缺失时不静默丢弃整条 issue，而是给出明确占位告警，让前端/报告能识别
        「高风险问题但模型未填法律后果」这一异常，而非降级成普通问题。
        """
        severity = info.data.get("severity")
        if severity == IssueSeverity.HIGH and not v.strip():
            return "（模型未提供法律风险说明，需人工补充分析该 high 问题的法律后果）"
        return v


class DeterministicFinding(BaseModel):
    """确定性校验结果（纯代码判定，零 LLM）"""
    finding_id: str = Field(..., description="finding 唯一标识，如 DETERM.amount_case.1")
    rule_id: str = Field(..., description="对应规则编号")
    rule_category: str = Field(..., description="规则类别")
    passed: bool = Field(..., description="是否通过")
    field: str = Field(default="", description="校验字段")
    expected: Optional[Any] = Field(None, description="期望值")
    actual: Optional[Any] = Field(None, description="实际值")
    detail: str = Field(..., description="校验详情")
    location: str = Field(default="", description="原文定位")
    # 双向验证回路：LLM 是否覆盖了此 finding
    covered_by_llm: bool = Field(default=False, description="LLM 的 issues 是否覆盖了此 FAIL 项")


class ContractAuditReport(BaseModel):
    """合同审核报告（汇总确定性结果 + LLM 结果 + 验证状态）"""
    contract_id: str = Field(..., description="合同标识")
    contract_type: ContractType = Field(default=ContractType.GENERAL, description="合同类型")
    validation_time: str = Field(..., description="审核时间")

    deterministic_findings: List[DeterministicFinding] = Field(default_factory=list, description="确定性校验结果")
    issues: List[ContractIssue] = Field(default_factory=list, description="审核问题列表")

    overall_risk_level: str = Field(..., description="整体风险等级: high/medium/low/none")
    summary: str = Field(..., description="审核总结")

    # 审核状态：区分「真的没问题」与「分析未成功（如 LLM 超时）」
    #   success     - 全流程正常完成（含「未发现问题」）
    #   llm_timeout - 深度分析阶段 LLM 调用超时，结果不可信
    #   error       - 其它异常导致分析未完成
    status: str = Field(default="success", description="审核状态: success/llm_timeout/error")
    status_message: str = Field(default="", description="状态说明（如超时提示），用于前端告警展示")

    # 统计属性
    @property
    def high_severity_count(self) -> int:
        return len([i for i in self.issues if i.severity == IssueSeverity.HIGH])

    @property
    def medium_severity_count(self) -> int:
        return len([i for i in self.issues if i.severity == IssueSeverity.MEDIUM])

    @property
    def low_severity_count(self) -> int:
        return len([i for i in self.issues if i.severity == IssueSeverity.LOW])

    @property
    def unverified_count(self) -> int:
        """未通过验证回路的 issue 数量"""
        return len([i for i in self.issues if not i.verified])

    @property
    def deterministic_fail_count(self) -> int:
        """确定性校验失败数"""
        return len([f for f in self.deterministic_findings if not f.passed])

    @property
    def llm_coverage_rate(self) -> float:
        """LLM 对确定性 FAIL 项的覆盖率（验证回路关键指标）"""
        fails = [f for f in self.deterministic_findings if not f.passed]
        if not fails:
            return 1.0
        covered = len([f for f in fails if f.covered_by_llm])
        return round(covered / len(fails), 2)
