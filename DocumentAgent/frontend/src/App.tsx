import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { DocumentUpload } from './components/DocumentUpload';
import { DocumentPreview } from './components/DocumentPreview';
import { OCRResults } from './components/OCRResults';
import { ReviewResults } from './components/ReviewResults';
import { ContractReviewResults } from './components/ContractReviewResults';
import { HistoryPanel } from './components/HistoryPanel';
import {
  uploadInvoice,
  validateInvoice,
  uploadContract,
  auditContractStream,
  InvoiceData,
  ValidationReport,
  ContractOverview,
  ContractAuditResult
} from './services/api';

export default function App() {
  const [activeMenu, setActiveMenu] = useState('票据审查');
  const [uploadedDocument, setUploadedDocument] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [ocrData, setOcrData] = useState<InvoiceData | null>(null);
  const [contractData, setContractData] = useState<ContractOverview | null>(null);
  const [contractParseId, setContractParseId] = useState<string | null>(null);
  const [invoiceId, setInvoiceId] = useState<string | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [contractAuditResult, setContractAuditResult] = useState<ContractAuditResult | null>(null);
  const [contractStreaming, setContractStreaming] = useState(false);
  const [contractLiveStage, setContractLiveStage] = useState('');
  const [contractLiveToken, setContractLiveToken] = useState('');
  const [showReviewResults, setShowReviewResults] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDocumentUpload = async (file: File) => {
    setIsProcessing(true);
    setSidebarCollapsed(true);
    setError(null);
    setUploadedFile(file);

    try {
      // 创建预览URL
      const reader = new FileReader();
      reader.onload = (e) => {
        setUploadedDocument(e.target?.result as string);
      };
      reader.readAsDataURL(file);

      // 根据当前菜单调用不同的API
      if (activeMenu === '合同审查') {
        // 合同审查
        const response = await uploadContract(file);
        console.log('Contract Response:', response);

        if (response.success && response.data) {
          console.log('Contract Data:', response.data);
          setContractData(response.data);
          // 保存 overview 阶段的解析标识，audit 时复用已解析的 markdown，避免重复 MinerU 解析
          setContractParseId(response.parse_id || null);
          setOcrData(null); // 清空发票数据
          setInvoiceId(null);
        } else {
          throw new Error(response.message || '合同信息提取失败');
        }
      } else {
        // 票据审查（默认）
        const response = await uploadInvoice(file);
        console.log('OCR Response:', response);

        if (response.success && response.data) {
          console.log('OCR Data:', response.data);
          setOcrData(response.data);
          setContractData(null); // 清空合同数据
          setInvoiceId(response.invoice_id || null);
        } else {
          throw new Error(response.message || 'OCR识别失败');
        }
      }
    } catch (err) {
      console.error('上传失败:', err);
      setError(err instanceof Error ? err.message : '上传失败');
      // 如果失败,重置状态
      setUploadedDocument(null);
      setUploadedFile(null);
      setSidebarCollapsed(false);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStartReview = async () => {
    // 合同审查：不需要额外操作,审查清单已经在OCRResults中显示
    if (activeMenu === '合同审查') {
      // 合同审查清单已经自动显示,这里什么都不做
      return;
    }

    // 票据审查：调用API
    if (!ocrData || !invoiceId) {
      setError('请先上传并识别发票');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      // 调用后端API进行审查
      const response = await validateInvoice(invoiceId, ocrData);

      if (response.success && response.report) {
        setValidationReport(response.report);
        setShowReviewResults(true);
      } else {
        throw new Error(response.message || '审查失败');
      }
    } catch (err) {
      console.error('审查失败:', err);
      setError(err instanceof Error ? err.message : '审查失败');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStartContractReview = async (selectedRuleIds?: string[]) => {
    // 合同审查：用保留的原始文件调用后端审核端点（重新上传文件，方案 B 流式）
    if (!uploadedFile) {
      setError('请先上传合同文件');
      return;
    }

    setIsProcessing(true);
    setError(null);
    setContractStreaming(true);
    setContractLiveStage('正在准备审核...');
    setContractLiveToken('');
    setContractAuditResult(null);
    setShowReviewResults(true); // 提前进入结果页，实时展示分析进度

    try {
      await auditContractStream(
        uploadedFile,
        (evt) => {
          if (evt.type === 'stage') {
            setContractLiveStage(evt.message);
          } else if (evt.type === 'token') {
            setContractLiveToken((prev) => prev + evt.content);
          } else if (evt.type === 'done') {
            setContractAuditResult(evt.report);
            setContractLiveStage('');
            setContractLiveToken('');
            setContractStreaming(false);
          } else if (evt.type === 'error') {
            setError(evt.message || '审查失败');
            setContractStreaming(false);
          }
        },
        selectedRuleIds,
        contractParseId ?? undefined
      );
    } catch (err) {
      console.error('审查失败:', err);
      setError(err instanceof Error ? err.message : '审查失败');
      setContractStreaming(false);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setUploadedDocument(null);
    setUploadedFile(null);
    setOcrData(null);
    setContractData(null);
    setContractParseId(null);
    setInvoiceId(null);
    setValidationReport(null);
    setContractAuditResult(null);
    setContractStreaming(false);
    setContractLiveStage('');
    setContractLiveToken('');
    setShowReviewResults(false);
    setIsProcessing(false);
    setError(null);
    setSidebarCollapsed(false);
  };

  return (
    <div className="flex h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50 dynamic-bg">
      <Sidebar 
        activeMenu={activeMenu} 
        onMenuChange={setActiveMenu}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 头部 */}
        <div className="glass-effect-dark border-b border-white/50 px-6 py-4 flex items-center justify-between shadow-premium">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowHistory(true)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-300 ${
                showHistory
                  ? 'bg-blue-100 text-blue-700 shadow-md'
                  : 'text-gray-700 hover:bg-white/60 hover:shadow-md'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm">历史记录</span>
            </button>
          </div>

        </div>

        {/* 主内容区 */}
        <div className="flex-1 overflow-auto">
          {/* 错误提示 */}
          {error && (
            <div className="absolute top-20 left-1/2 transform -translate-x-1/2 z-50 max-w-md">
              <div className="glass-effect-dark border border-red-300 bg-red-50 px-6 py-4 rounded-xl shadow-premium-lg flex items-center gap-3">
                <div className="text-red-500">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <div className="text-red-800 font-medium">错误</div>
                  <div className="text-red-700 text-sm">{error}</div>
                </div>
                <button
                  onClick={() => setError(null)}
                  className="text-red-500 hover:text-red-700 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {showHistory ? (
            <div className="h-full p-6">
              <HistoryPanel
                embedded
                onClose={() => setShowHistory(false)}
              />
            </div>
          ) : !uploadedDocument && !showReviewResults ? (
            <DocumentUpload onUpload={handleDocumentUpload} activeMenu={activeMenu} />
          ) : showReviewResults ? (
            activeMenu === '合同审查' ? (
              <ContractReviewResults
                onBack={handleReset}
                auditResult={contractAuditResult}
                documentUrl={uploadedDocument}
                streaming={contractStreaming}
                liveStage={contractLiveStage}
                liveToken={contractLiveToken}
              />
            ) : (
              <ReviewResults
                onBack={handleReset}
                activeMenu={activeMenu}
                validationReport={validationReport}
              />
            )
          ) : (
            <div className="flex h-full">
              <DocumentPreview
                imageUrl={uploadedDocument!}
                onStartReview={handleStartReview}
                isProcessing={isProcessing}
                activeMenu={activeMenu}
              />
              <OCRResults
                data={ocrData}
                contractData={contractData}
                activeMenu={activeMenu}
                isProcessing={isProcessing}
                onStartContractReview={handleStartContractReview}
              />
            </div>
          )}
        </div>
      </div>

    </div>
  );
}