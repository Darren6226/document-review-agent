"""
文档审核系统 - FastAPI 后端服务
支持票据审查和合同审查

使用 Deep Agents 框架实现发票校验
"""

import os
import sys
import json
import uuid
import time
import shutil
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
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
from services.contract_agent import audit_contract_with_agent_sync
from models.validation import ContractAuditReport

# 导入历史记录存储模块
from services.history_store import save_record, load_records

# ==================== 配置 ====================

# 创建必要的目录
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# MinerU 解析结果缓存目录：overview 解析出的 markdown 在此缓存，
# audit 时按 parse_id 复用，避免同一份 PDF 重复调用 MinerU 解析（耗时且耗额度）
PARSED_CACHE_DIR = Path("./parsed")
PARSED_CACHE_DIR.mkdir(exist_ok=True)

# 解析缓存有效期（小时）：超过该时长的缓存文件会被后台任务定期清理
PARSED_CACHE_TTL_HOURS = int(os.getenv("PARSED_CACHE_TTL_HOURS", "24"))
# 后台清理间隔（秒）：默认每小时清理一次
PARSED_CACHE_CLEAN_INTERVAL = int(os.getenv("PARSED_CACHE_CLEAN_INTERVAL", "3600"))


def _cleanup_parsed_cache():
    """清理过期的解析缓存文件（超过 PARSED_CACHE_TTL_HOURS 的 *.md）。

    返回被清理的文件数量，用于日志与后台循环统计。
    """
    if not PARSED_CACHE_DIR.exists():
        return 0
    cutoff = time.time() - PARSED_CACHE_TTL_HOURS * 3600
    removed = 0
    try:
        for f in PARSED_CACHE_DIR.iterdir():
            if f.is_file() and f.suffix == ".md":
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except OSError:
                    continue
    except OSError as e:
        print(f"[warn] 解析缓存清理失败: {e}")
    return removed


async def _parsed_cache_cleanup_loop():
    """后台循环任务：周期性清理过期解析缓存。"""
    import asyncio as _asyncio
    while True:
        try:
            # 启动后立即清理一次，然后按间隔循环
            removed = await _asyncio.to_thread(_cleanup_parsed_cache)
            if removed:
                print(f"[cache] 解析缓存清理：删除 {removed} 个过期文件")
        except Exception as e:
            print(f"[warn] 解析缓存清理异常: {e}")
        await _asyncio.sleep(PARSED_CACHE_CLEAN_INTERVAL)

# API 配置 - 使用硅基流动
API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

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


@app.on_event("startup")
async def _start_parsed_cache_cleanup():
    """应用启动时，启动解析缓存的后台清理任务。"""
    try:
        task = asyncio.create_task(_parsed_cache_cleanup_loop())
        # 保存任务引用，避免被 GC 回收（Python < 3.11 需要持有引用）
        app.state.parsed_cache_cleanup_task = task
        print(f"[cache] 解析缓存后台清理已启动（TTL={PARSED_CACHE_TTL_HOURS}h，间隔={PARSED_CACHE_CLEAN_INTERVAL}s）")
    except Exception as e:
        print(f"[warn] 解析缓存后台清理启动失败: {e}")


# 初始化系统
extraction_system = None
invoice_agent = None

if API_KEY:
    try:
        extraction_system = InvoiceExtractionSystem(
            api_key=API_KEY,
            model_name="Qwen/Qwen3-VL-32B-Instruct"  # 视觉模型
        )
        print("发票识别系统初始化成功")
    except Exception as e:
        print(f"[ERROR] 发票识别系统初始化失败：{e}（/api/invoice/upload 将返回 503）")
else:
    print("[WARN] 未设置 SILICONFLOW_API_KEY 环境变量（/api/invoice/upload 将返回 503）")

# 创建 Deep Agent
# 注意：发票 Agent 内部默认使用阿里云 DashScope（与合同 Agent 一致），
# 由 create_invoice_agent 自行从环境变量 DASHSCOPE_API_KEY/DASHSCOPE_BASE_URL 读取，
# 因此这里**不传 model/api_key/base_url**，避免传入硅基流动格式的模型名导致
# "Model not exist" 错误（参见历史 bug：c7b1bb52-...）。
try:
    invoice_agent = create_invoice_agent(debug=False)
    print("Deep Agent 初始化成功")
except Exception as e:
    print(f"[ERROR] Deep Agent 初始化失败：{e}（/api/invoice/validate 将返回 503）")


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
    file_path: Optional[Path] = None
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
            raise HTTPException(
                status_code=503,
                detail="发票识别系统未初始化：请检查 SILICONFLOW_API_KEY 环境变量是否正确配置"
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
    finally:
        # 清理上传的临时文件（OCR 已完成或异常时）
        if file_path is not None and file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass


@app.post("/api/invoice/validate", response_model=ValidationResponse)
def validate_invoice(request: ValidationRequest):
    """
    执行发票审查（基于 Deep Agents）

    进行完整性、格式、计算和业务规则校验
    """
    try:
        invoice_data = request.invoice_data

        # 检查 Agent 是否初始化
        if not invoice_agent:
            raise HTTPException(
                status_code=503,
                detail="发票审查 Agent 未初始化：请检查 SILICONFLOW_API_KEY 及模型配置是否正确"
            )

        # 使用 Deep Agent 执行校验（同步版本，def 端点在独立线程中运行，直接创建新 event loop）
        print(f"正在审查发票: {request.invoice_id}")
        report = validate_invoice_with_agent_sync(invoice_data, invoice_agent)

        # 转换为字典
        report_data = report.model_dump(exclude_none=False)

        # 保存历史记录
        try:
            save_record({
                "id": str(uuid.uuid4()),
                "type": "票据审查",
                "title": request.invoice_id or "发票",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "已完成",
                "summary": report_data.get("summary", ""),
                "risk_level": report_data.get("overall_status", "PASSED"),
                "detail": report_data,
            })
        except Exception as e:
            print(f"[WARN] 保存发票审查历史失败：{e}")

        return ValidationResponse(
            success=True,
            message="发票审查完成",
            report=report_data
        )

    except Exception as e:
        print(f"审查错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"审查失败: {str(e)}")


# ==================== 合同审查 API ====================

class ContractOverviewResponse(BaseModel):
    """合同概览响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    # 解析标识：overview 阶段缓存了 MinerU 解析出的 markdown，
    # audit 时携带该标识即可复用，避免重复解析
    parse_id: Optional[str] = None


class ContractAuditResponse(BaseModel):
    """合同审核响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


def _get_parsed_markdown(parse_id: str) -> Optional[str]:
    """按 parse_id 读取缓存的 markdown 解析结果。

    Args:
        parse_id: overview 阶段返回的解析标识

    Returns:
        Optional[str]: 缓存的 markdown 文本；不存在或读取失败返回 None
    """
    if not parse_id:
        return None
    cache_path = PARSED_CACHE_DIR / f"{parse_id}.md"
    try:
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [warn] 读取解析缓存失败 {parse_id}: {e}")
    return None


def _save_parsed_markdown(parse_id: str, content: str):
    """把解析出的 markdown 写入缓存，供后续 audit 复用。

    Args:
        parse_id: 解析标识（MinerU batch_id）
        content: markdown 文本
    """
    try:
        cache_path = PARSED_CACHE_DIR / f"{parse_id}.md"
        cache_path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"  [warn] 保存解析缓存失败 {parse_id}: {e}")


def _parse_pdf_to_markdown(file_path: Path, filename: str, content_type: str, parse_id: Optional[str] = None) -> tuple[str, str]:
    """使用 MinerU 解析 PDF 为 markdown（合同 overview 和 audit 端点共用）。

    Args:
        file_path: 已保存的文件路径
        filename: 原始文件名
        content_type: 文件 MIME 类型
        parse_id: 可选，指定的解析标识；不传则由 MinerU 返回 batch_id

    Returns:
        tuple[str, str]: (解析后的 markdown 文本, 解析标识 parse_id)
    """
    import requests
    import time
    import zipfile

    MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "https://mineru.net")
    MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")

    if not MINERU_API_KEY:
        raise ValueError("未配置 MINERU_API_KEY，请在 .env 文件中设置")

    headers = {"Authorization": f"Bearer {MINERU_API_KEY}"}

    # 读取本地文件内容
    with open(file_path, "rb") as f:
        file_content = f.read()

    # 步骤 1: 申请上传链接（精准解析 API v4，先申请后 PUT 到 OSS）
    batch_url = f"{MINERU_BASE_URL}/api/v4/file-urls/batch"
    batch_data = {
        "files": [
            {
                "name": filename,
                "is_ocr": True,
                "data_id": str(uuid.uuid4()),
            }
        ],
        "language": "ch",
    }
    batch_response = requests.post(
        batch_url, headers=headers, json=batch_data, timeout=60
    )
    if batch_response.status_code != 200:
        raise Exception(f"MinerU 申请上传链接失败: {batch_response.text}")

    batch_json = batch_response.json()
    batch_id = batch_json.get("data", {}).get("batch_id")
    file_urls = batch_json.get("data", {}).get("file_urls") or []
    if not batch_id or not file_urls:
        raise Exception("MinerU 未返回 batch_id 或上传链接")

    # 使用外部传入的 parse_id（若提供），否则用 MinerU 返回的 batch_id
    if parse_id:
        batch_id = parse_id

    upload_target = file_urls[0]
    print(f"  获得上传链接: {upload_target}")

    # 步骤 2: 将文件 PUT 到 OSS 上传链接（上传后 MinerU 自动提交解析任务）
    # 注意：预签名 OSS URL 的签名不含自定义 Content-Type，附加该头会导致 SignatureDoesNotMatch
    put_response = requests.put(
        upload_target,
        data=file_content,
        timeout=120,
    )
    if put_response.status_code >= 300:
        raise Exception(
            f"MinerU 文件上传失败: {put_response.status_code} {put_response.text[:200]}"
        )

    print(f"  文件已上传，batch_id={batch_id}")

    # 步骤 3: 轮询批量解析结果
    poll_url = f"{MINERU_BASE_URL}/api/v4/extract-results/batch/{batch_id}"
    max_wait = 240
    start_time = time.time()

    while True:
        if time.time() - start_time > max_wait:
            raise Exception("MinerU 解析超时")

        poll_response = requests.get(poll_url, headers=headers, timeout=30)
        if poll_response.status_code != 200:
            raise Exception(f"MinerU 状态查询失败: {poll_response.text}")

        poll_result = poll_response.json()
        results = poll_result.get("data", {}).get("extract_result") or []
        if not results:
            print("  解析任务尚未就绪，继续等待...")
            time.sleep(3)
            continue

        item = results[0]
        state = item.get("state")
        zip_url = item.get("full_zip_url")

        if state == "done" and zip_url:
            print("  解析完成，下载结果...")
            break
        elif state == "failed":
            raise Exception(f"MinerU 解析失败: {item.get('err_msg', '')}")
        else:
            print(f"  状态: {state}，继续等待...")
            time.sleep(3)

    # 下载并解压结果
    zip_response = requests.get(zip_url, timeout=60)
    if zip_response.status_code != 200:
        raise Exception(f"下载结果失败: {zip_response.status_code}")

    zip_path = UPLOAD_DIR / f"{batch_id}.zip"
    with open(zip_path, "wb") as f:
        f.write(zip_response.content)

    extract_dir = UPLOAD_DIR / batch_id
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    md_files = list(extract_dir.rglob("*.md"))
    if not md_files:
        raise Exception("未找到解析结果文件")

    md_content = md_files[0].read_text(encoding="utf-8")
    print(f"  解析内容长度: {len(md_content)} 字符")

    # 清理临时文件
    try:
        zip_path.unlink()
        shutil.rmtree(extract_dir)
    except Exception:
        pass

    # 缓存解析结果，供 audit 复用，避免重复解析
    _save_parsed_markdown(batch_id, md_content)

    return md_content, batch_id


@app.post("/api/contract/overview", response_model=ContractOverviewResponse)
async def get_contract_overview(file: UploadFile = File(...)):
    """
    上传合同PDF/图片并提取概览信息

    提取内容：甲方、乙方、合同金额、日期等关键信息
    支持格式: PDF
    """
    file_path: Optional[Path] = None
    try:
        # 验证文件类型（仅支持 PDF）
        if file.content_type != 'application/pdf':
            raise HTTPException(status_code=400, detail="不支持的文件类型，仅支持 PDF 格式的合同文件")

        # 验证文件大小 (20MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过20MB限制")

        # 生成唯一文件名
        unique_filename = f"{uuid.uuid4()}.pdf"
        file_path = UPLOAD_DIR / unique_filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"正在提取合同信息: {file_path}")

        try:
            # 步骤 1: 使用 MinerU 解析 PDF（异步包装避免阻塞事件循环）
            # 解析结果会写入 PARSED_CACHE_DIR 缓存，parse_id 返回给前端供 audit 复用
            print(f"  步骤 1: 调用 MinerU 解析 PDF...")
            md_content, parse_id = await asyncio.to_thread(
                _parse_pdf_to_markdown, file_path, file.filename, file.content_type
            )

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
                data=contract_info,
                parse_id=parse_id
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
    finally:
        # 清理上传的临时文件
        if file_path is not None:
            try:
                file_path.unlink()
            except Exception:
                pass


@app.post("/api/contract/audit", response_model=ContractAuditResponse)
def audit_contract(
    file: UploadFile = File(...),
    rules: Optional[str] = Form(None),
    parse_id: Optional[str] = Form(None)
):
    """
    上传合同 PDF 并进行专业审核

    审核流程（Harness Engineering v2）：
    1. MinerU 解析 PDF → markdown（若携带 parse_id 且缓存命中，则跳过重新解析）
    2. 确定性管线：金额/日期/条款引用/甲乙方名称校验（零 LLM）
    3. 合同类型识别：轻量 LLM 调用
    4. Agent 审核：VFS + Skill + 工具 + Planner 自规划
    5. 双向验证回路：查幻觉 + 查遗漏

    支持格式: PDF

    实现说明：使用同步端点（def 而非 async def），FastAPI 自动在 threadpool 中执行。
    这样线程内 asyncio.new_event_loop() 是干净的（无父 loop 引用），
    避免与 LangGraph 异步资源冲突导致 ainvoke 永久挂起。

    Args:
        file: 合同 PDF 文件
        rules: 可选，JSON 格式的规则ID列表（如 '["1","2","3"]'），为空则使用全部规则
        parse_id: 可选，overview 阶段返回的解析标识。若命中缓存则复用已解析的 markdown，
            避免同一份 PDF 重复调用 MinerU；未提供或缓存失效时回退为重新解析
    """
    file_path: Optional[Path] = None
    try:
        # 验证文件类型（仅支持 PDF）
        if file.content_type != 'application/pdf':
            raise HTTPException(status_code=400, detail="不支持的文件类型，仅支持 PDF 格式的合同文件")

        # 验证文件大小 (20MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过 20MB 限制")

        # 生成唯一文件名
        unique_filename = f"{uuid.uuid4()}.pdf"
        file_path = UPLOAD_DIR / unique_filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"正在审核合同: {file_path}")

        try:
            # 步骤 1: 获取合同 markdown
            # 优先复用 overview 阶段缓存的解析结果（parse_id 命中缓存则跳过 MinerU 重复解析）
            cached_md = _get_parsed_markdown(parse_id) if parse_id else None
            if cached_md is not None:
                print(f"  步骤 1: 命中解析缓存（parse_id={parse_id}），跳过 MinerU 解析")
                md_content = cached_md
            else:
                # 未命中缓存则调用 MinerU 解析 PDF（同步阻塞调用，requests 库）
                print(f"  步骤 1: 调用 MinerU 解析 PDF...")
                md_content, _parse_id = _parse_pdf_to_markdown(file_path, file.filename, file.content_type)
                print(f"  步骤 1: 解析完成（parse_id={_parse_id}）")

        except Exception as e:
            print(f"MinerU 解析失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"合同解析失败: {str(e)}"
            )

        try:
            # 步骤 2-5: 确定性管线 + 类型识别 + Agent 审核 + 验证回路
            # 函数内部使用 asyncio.new_event_loop + run_until_complete，自带 180s 超时保护
            print(f"  步骤 2-5: 合同审核（确定性管线 + Agent + 验证回路）...")

            # 解析规则列表
            selected_rules = None
            if rules:
                try:
                    selected_rules = json.loads(rules)
                    print(f"  使用自定义规则: {selected_rules}")
                except json.JSONDecodeError:
                    print(f"  [WARN] 规则参数解析失败，使用全部规则")

            report: ContractAuditReport = audit_contract_with_agent_sync(md_content, selected_rules=selected_rules)

            print(f"  审核完成: {report.overall_risk_level} - {report.summary}（status={report.status}）")

            # 保存历史记录
            try:
                save_record({
                    "id": str(uuid.uuid4()),
                    "type": "合同审查",
                "title": file.filename or "合同文件",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                # status 反映真实审核状态：success 记为「已完成」，超时/异常记为「未完成」
                # 供前端历史列表区分展示，避免把不可信的超时记录混入「已完成」列表
                "status": "已完成" if report.status == "success" else "未完成",
                "summary": report.summary,
                # 分析未成功时 risk_level 标记 unknown，避免历史列表误导为「无风险」
                "risk_level": report.overall_risk_level if report.status == "success" else "unknown",
                "detail": report.model_dump(),
                })
            except Exception as e:
                print(f"[WARN] 保存合同审查历史失败：{e}")

            # 审核未成功完成（超时/异常）时，success 必须反映真实状态，
            # 不能返回 True 让前端误判为「审核通过」。前端据此区分展示
            # 「审核未完成，请重试」，避免把不可信结论混入「已完成」列表。
            audit_ok = report.status == "success"

            return ContractAuditResponse(
                success=audit_ok,
                message=f"合同审核完成：{report.summary}",
                data=report.model_dump()
            )

        except Exception as e:
            print(f"合同审核失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"合同审核失败: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"合同处理错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"合同处理失败: {str(e)}")
    finally:
        # 清理上传的临时文件
        if file_path is not None:
            try:
                file_path.unlink()
            except Exception:
                pass


# ==================== 历史记录 API ====================

class HistoryResponse(BaseModel):
    """历史记录响应"""
    success: bool
    message: str
    data: Optional[List[Dict[str, Any]]] = None


@app.get("/api/history", response_model=HistoryResponse)
async def get_history():
    """
    获取全部历史记录（最新的排在前面）

    每条记录包含：id, type, title, date, status, summary, risk_level 等字段。
    """
    try:
        records = load_records()
        return HistoryResponse(
            success=True,
            message=f"获取历史记录成功，共 {len(records)} 条",
            data=records
        )
    except Exception as e:
        print(f"获取历史记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
