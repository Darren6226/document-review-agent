"""
发票校验数据模型
使用 Pydantic 定义结构化输出
"""

from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field


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
