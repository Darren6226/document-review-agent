"""
文档审核系统 - FastAPI 后端服务
支持票据审查和合同审查

使用 Deep Agents 框架实现发票校验
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

# 导入业务服务模块
from services.invoice_verification import InvoiceExtractionSystem, Invoice
from services.invoice_agent import create_invoice_agent, validate_invoice_with_agent_sync

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
    description="支持票据和合同的OCR识别与智能审查（基于 Deep Agents）",
    version="2.0.0"
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
invoice_agent = None

if API_KEY:
    try:
        extraction_system = InvoiceExtractionSystem(
            api_key=API_KEY,
            model_name="Qwen/Qwen3.6-27B"  # 硅基流动模型
        )
        print("发票识别系统初始化成功")
    except Exception as e:
        print(f"系统初始化警告：{e}")
else:
    print("未设置 OPENAI_API_KEY 环境变量")

# 创建 Deep Agent
try:
    invoice_agent = create_invoice_agent(
        model="openai:gpt-4o",  # 可根据需要切换模型
        debug=False
    )
    print("Deep Agent 初始化成功")
except Exception as e:
    print(f"Deep Agent 初始化警告：{e}")


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "文档审核系统 API",
        "version": "2.0.0",
        "status": "running",
        "framework": "Deep Agents",
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
        "invoice_agent": invoice_agent is not None,
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
    执行发票审查（基于 Deep Agents）

    进行完整性、格式、计算和业务规则校验
    """
    try:
        invoice_data = request.invoice_data

        # 检查 Agent 是否初始化
        if not invoice_agent:
            # 返回模拟审查结果
            return ValidationResponse(
                success=True,
                message="审查完成(测试模式)",
                report=_get_mock_validation_report(invoice_data)
            )

        # 使用 Deep Agent 执行校验
        print(f"正在审查发票: {request.invoice_id}")
        report = validate_invoice_with_agent_sync(invoice_data, invoice_agent)

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

            MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "https://mineru.net")
            MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")

            # 检查 API Key 是否配置
            if not MINERU_API_KEY:
                raise ValueError("未配置 MINERU_API_KEY，请在.env 文件中设置")

            # 构建 API URL
            batch_url = f"{MINERU_BASE_URL}/api/v4/file-urls/batch"

            # 读取文件内容
            with open(file_path, "rb") as f:
                file_content = f.read()

            # 上传文件到 MinerU
            headers = {
                "Authorization": f"Bearer {MINERU_API_KEY}"
            }

            # 使用 MinerU 的文件上传接口
            upload_url = f"{MINERU_BASE_URL}/api/v4/file/upload"
            files = {
                "file": (file.filename, file_content, file.content_type)
            }

            upload_response = requests.post(
                upload_url,
                headers=headers,
                files=files,
                timeout=60
            )

            if upload_response.status_code != 200:
                raise Exception(f"MinerU 上传失败: {upload_response.text}")

            upload_result = upload_response.json()
            file_url = upload_result.get("data", {}).get("file_url")

            if not file_url:
                raise Exception("MinerU 未返回文件 URL")

            print(f"  文件上传成功: {file_url}")

            # 提交解析任务
            task_url = f"{MINERU_BASE_URL}/api/v4/extract/task"
            task_data = {
                "file_url": file_url,
                "is_ocr": True,
                "enable_formula": False,
                "enable_table": True,
                "layout_model": "doclayout_yolo",
                "language": "ch"
            }

            task_response = requests.post(
                task_url,
                headers=headers,
                json=task_data,
                timeout=30
            )

            if task_response.status_code != 200:
                raise Exception(f"MinerU 任务提交失败: {task_response.text}")

            task_result = task_response.json()
            task_id = task_result.get("data", {}).get("task_id")

            if not task_id:
                raise Exception("MinerU 未返回任务 ID")

            print(f"  任务已提交: {task_id}")

            # 轮询任务状态
            poll_url = f"{MINERU_BASE_URL}/api/v4/extract/task/{task_id}"
            max_wait = 120  # 最多等待 2 分钟
            start_time = time.time()

            while True:
                if time.time() - start_time > max_wait:
                    raise Exception("MinerU 解析超时")

                poll_response = requests.get(
                    poll_url,
                    headers=headers,
                    timeout=30
                )

                if poll_response.status_code != 200:
                    raise Exception(f"MinerU 状态查询失败: {poll_response.text}")

                poll_result = poll_response.json()
                status = poll_result.get("data", {}).get("status")
                zip_url = poll_result.get("data", {}).get("full_zip_url")

                if status == "completed" and zip_url:
                    print(f"  解析完成，下载结果...")
                    break
                elif status == "failed":
                    raise Exception("MinerU 解析失败")
                else:
                    print(f"  状态: {status}，继续等待...")
                    time.sleep(2)

            # 下载并解析结果
            zip_response = requests.get(zip_url, timeout=60)
            if zip_response.status_code != 200:
                raise Exception(f"下载结果失败: {zip_response.status_code}")

            # 保存并解压 ZIP
            zip_path = UPLOAD_DIR / f"{task_id}.zip"
            with open(zip_path, "wb") as f:
                f.write(zip_response.content)

            extract_dir = UPLOAD_DIR / task_id
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # 查找 markdown 文件
            md_files = list(extract_dir.rglob("*.md"))
            if not md_files:
                raise Exception("未找到解析结果文件")

            # 读取第一个 markdown 文件
            md_content = md_files[0].read_text(encoding="utf-8")
            print(f"  解析内容长度: {len(md_content)} 字符")

            # 清理临时文件
            try:
                zip_path.unlink()
                shutil.rmtree(extract_dir)
            except:
                pass

        except Exception as e:
            print(f"MinerU 解析失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"合同解析失败: {str(e)}"
            )

        try:
            # 步骤 2: 使用 extract_contract_info_dict 提取信息
            print(f"  步骤 2: 提取合同信息...")
            contract_info = extract_contract_info_dict(md_content)
            print(f"  提取完成: {contract_info}")

            return ContractOverviewResponse(
                success=True,
                message="合同信息提取成功",
                data=contract_info
            )

        except Exception as e:
            print(f"合同信息提取失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"合同信息提取失败: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"合同处理错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"合同处理失败: {str(e)}")


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
