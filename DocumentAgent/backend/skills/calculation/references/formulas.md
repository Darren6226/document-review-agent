# 计算校验公式

## 核心公式

### 1. 价税合计
```
价税合计 = 合计金额 + 合计税额
total_amount_with_tax = total_amount + total_tax
```
- 容差：0.02元

### 2. 行项目金额合计
```
合计金额 = SUM(行项目.amount)
total_amount = SUM(line_items[].amount)
```
- 容差：0.02元

### 3. 行项目税额合计
```
合计税额 = SUM(行项目.tax_amount)
total_tax = SUM(line_items[].tax_amount)
```
- 容差：0.02元

### 4. 单项税额
```
税额 = 金额 × 税率
tax_amount = amount × tax_rate
```
- 容差：0.02元

