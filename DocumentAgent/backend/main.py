"""
文档审核系统 - FastAPI 后端服务
支持票据审查和合同审查
"""

import os
import sys
import json
import uuid
import shutil
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from fastapi import Form

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 导入业务服务模块 (使用相对路径，不需要添加到 sys.path)
from services.invoice_verification import InvoiceExtractionSystem, Invoice
from services.invoice_validation import InvoiceValidationSystem, FinalValidationReport

# 导入合同审查模块
from services.contract_extraction import extract_contract_info_dict, ContractOverview

# ==================== 配置 ====================

# 创建必要的目录
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# API 配置 - 使用硅基流动
API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = "https://api.siliconflow.cn/v1"

# ==================== 数据模型 ====================

class OCRResponse(BaseModel):
    """OCR识别响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    invoice_id: Optional[str] = None


class ValidationRequest(BaseModel):
    """审查请求"""
    invoice_id: str
    invoice_data: Dict[str, Any]


class ValidationResponse(BaseModel):
    """审查响应"""
    success: bool
    message: str
    report: Optional[Dict[str, Any]] = None


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="文档审核系统 API",
    description="支持票据和合同的OCR识别与智能审查",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React 开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化系统
extraction_system = None
validation_system = None

if API_KEY:
    try:
        extraction_system = InvoiceExtractionSystem(
            api_key=API_KEY,
           model_name="Qwen/Qwen3.6-27B"  # 硅基流动模型
        )
        validation_system = InvoiceValidationSystem(
            api_key=API_KEY,
            enable_llm_validation=False  # 可设置为 True 启用 LLM 业务规则校验
        )
        print("发票识别和校验系统初始化成功")
    except Exception as e:
        print(f"⚠ 系统初始化警告：{e}")
else:
    print("⚠ 未设置 OPENAI_API_KEY 环境变量")


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "文档审核系统 API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "invoice_upload": "/api/invoice/upload",
            "invoice_validate": "/api/invoice/validate",
            "contract_overview": "/api/contract/overview",
            "health": "/api/health"
        }
    }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "extraction_system": extraction_system is not None,
        "validation_system": validation_system is not None,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/invoice/upload", response_model=OCRResponse)
async def upload_invoice(file: UploadFile = File(...)):
    """
    上传发票图片并进行OCR识别

    支持格式: PNG, JPG, JPEG, PDF
    """
    try:
        # 验证文件类型
        if not file.content_type or not file.content_type.startswith(('image/', 'application/pdf')):
            raise HTTPException(status_code=400, detail="不支持的文件类型,仅支持图片和PDF")

        # 验证文件大小 (20MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过20MB限制")

        # 生成唯一文件名
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = UPLOAD_DIR / unique_filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 检查系统是否初始化
        if not extraction_system:
            # 返回模拟数据用于测试
            return OCRResponse(
                success=True,
                message="OCR识别完成(测试模式)",
                data=_get_mock_invoice_data(),
                invoice_id=str(uuid.uuid4())
            )

        # 执行OCR识别
        print(f"正在识别发票: {file_path}")
        invoice = extraction_system.extract_from_image(str(file_path))

        # 转换为字典
        invoice_data = invoice.to_dict()

        return OCRResponse(
            success=True,
            message="发票识别成功",
            data=invoice_data,
            invoice_id=f"{invoice.invoice_code}_{invoice.invoice_number}"
        )

    except HTTPException:
        raise
    except ValidationError as e:
        print(f"发票数据验证失败: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="暂不支持该文档类型，请上传正确的增值税发票图片"
        )
    except Exception as e:
        print(f"OCR识别错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")


@app.post("/api/invoice/validate", response_model=ValidationResponse)
async def validate_invoice(request: ValidationRequest):
    """
    执行发票审查

    进行完整性、格式、计算和业务规则校验
    """
    try:
        invoice_data = request.invoice_data

        # 检查系统是否初始化
        if not validation_system:
            # 返回模拟审查结果
            return ValidationResponse(
                success=True,
                message="审查完成(测试模式)",
                report=_get_mock_validation_report(invoice_data)
            )

        # 执行校验
        print(f"正在审查发票: {request.invoice_id}")
        report = validation_system.validate_invoice(invoice_data)

        # 转换为字典
        report_data = report.model_dump(exclude_none=False)

        return ValidationResponse(
            success=True,
            message="发票审查完成",
            report=report_data
        )

    except Exception as e:
        print(f"审查错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"审查失败: {str(e)}")


# ==================== 模拟数据(用于测试) ====================

def _get_mock_invoice_data() -> Dict[str, Any]:
    """获取模拟发票数据"""
    return {
        "invoice_type": "增值税专用发票",
        "province": "上海",
        "invoice_code": "3100153130",
        "invoice_number": "14641426",
        "issue_date": "2016-06-02",
        "check_code": "",
        "purchaser_name": "百度时代网络技术(北京)有限公司",
        "purchaser_tax_id": "110108787751579",
        "purchaser_address": "北京市海淀区上地十街10号 010-59928888",
        "purchaser_bank": "招商银行股份有限公司北京上地支行 110920357610301",
        "seller_name": "上海爱信诺航天信息有限公司",
        "seller_tax_id": "310115687812026",
        "seller_address": "上海市浦东新区龙阳路2345号 021-50277777",
        "seller_bank": "中国工商银行上海市杨浦支行 1001241019000053363",
        "total_amount": 12580.00,
        "total_tax": 754.80,
        "total_amount_with_tax": 13334.80,
        "amount_in_words": "壹万叁仟叁佰叁拾肆元捌角整",
        "line_items": [
            {
                "row": "1",
                "name": "*信息技术服务*技术服务费",
                "specification": None,
                "unit": None,
                "quantity": None,
                "unit_price": None,
                "amount": 12580.00,
                "tax_rate": 0.06,
                "tax_amount": 754.80
            }
        ],
        "payee": "张三",
        "checker": "李四",
        "drawer": "王五",
        "remarks": ""
    }


def _get_mock_validation_report(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """获取模拟审查报告"""
    return {
        "invoice_id": f"{invoice_data.get('invoice_code', 'N/A')}_{invoice_data.get('invoice_number', 'N/A')}",
        "validation_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "overall_status": "PASSED",
        "summary": "发票校验完全通过,未发现任何问题",
        "agent_reports": [
            {
                "agent_name": "完整性校验Agent",
                "execution_time": 0.05,
                "results": [
                    {
                        "agent_name": "完整性校验Agent",
                        "level": "info",
                        "category": "完整性校验",
                        "message": "所有 13 个必填字段完整",
                        "field": None,
                        "expected": None,
                        "actual": None,
                        "suggestion": "专用发票核心信息齐全"
                    }
                ]
            },
            {
                "agent_name": "格式校验Agent",
                "execution_time": 0.03,
                "results": [
                    {
                        "agent_name": "格式校验Agent",
                        "level": "info",
                        "category": "格式校验",
                        "message": "发票代码格式正确",
                        "field": "invoice_code",
                        "expected": None,
                        "actual": invoice_data.get('invoice_code'),
                        "suggestion": None
                    },
                    {
                        "agent_name": "格式校验Agent",
                        "level": "info",
                        "category": "格式校验",
                        "message": "发票号码格式正确",
                        "field": "invoice_number",
                        "expected": None,
                        "actual": invoice_data.get('invoice_number'),
                        "suggestion": None
                    }
                ]
            },
            {
                "agent_name": "计算校验Agent",
                "execution_time": 0.02,
                "results": [
                    {
                        "agent_name": "计算校验Agent",
                        "level": "info",
                        "category": "计算校验",
                        "message": f"价税合计计算正确: {invoice_data.get('total_amount', 0):.2f} + {invoice_data.get('total_tax', 0):.2f} = {invoice_data.get('total_amount_with_tax', 0):.2f}",
                        "field": "total_amount_with_tax",
                        "expected": None,
                        "actual": None,
                        "suggestion": None
                    }
                ]
            },
            {
                "agent_name": "业务规则校验Agent",
                "execution_time": 0.01,
                "results": [
                    {
                        "agent_name": "业务规则校验Agent",
                        "level": "info",
                        "category": "业务规则校验",
                        "message": "未发现明显的业务逻辑问题",
                        "field": None,
                        "expected": None,
                        "actual": None,
                        "suggestion": None
                    }
                ]
            }
        ]
    }


# ==================== 合同审查 API ====================

class ContractOverviewResponse(BaseModel):
    """合同概览响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@app.post("/api/contract/overview", response_model=ContractOverviewResponse)
async def get_contract_overview(file: UploadFile = File(...)):
    """
    上传合同PDF/图片并提取概览信息

    提取内容：甲方、乙方、合同金额、日期等关键信息
    支持格式: PDF, PNG, JPG, JPEG
    """
    try:
        # 验证文件类型
        if not file.content_type or not file.content_type.startswith(('image/', 'application/pdf')):
            raise HTTPException(status_code=400, detail="不支持的文件类型,仅支持图片和PDF")

        # 验证文件大小 (20MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过20MB限制")

        # 生成唯一文件名
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'pdf'
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        file_path = UPLOAD_DIR / unique_filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"正在提取合同信息: {file_path}")

        # 如果不是PDF，暂时不支持
        if not file.content_type == 'application/pdf':
            raise HTTPException(
                status_code=400,
                detail="目前仅支持PDF格式的合同文件"
            )

        try:
            # 步骤 1: 使用 MinerU 解析 PDF
            print(f"  步骤 1: 调用 MinerU 解析 PDF...")
            import requests
            import json as json_lib
            import time
            import zipfile
            import os

            MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "https://mineru.net")
            MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")
            
            # 检查 API Key 是否配置
            if not MINERU_API_KEY:
                raise ValueError("未配置 MINERU_API_KEY，请在.env 文件中设置")

            # 构建 API URL
            batch_url = f"{MINERU_BASE_URL}/api/v4/file-urls/batch"
            
            # 步骤 1.1: 申请上传 URL
            print(f"  步骤 1.1: 申请文件上传 URL...")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MINERU_API_KEY}"
            }
            
            data = {
                "files": [
                    {
                        "name": file.filename,
                        "is_ocr": True,
                        "language": "ch"
                    }
                ],
                "enable_formula": True,
                "language": "ch",
                "layout_model": "doclayout_yolo",
                "enable_table": True
            }

            response = requests.post(batch_url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code") != 0:
                raise ValueError(f'申请上传 URL 失败：{result.get("msg", "未知错误")}')
            
            batch_id = result["data"]["batch_id"]
            file_urls = result["data"]["file_urls"]
            
            print(f"  批次 ID: {batch_id}")
            print(f"  获取到 {len(file_urls)} 个上传 URL")

            # 步骤 1.2: 上传文件
            print(f"  步骤 1.2: 上传文件到 MinerU...")
            with open(file_path, "rb") as f:
                upload_response = requests.put(file_urls[0], data=f, timeout=300)
                if upload_response.status_code not in [200, 201]:
                    raise ValueError(f"文件上传失败，状态码：{upload_response.status_code}")
            
            print(f"  文件上传成功")

            # 步骤 1.3: 等待解析完成
            print(f"  步骤 1.3: 等待 PDF 解析完成...")
            max_wait_time = 300  # 最大等待时间 5 分钟
            check_interval = 5   # 每 5 秒检查一次
            waited_time = 0
            
            while waited_time < max_wait_time:
                time.sleep(check_interval)
                waited_time += check_interval
                
                # 检查解析状态
                results_url = f"{MINERU_BASE_URL}/api/v4/extract-results/batch/{batch_id}"
                status_response = requests.get(results_url, headers=headers, timeout=30)
                status_response.raise_for_status()
                
                status_result = status_response.json()
                if status_result.get("code") != 0:
                    raise ValueError(f'获取解析结果失败：{status_result.get("msg", "未知错误")}')
                
                batch_data = status_result.get("data", {})
                extract_results = batch_data.get("extract_result", [])
                
                if extract_results and len(extract_results) > 0:
                    first_item = extract_results[0]
                    state = first_item.get("state")
                    
                    print(f"  解析状态：{state} (已等待 {waited_time}秒)")
                    
                    if state == "done":
                        print(f"  解析完成!")
                        break
                    elif state == "failed":
                        error_message = first_item.get("error_message", "未知错误")
                        raise ValueError(f"PDF 解析失败：{error_message}")
            
            if waited_time >= max_wait_time:
                raise TimeoutError(f"PDF 解析超时 (等待了{max_wait_time}秒)")

            # 步骤 1.4: 获取解析结果
            print(f"  步骤 1.4: 下载解析结果...")
            full_zip_url = extract_results[0].get("full_zip_url")
            if not full_zip_url:
                raise ValueError("未找到解析结果下载链接")
            
            # 下载 ZIP 文件
            zip_response = requests.get(full_zip_url, timeout=60)
            zip_response.raise_for_status()
            
            # 保存到临时 ZIP 文件
            temp_zip_path = UPLOAD_DIR / f"{uuid.uuid4()}.zip"
            with open(temp_zip_path, "wb") as zip_file:
                zip_file.write(zip_response.content)
            
            # 解压 ZIP 文件
            temp_extract_dir = UPLOAD_DIR / f"temp_{uuid.uuid4()}"
            temp_extract_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
                
                # 查找 full.md 文件
                md_content = ""
                for file_info in zip_ref.infolist():
                    filename = file_info.filename
                    if os.path.basename(filename) == 'full.md':
                        # 读取 MD 内容
                        extracted_path = temp_extract_dir / filename
                        with open(extracted_path, 'r', encoding='utf-8') as md_file:
                            md_content = md_file.read()
                        break
            
            # 清理临时文件
            os.remove(temp_zip_path)
            shutil.rmtree(temp_extract_dir)

            if not md_content:
                raise ValueError("MinerU 解析结果为空")

            print(f"  提取到文本长度: {len(md_content)} 字符")

            # 步骤2: 使用 LLM 提取合同信息
            print(f"  步骤2: 调用 LLM 提取合同信息...")
            overview = extract_contract_info_dict(md_content)
            print(f"  信息提取完成")

            # 打印提取的数据，方便调试
            print(f"\n提取的合同数据:")
            print(f"  合同类型: {overview.get('contract_type', '')}")
            print(f"  合同标题: {overview.get('contract_title', '')}")
            print(f"  甲方: {overview.get('party_a', '')}")
            print(f"  乙方: {overview.get('party_b', '')}")
            print(f"  金额: {overview.get('total_amount', '')}")
            print(f"  生效日期: {overview.get('effective_date', '')}")
            print(f"  到期日期: {overview.get('expiry_date', '')}")
            print(f"  关键条款数量: {len(overview.get('key_terms', []))}")
            print()

            # 步骤3: 保存markdown内容供审查使用
            # 生成合同ID（使用文件名的stem作为ID）
            contract_id = file_path.stem
            md_file = UPLOAD_DIR / f"{contract_id}_content.md"

            print(f"  步骤3: 保存合同内容到 {md_file}")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(md_content)

            # 在响应中添加contract_id
            overview["contract_id"] = contract_id

            return ContractOverviewResponse(
                success=True,
                message="合同信息提取成功",
                data=overview
            )

        except requests.exceptions.ConnectionError:
            print(f"  ❌ 无法连接到 MinerU API: {MINERU_BASE_URL}")
            raise HTTPException(
                status_code=503,
                detail=f"无法连接到 MinerU 服务，请确保服务运行在 {MINERU_BASE_URL}"
            )
        except requests.exceptions.Timeout:
            print(f"  ❌ MinerU API 请求超时")
            raise HTTPException(
                status_code=504,
                detail="PDF 解析超时，请稍后重试"
            )
        except ValueError as e:
            print(f"  ❌ 数据处理错误: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"数据处理失败: {str(e)}"
            )
        except Exception as e:
            print(f"  ❌ 提取失败: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"合同信息提取失败: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"合同信息提取错误: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"信息提取失败: {str(e)}")


@app.post("/api/contract/audit")
async def audit_contract(contract_id: str = Form(...)):
    """
    合同专业审查接口

    接收合同ID，从上传记录中获取合同内容，然后调用LLM进行专业审查
    """
    print(f"\n{'='*80}")
    print(f"开始合同专业审查")
    print(f"{'='*80}")
    print(f"合同ID: {contract_id}")

    try:
        # 1. 从上传记录中获取合同的markdown内容
        md_file = UPLOAD_DIR / f"{contract_id}_content.md"

        if not md_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"未找到合同内容文件: {contract_id}"
            )

        # 读取合同markdown内容
        with open(md_file, "r", encoding="utf-8") as f:
            contract_text = f.read()

        print(f"  合同文本长度: {len(contract_text)} 字符")

        # 2. 调用专业审查系统
        print(f"  步骤1: 调用LLM进行专业审查...")

        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser
        from pydantic import BaseModel, Field, ConfigDict
        from typing import List
        import json

        # 导入审查规则和提示词
        from prompts.contract_audit_prompt import (
            PROFESSIONAL_CONTRACT_AUDIT_RULES,
            PROFESSIONAL_SYSTEM_PROMPT,
            PROFESSIONAL_USER_PROMPT
        )

        # 定义数据结构
        class Issue(BaseModel):
            model_config = ConfigDict(populate_by_name=True, extra='allow')
            rule_category: str = Field(description="规则类别")
            issue_type: str = Field(description="问题类型")
            description: str = Field(description="问题详细描述")
            original: str = Field(default="", description="原文中有问题的部分")
            suggestion: str = Field(default="", description="修改建议")
            severity: str = Field(
                description="严重程度: high, medium, low",
                pattern="^(high|medium|low)$"
            )
            legal_risk: str = Field(default="", description="法律风险说明")

        class ModificationMapping(BaseModel):
            model_config = ConfigDict(populate_by_name=True, extra='allow')
            original: str = Field(default="", description="原文片段")
            modified: str = Field(default="", description="修改后的文本")
            reason: str = Field(default="", description="修改原因")
            rule_ref: str = Field(default="", description="规则编号")

        class AuditResult(BaseModel):
            has_issues: bool = Field(description="是否发现问题")
            issues: List[Issue] = Field(description="问题列表", default_factory=list)
            modifications: List[ModificationMapping] = Field(
                description="修改记录",
                default_factory=list
            )
            corrected_text: str = Field(description="修正后的完整文本")
            summary: str = Field(description="审核总结")
            overall_risk_level: str = Field(
                description="整体风险等级",
                pattern="^(high|medium|low|none)$"
            )

        # 创建 LLM
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")

        llm = ChatOpenAI(
            model="Qwen/Qwen3.6-27B",  # 硅基流动模型
            temperature=0.1,
            max_tokens=2000,  # 减少最大输出token数
            timeout=120,  # 增加超时到120秒
            openai_api_key=api_key,
            openai_api_base=base_url
        )

        # 截断合同文本，避免超过模型上下文限制
        # 保留前 4000 个字符（约 1000-1500 tokens）
        MAX_TEXT_LENGTH = 4000
        if len(contract_text) > MAX_TEXT_LENGTH:
            print(f"  合同文本过长 ({len(contract_text)} 字符)，进行截断...")
            contract_text = contract_text[:MAX_TEXT_LENGTH] + "\n\n[... 内容已被截断 ...]"

        # 创建审查链
        audit_prompt = ChatPromptTemplate.from_messages([
            ("system", PROFESSIONAL_SYSTEM_PROMPT),
            ("user", PROFESSIONAL_USER_PROMPT)
        ])

        # 使用 JsonOutputParser 替代 with_structured_output
        # 因为硅基流动模型不支持 JSON 模式
        output_parser = JsonOutputParser()
        audit_chain = audit_prompt | llm | output_parser

        # 执行审查
        try:
            raw_result = audit_chain.invoke({
                "rules": PROFESSIONAL_CONTRACT_AUDIT_RULES,
                "text": contract_text
            })
            print(f"  原始返回结果类型: {type(raw_result)}")
            print(f"  原始返回结果: {raw_result}")

            # 检查是否成功解析
            if raw_result is None:
                print(f"  ⚠️ JSON 解析返回 None，使用默认结果")
                raw_result = {
                    "has_issues": False,
                    "issues": [],
                    "modifications": [],
                    "corrected_text": contract_text,
                    "summary": "LLM 返回内容无法解析为 JSON，建议检查模型输出格式",
                    "overall_risk_level": "low"
                }

            # 将字典结果转换为 AuditResult 对象
            result = AuditResult(**raw_result)

        except Exception as parse_error:
            print(f"  ⚠️ 结果解析失败: {parse_error}")
            print(f"  使用默认的审查结果")
            result = AuditResult(
                has_issues=False,
                issues=[],
                modifications=[],
                corrected_text=contract_text,
                summary=f"审查过程中遇到解析错误: {str(parse_error)}。建议：1) 检查模型是否支持 JSON 输出 2) 尝试使用其他模型 3) 增加提示词中的 JSON 格式要求",
                overall_risk_level="low"
            )

        print(f"  审查完成")
        print(f"  是否发现问题: {result.has_issues}")
        print(f"  问题总数: {len(result.issues)}")
        print(f"  整体风险等级: {result.overall_risk_level}")

        # 3. 转换为响应格式
        issues_data = []
        for issue in result.issues:
            issues_data.append({
                "rule_category": issue.rule_category,
                "issue_type": issue.issue_type,
                "description": issue.description,
                "original": issue.original,
                "suggestion": issue.suggestion,
                "severity": issue.severity,
                "legal_risk": issue.legal_risk
            })

        response_data = {
            "has_issues": result.has_issues,
            "issues": issues_data,
            "summary": result.summary,
            "overall_risk_level": result.overall_risk_level,
            "corrected_text": result.corrected_text
        }

        return {
            "success": True,
            "message": "审查完成",
            "data": response_data
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"  ❌ 审查失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"合同审查失败: {str(e)}"
        )


def _get_mock_contract_overview() -> Dict[str, Any]:
    """获取模拟合同概览数据"""
    return {
        "contract_type": "劳动合同",
        "contract_title": "劳动合同",
        "party_a": "北京某某科技有限公司",
        "party_a_type": "公司",
        "party_a_details": "统一社会信用代码：91110000XXXXXXXXXX，地址：北京市海淀区中关村大街1号",
        "party_b": "张三",
        "party_b_type": "个人",
        "party_b_details": "身份证号：110101199001011234",
        "total_amount": "月工资 ¥5,000",
        "amount_in_words": "人民币伍仟元整",
        "currency": "人民币",
        "effective_date": "2024年1月1日",
        "expiry_date": "2027年12月31日",
        "duration": "三年",
        "signing_date": "2024年1月1日",
        "key_terms": [
            "工资待遇：月工资人民币伍仟元整（¥5,000）",
            "支付方式：每月15日前银行转账",
            "合同期限：2024年1月1日至2027年12月31日",
            "违约责任：甲方未按时支付工资应支付违约金"
        ],
        "special_clauses": ""
    }


# ==================== 启动配置 ====================

if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*60)
    print("文档审核系统 - FastAPI 后端服务")
    print("="*60)
    print(f"上传目录: {UPLOAD_DIR.absolute()}")
    print(f"API密钥状态: {'✓ 已配置' if API_KEY else '✗ 未配置 (将使用测试模式)'}")
    print("="*60 + "\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
