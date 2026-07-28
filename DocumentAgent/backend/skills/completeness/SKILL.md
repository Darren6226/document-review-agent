---
name: completeness
description: 发票完整性校验 - 验证必填字段和建议字段是否完整
---

# 发票完整性校验 Skill

## 职责

验证发票数据的完整性，检查必填字段和建议字段是否存在。

## 校验逻辑

### 1. 判断发票类型

根据 `invoice_type` 字段判断：
- 包含"专用"二字 → 增值税专用发票（13个必填字段）
- 其他 → 普通发票（14个必填字段，含校验码）

### 2. 检查必填字段

**专用发票必填字段（13个）：**
- `invoice_type` - 发票类型
- `invoice_code` - 发票代码（10位数字）
- `invoice_number` - 发票号码（8位数字）
- `issue_date` - 开票日期
- `purchaser_name` - 购买方名称
- `purchaser_tax_id` - 购买方纳税人识别号
- `seller_name` - 销售方名称
- `seller_tax_id` - 销售方纳税人识别号
- `total_amount` - 合计金额
- `total_tax` - 合计税额
- `total_amount_with_tax` - 价税合计
- `payee` - 收款人
- `drawer` - 开票人

**普通发票额外必填：**
- `check_code` - 校验码

### 3. 检查建议字段

以下字段缺失时发出 WARNING（非 ERROR）：
- `purchaser_address` - 购买方地址电话
- `purchaser_bank` - 购买方开户行及账号
- `seller_address` - 销售方地址电话
- `seller_bank` - 销售方开户行及账号
- `line_items` - 商品明细
- `checker` - 复核人

### 4. 特殊处理

金额字段（`total_amount`, `total_tax`, `total_amount_with_tax`）允许值为 0，但不允许为 None 或空字符串。

## 输出格式

```python
{
    "agent_name": "完整性校验Agent",
    "level": "error|warning|info",
    "category": "完整性校验",
    "message": "必填字段 [字段名] 缺失",
    "field": "字段名",
    "expected": "期望情况（如：字段存在）",
    "actual": "实际情况（如：字段缺失）",
    "suggestion": "建议内容"
}
```

## 级别定义

- **ERROR**: 必填字段缺失，发票不可用
- **WARNING**: 建议字段缺失，不影响发票有效性
- **INFO**: 所有字段完整
