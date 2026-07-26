/**
 * API 服务层
 * 处理所有与后端的通信
 */

// API 基础URL
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// API 响应类型
export interface APIResponse<T = any> {
  success: boolean;
  message: string;
  data?: T;
}

// 发票数据类型
export interface InvoiceData {
  invoice_type: string;
  province?: string;
  invoice_code: string;
  invoice_number: string;
  issue_date: string;
  check_code?: string;
  purchaser_name: string;
  purchaser_tax_id: string;
  purchaser_address?: string;
  purchaser_bank?: string;
  seller_name: string;
  seller_tax_id: string;
  seller_address?: string;
  seller_bank?: string;
  total_amount: number;
  total_tax: number;
  total_amount_with_tax: number;
  amount_in_words?: string;
  line_items: LineItem[];
  payee?: string;
  checker?: string;
  drawer?: string;
  remarks?: string;
}

export interface LineItem {
  row: string;
  name: string;
  specification?: string;
  unit?: string;
  quantity?: number;
  unit_price?: number;
  amount: number;
  tax_rate: number;
  tax_amount: number;
}

// OCR 上传响应
export interface OCRResponse {
  success: boolean;
  message: string;
  data?: InvoiceData;
  invoice_id?: string;
}

// 审查结果类型
export interface ValidationResult {
  agent_name: string;
  level: 'error' | 'warning' | 'info';
  category: string;
  message: string;
  field?: string;
  expected?: any;
  actual?: any;
  suggestion?: string;
}

export interface AgentReport {
  agent_name: string;
  execution_time: number;
  results: ValidationResult[];
}

export interface ValidationReport {
  invoice_id: string;
  validation_time: string;
  overall_status: 'PASSED' | 'FAILED' | 'WARNING';
  summary: string;
  agent_reports: AgentReport[];
}

export interface ValidationResponse {
  success: boolean;
  message: string;
  report?: ValidationReport;
}

/**
 * 上传发票图片并进行OCR识别
 */
export async function uploadInvoice(file: File): Promise<OCRResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/invoice/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `上传失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 执行发票审查
 */
export async function validateInvoice(
  invoiceId: string,
  invoiceData: InvoiceData
): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE_URL}/api/invoice/validate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      invoice_id: invoiceId,
      invoice_data: invoiceData,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `审查失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  return response.json();
}

// ==================== 合同审查相关 ====================

/**
 * 合同概览数据类型
 */
export interface ContractOverview {
  contract_id?: string;
  contract_type: string;
  contract_title: string;
  party_a: string;
  party_a_type: string;
  party_a_details: string;
  party_b: string;
  party_b_type: string;
  party_b_details: string;
  total_amount: string;
  amount_in_words: string;
  currency: string;
  effective_date: string;
  expiry_date: string;
  duration: string;
  signing_date: string;
  key_terms: string[];
  special_clauses: string;
}

/**
 * 合同概览响应
 */
export interface ContractOverviewResponse {
  success: boolean;
  message: string;
  data?: ContractOverview;
}

/**
 * 上传合同并提取概览信息
 */
export async function uploadContract(file: File): Promise<ContractOverviewResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/contract/overview`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `合同上传失败: ${response.statusText}`);
  }

  return response.json();
}

/**
 * 合同审查问题
 */
export interface ContractAuditIssue {
  rule_category: string;
  issue_type: string;
  description: string;
  original: string;
  suggestion: string;
  severity: 'high' | 'medium' | 'low';
  legal_risk: string;
}

/**
 * 合同审查结果
 */
export interface ContractAuditResult {
  has_issues: boolean;
  issues: ContractAuditIssue[];
  summary: string;
  overall_risk_level: 'high' | 'medium' | 'low' | 'none';
  corrected_text: string;
}

/**
 * 合同审查响应
 */
export interface ContractAuditResponse {
  success: boolean;
  message: string;
  data?: ContractAuditResult;
}

/**
 * 审查合同
 */
export async function auditContract(contractId: string): Promise<ContractAuditResponse> {
  const formData = new FormData();
  formData.append('contract_id', contractId);

  const response = await fetch(`${API_BASE_URL}/api/contract/audit`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `合同审查失败: ${response.statusText}`);
  }

  return response.json();
}
