---
name: calculation
description: 发票计算校验 - 验证金额、税额、价税合计计算是否正确
---

# 发票计算校验 Skill

## 职责

验证发票的金额计算是否正确，包括总价校验和行项目明细校验。

> 职责边界：本 Skill 仅做算术勾稽（金额/税额/价税合计的加减与单项税额）。**税率合规性、金额范围合理性由 `business` Skill 负责**，避免重复校验。

## 前置依赖与降级

- 本 Skill 依赖 `amount / tax / total_amount / total_amount_with_tax / tax_rate / line_items` 等字段**存在且为数字**。
- 若某字段缺失或非数字（应由 `completeness` / `format` 判 ERROR），**跳过对应勾稽项**，仅输出一条 INFO："因前置字段缺失或格式异常，未执行[具体项]计算校验"，**不得重复报 ERROR/WARNING**。
- 目的：避免与 `completeness` / `format` 产生重复告警。

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
