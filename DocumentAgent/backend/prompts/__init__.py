"""
提示词模板包
提供合同审核等专业提示词模板
"""

from .contract_audit_prompt import (
    create_professional_contract_audit_prompt,
    PROFESSIONAL_CONTRACT_AUDIT_RULES,
    PROFESSIONAL_SYSTEM_PROMPT,
    PROFESSIONAL_USER_PROMPT,
    AuditResult,
    Issue,
    ModificationMapping,
)

__all__ = [
    "create_professional_contract_audit_prompt",
    "PROFESSIONAL_CONTRACT_AUDIT_RULES",
    "PROFESSIONAL_SYSTEM_PROMPT",
    "PROFESSIONAL_USER_PROMPT",
    "AuditResult",
    "Issue",
    "ModificationMapping",
]
