"""
文档审核后端包
提供完整的文档审核功能，包括：
- 发票 OCR 识别与提取
- 发票智能校验
- 合同信息提取
- 合同专业审核
"""

# 使用绝对导入以支持直接运行
from services.invoice_verification import InvoiceExtractionSystem, Invoice
from services.invoice_validation import InvoiceValidationSystem, FinalValidationReport
from services.contract_extraction import extract_contract_info_dict, ContractOverview
from prompts.contract_audit_prompt import (
    create_professional_contract_audit_prompt,
    PROFESSIONAL_CONTRACT_AUDIT_RULES,
    AuditResult,
)

__all__ = [
    # 发票相关
    "InvoiceExtractionSystem",
    "Invoice",
    "InvoiceValidationSystem",
    "FinalValidationReport",
    
    # 合同相关
    "extract_contract_info_dict",
    "ContractOverview",
    
    # 提示词模板
    "create_professional_contract_audit_prompt",
    "PROFESSIONAL_CONTRACT_AUDIT_RULES",
    "AuditResult",
]
