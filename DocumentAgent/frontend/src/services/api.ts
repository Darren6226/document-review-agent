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
  // overview 阶段缓存的 MinerU 解析标识，audit 时携带以复用已解析的 markdown
  parse_id?: string;
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
 * 合同审查问题（与后端 ContractIssue 对齐，含三重证据链 + 验证状态）
 */
export interface ContractAuditIssue {
  rule_category: string;
  issue_type: string;
  description: string;
  original: string;
  suggestion: string;
  severity: 'high' | 'medium' | 'low';
  legal_risk: string;
  // 证据链字段
  evidence_location: string;
  rule_id: string;
  basis_type: 'llm_judgment' | 'deterministic' | 'hybrid';
  deterministic_ref?: string | null;
  // 验证状态
  verified: boolean;
  verification_note: string;
}

/**
 * 确定性校验结果（与后端 DeterministicFinding 对齐）
 */
export interface DeterministicFinding {
  finding_id: string;
  rule_id: string;
  rule_category: string;
  passed: boolean;
  field: string;
  expected?: any;
  actual?: any;
  detail: string;
  location: string;
  covered_by_llm: boolean;
}

/**
 * 合同审查结果（与后端 ContractAuditReport 对齐）
 */
export interface ContractAuditResult {
  contract_id: string;
  contract_type: 'labor' | 'sales' | 'lease' | 'loan' | 'general';
  validation_time: string;
  deterministic_findings: DeterministicFinding[];
  issues: ContractAuditIssue[];
  overall_risk_level: 'high' | 'medium' | 'low' | 'none';
  summary: string;
  // 审核状态：success=正常完成；llm_timeout=深度分析超时（结果不可信）；error=其它异常
  status?: 'success' | 'llm_timeout' | 'error';
  status_message?: string;
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
 * 审查合同（重新上传文件，与后端 file: UploadFile 签名对齐）
 * @param file 合同文件
 * @param rules 可选，选中的审查规则ID列表（如 ["1", "2", "3"]），为空则使用全部规则
 * @param parseId 可选，overview 阶段返回的解析标识。携带后后端可复用已解析的 markdown，
 *        避免同一份 PDF 重复调用 MinerU 解析
 */
export async function auditContract(file: File, rules?: string[], parseId?: string): Promise<ContractAuditResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (rules && rules.length > 0) {
    formData.append('rules', JSON.stringify(rules));
  }
  if (parseId) {
    formData.append('parse_id', parseId);
  }

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

/**
 * 合同审查事件（SSE 实时推送，与后端 audit_contract_stream 对齐）
 */
export type ContractAuditStreamEvent =
  | { type: 'stage'; stage: string; message: string }
  | { type: 'token'; content: string }
  | { type: 'done'; report: ContractAuditResult }
  | { type: 'error'; message: string };

/**
 * 流式审查合同（方案 B）：使用 fetch + ReadableStream 逐行解析 SSE，
 * 通过 onEvent 回调实时把 stage / token / done / error 推给 UI。
 * 相比一次性返回，能在长合同分析期间实时展示进度，避免白屏/误判卡死。
 */
export async function auditContractStream(
  file: File,
  onEvent: (evt: ContractAuditStreamEvent) => void,
  rules?: string[],
  parseId?: string,
): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);
  if (rules && rules.length > 0) {
    formData.append('rules', JSON.stringify(rules));
  }
  if (parseId) {
    formData.append('parse_id', parseId);
  }

  const response = await fetch(`${API_BASE_URL}/api/contract/audit`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `合同审查失败: ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 按 SSE 分隔符 "\n\n" 切分完整事件
    let sepIndex: number;
    while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sepIndex).trim();
      buffer = buffer.slice(sepIndex + 2);
      if (!raw.startsWith('data:')) continue;
      const payload = raw.slice('data:'.length).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload) as ContractAuditStreamEvent);
      } catch {
        // 忽略无法解析的片段
      }
    }
  }
}

/**
 * 历史记录条目类型（与后端 history_store 对齐）
 */
export interface HistoryRecord {
  id: string;
  type: string;
  title: string;
  date: string;
  status: string;
  summary: string;
  risk_level?: string;
  detail?: any;
}

/**
 * 获取全部历史记录
 */
export async function getHistory(): Promise<HistoryRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/history`, {
    method: 'GET',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `获取历史记录失败: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data || [];
}
