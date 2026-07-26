---
name: calculation
description: 发票计算校验 - 验证金额、税额、价税合计计算是否正确
---

# 发票计算校验 Skill

## 职责

验证发票的金额计算是否正确，包括总价校验和行项目明细校验。

## 校验规则

### 1. 价税合计校验

**公式**: `合计金额 + 合计税额 = 价税合计`

```python
calculated_total = round(total_amount + total_tax, 2)
diff = abs(calculated_total - total_amount_with_tax)
```

- **容差**: 0.02元（2分钱）
- **级别**: ERROR（超过容差）
- **提示**: "价税合计计算不正确"

### 2. 行项目金额合计校验

**公式**: `SUM(行项目.amount) = total_amount`

```python
items_total_amount = sum(item['amount'] for item in line_items)
diff = abs(items_total_amount - total_amount)
```

- **容差**: 0.02元
- **级别**: WARNING（超过容差）
- **提示**: "行项目金额合计与发票总金额不一致"

### 3. 行项目税额合计校验

**公式**: `SUM(行项目.tax_amount) = total_tax`

```python
items_total_tax = sum(item['tax_amount'] for item in line_items)
diff = abs(items_total_tax - total_tax)
```

- **容差**: 0.02元
- **级别**: WARNING（超过容差）

### 4. 单项税额校验

**公式**: `金额 × 税率 = 税额`

```python
expected_tax = round(amount * tax_rate, 2)
diff = abs(expected_tax - tax_amount)
```

- **容差**: 0.02元
- **级别**: ERROR（超过容差）
- **提示**: "税额计算错误，正确税额应为 ¥{expected_tax}"

### 5. 金额合理性校验

- 含税金额不能为负数 → ERROR
- 含税金额超过1000万 → WARNING（异常大额）

## 中国增值税标准税率

```python
VALID_TAX_RATES = [0.00, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13]
```

- 税率不在标准税率列表中 → WARNING

## 输出格式

```python
{
    "agent_name": "计算校验Agent",
    "level": "error|warning|info",
    "category": "计算校验",
    "message": "校验结果描述",
    "field": "字段名",
    "expected": "期望值",
    "actual": "实际值",
    "suggestion": "修正建议"
}
```
