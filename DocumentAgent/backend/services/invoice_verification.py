"""
中国增值税发票智能识别与提取系统
基于真实发票数据设计

支持:
- 增值税专用发票
- 增值税普通发票
- 电子发票

使用: pip install pydantic langchain langchain_openai
"""

import os
import re
import json
import base64
from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI


# ==================== 数据模型 ====================

class LineItem(BaseModel):
    """发票行项目"""
    row: str = Field(..., description="行号")
    name: str = Field(..., description="商品或服务名称")
    specification: Optional[str] = Field(None, description="规格型号")
    unit: Optional[str] = Field(None, description="单位")
    quantity: Optional[float] = Field(None, description="数量")
    unit_price: Optional[float] = Field(None, description="单价")
    amount: float = Field(..., description="金额(不含税)")
    tax_rate: float = Field(..., description="税率(小数,如0.06表示6%)")
    tax_amount: float = Field(..., description="税额")

    @field_validator('row', mode='before')
    @classmethod
    def convert_row_to_string(cls, v):
        """自动将行号转换为字符串 - 兼容模型返回整数的情况"""
        if v is None:
            return v
        return str(v)


class Invoice(BaseModel):
    """中国增值税发票完整模型"""

    # ===== 基本信息 =====
    invoice_type: str = Field(..., description="发票类型(如:增值税专用发票)")
    province: Optional[str] = Field(None, description="省份")
    invoice_code: str = Field(..., description="发票代码(10位数字)")
    invoice_number: str = Field(..., description="发票号码(8位数字)")
    issue_date: str = Field(..., description="开票日期(YYYY-MM-DD)")
    check_code: Optional[str] = Field(None, description="校验码(普通发票有,专用发票无)")

    # ===== 购买方信息 =====
    purchaser_name: str = Field(..., description="购买方名称")
    purchaser_tax_id: str = Field(..., description="购买方纳税人识别号")
    purchaser_address: Optional[str] = Field(None, description="购买方地址电话")
    purchaser_bank: Optional[str] = Field(None, description="购买方开户行及账号")

    # ===== 销售方信息 =====
    seller_name: str = Field(..., description="销售方名称")
    seller_tax_id: str = Field(..., description="销售方纳税人识别号")
    seller_address: Optional[str] = Field(None, description="销售方地址电话")
    seller_bank: Optional[str] = Field(None, description="销售方开户行及账号")

    # ===== 金额信息 =====
    total_amount: float = Field(..., description="合计金额(不含税)")
    total_tax: float = Field(..., description="合计税额")
    total_amount_with_tax: float = Field(..., description="价税合计")
    amount_in_words: Optional[str] = Field(None, description="价税合计(大写)")

    # ===== 商品明细 =====
    line_items: List[LineItem] = Field(default_factory=list, description="行项目明细")

    # ===== 其他信息 =====
    payee: Optional[str] = Field(None, description="收款人")
    checker: Optional[str] = Field(None, description="复核人")
    drawer: Optional[str] = Field(None, description="开票人")
    remarks: Optional[str] = Field(None, description="备注")

    @field_validator('issue_date')
    @classmethod
    def validate_date(cls, v):
        """标准化日期格式"""
        if not v:
            return v

        # 处理中文日期: 2016年06月02日 -> 2016-06-02
        match = re.search(r'(\d{4})年(\d{2})月(\d{2})日', v)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        # 处理其他格式
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
            try:
                dt = datetime.strptime(str(v), fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return v

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.model_dump(mode='python')

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return self.model_dump_json(indent=indent, exclude_none=False)


# ==================== OCR数据标准化 ====================

def normalize_ocr_data(ocr_data: dict) -> dict:
    """
    将OCR识别的发票数据标准化为统一格式

    支持百度OCR、腾讯OCR等格式

    Args:
        ocr_data: OCR识别的原始数据

    Returns:
        标准化的发票数据字典
    """
    # 提取基本信息
    invoice_type = ocr_data.get('InvoiceTypeOrg') or ocr_data.get('InvoiceType', '')

    # 处理日期
    date_str = ocr_data.get('InvoiceDate', '')
    date_match = re.search(r'(\d{4})年(\d{2})月(\d{2})日', date_str)
    issue_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else date_str

    # 提取商品明细
    line_items = []
    commodity_names = ocr_data.get('CommodityName', [])
    commodity_amounts = ocr_data.get('CommodityAmount', [])
    commodity_tax_rates = ocr_data.get('CommodityTaxRate', [])
    commodity_taxes = ocr_data.get('CommodityTax', [])

    for i in range(len(commodity_names)):
        # 提取税率: "6%" -> 0.06
        tax_rate_str = commodity_tax_rates[i]['word'] if i < len(commodity_tax_rates) else '0%'
        tax_rate = float(tax_rate_str.replace('%', '')) / 100 if '%' in tax_rate_str else 0

        line_items.append({
            'row': str(i + 1),
            'name': commodity_names[i]['word'],
            'amount': float(commodity_amounts[i]['word']) if i < len(commodity_amounts) else 0,
            'tax_rate': tax_rate,
            'tax_amount': float(commodity_taxes[i]['word']) if i < len(commodity_taxes) else 0
        })

    # 构建标准化数据
    normalized = {
        'invoice_type': invoice_type,
        'province': ocr_data.get('Province', ''),
        'invoice_code': ocr_data.get('InvoiceCode', ''),
        'invoice_number': ocr_data.get('InvoiceNum', ''),
        'issue_date': issue_date,
        'check_code': ocr_data.get('CheckCode', ''),

        'purchaser_name': ocr_data.get('PurchaserName', ''),
        'purchaser_tax_id': ocr_data.get('PurchaserRegisterNum', ''),
        'purchaser_address': ocr_data.get('PurchaserAddress', ''),
        'purchaser_bank': ocr_data.get('PurchaserBank', ''),

        'seller_name': ocr_data.get('SellerName', ''),
        'seller_tax_id': ocr_data.get('SellerRegisterNum', ''),
        'seller_address': ocr_data.get('SellerAddress', ''),
        'seller_bank': ocr_data.get('SellerBank', ''),

        'total_amount': float(ocr_data.get('TotalAmount', 0)),
        'total_tax': float(ocr_data.get('TotalTax', 0)),
        'total_amount_with_tax': float(ocr_data.get('AmountInFiguers', 0)),
        'amount_in_words': ocr_data.get('AmountInWords', ''),

        'line_items': line_items,

        'payee': ocr_data.get('Payee', ''),
        'checker': ocr_data.get('Checker', ''),
        'drawer': ocr_data.get('NoteDrawer', ''),
        'remarks': ocr_data.get('Remarks', '')
    }

    return normalized


# ==================== 发票提取系统 ====================

class InvoiceExtractionSystem:
    """发票信息提取系统"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
       model_name: str = "Qwen/Qwen3-VL-32B-Instruct"
    ):
        """
        初始化提取系统

        Args:
            api_key: API密钥 (默认从 OPENAI_API_KEY 或 DASHSCOPE_API_KEY 环境变量读取)
            base_url: API 地址 (默认从 OPENAI_BASE_URL 环境变量读取，其次使用硅基流动地址)
           model_name: 模型名称
        """
        # 从环境变量获取配置
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        
        if not self.api_key:
            raise ValueError("请设置 OPENAI_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        
        self.llm = ChatOpenAI(
           model=model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.1,
        )

        self.extraction_prompt = self._build_extraction_prompt()

    def _build_extraction_prompt(self) -> str:
        """构建提取提示词"""
        return """你是专业的中国发票识别助手。请仔细识别图片中的增值税发票,提取所有信息并以JSON格式返回。

**必须提取的字段:**
1. invoice_type: 发票类型(如:上海增值税专用发票)
2. invoice_code: 发票代码(10位数字)
3. invoice_number: 发票号码(8位数字)
4. issue_date: 开票日期(YYYY年MM月DD日格式)
5. purchaser_name: 购买方名称
6. purchaser_tax_id: 购买方纳税人识别号
7. purchaser_address: 购买方地址电话
8. purchaser_bank: 购买方开户行及账号
9. seller_name: 销售方名称
10. seller_tax_id: 销售方纳税人识别号
11. seller_address: 销售方地址电话
12. seller_bank: 销售方开户行及账号
13. total_amount: 合计金额(纯数字)
14. total_tax: 合计税额(纯数字)
15. total_amount_with_tax: 价税合计(纯数字)
16. amount_in_words: 价税合计大写
17. line_items: 商品明细数组,每项包含:
    - row: 行号
    - name: 商品名称
    - amount: 金额
    - tax_rate: 税率(小数,如6%写成0.06)
    - tax_amount: 税额
18. payee: 收款人
19. checker: 复核人
20. drawer: 开票人

**重要规则:**
1. 所有金额必须是纯数字,不要包含¥、元等符号
2. 税率用小数表示(6%写成0.06)
3. 日期保持原格式(2016年06月02日)
4. 如果字段无法识别,使用null
5. 专用发票没有校验码,check_code留空

请直接返回JSON,不要其他说明。示例格式:
{
  "invoice_type": "上海增值税专用发票",
  "invoice_code": "3100153130",
  "invoice_number": "14641426",
  "issue_date": "2016年06月02日",
  "purchaser_name": "百度时代网络技术(北京)有限公司",
  "purchaser_tax_id": "110108787751579",
  ...
}
"""

    def extract_from_image(self, image_path: str) -> Invoice:
        """
        从图片提取发票信息

        Args:
            image_path: 图片路径

        Returns:
            Invoice对象
        """
        # 读取图片
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        # 构建消息
        message = HumanMessage(content=[
            {"type": "text", "text": self.extraction_prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
            }
        ])

        # 调用模型
        print("正在调用 AI 模型识别发票...")
        response = self.llm.invoke([message])

        # 提取JSON
        raw_json = self._extract_json(response.content)

        # 验证并转换
        invoice = Invoice.model_validate(raw_json)

        print("[OK] 发票信息提取完成")
        return invoice

    def _extract_json(self, text: str) -> dict:
        """从响应中提取JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except:
            pass

        # 提取JSON代码块
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # 提取JSON对象
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass

        raise ValueError(f"无法从响应中提取JSON: {text[:200]}...")


# ==================== 使用示例 ====================

def main():
    """使用示例"""

    # 初始化系统（使用视觉模型识别发票图片）
    system = InvoiceExtractionSystem(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        model_name="Qwen/Qwen3-VL-32B-Instruct"
    )

    # 从图片提取
    invoice = system.extract_from_image("./invoice.png")

    # 显示结果
    print("\n" + "="*60)
    print("发票信息提取结果")
    print("="*60)
    print(f"发票类型: {invoice.invoice_type}")
    print(f"发票代码: {invoice.invoice_code}")
    print(f"发票号码: {invoice.invoice_number}")
    print(f"开票日期: {invoice.issue_date}")
    print(f"购买方: {invoice.purchaser_name}")
    print(f"销售方: {invoice.seller_name}")
    print(f"价税合计: ¥{invoice.total_amount_with_tax:,.2f}")
    print(f"商品明细: {len(invoice.line_items)} 项")

    # 保存JSON
    with open("invoice_extracted.json", "w", encoding="utf-8") as f:
        f.write(invoice.to_json())

    print(f"\\n[OK] 详细数据已保存到 invoice_extracted.json")


if __name__ == "__main__":
    main()
