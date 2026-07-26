# 完整性校验规则

## 发票类型判断

| invoice_type 包含 | 发票类型 | 必填字段数 |
|------------------|----------|-----------|
| "专用" | 增值税专用发票 | 13 |
| 其他 | 普通发票 | 14（含校验码） |

## 专用发票必填字段（13个）

| 字段名 | 中文名称 | 备注 |
|--------|----------|------|
| invoice_type | 发票类型 | |
| invoice_code | 发票代码 | 10位数字 |
| invoice_number | 发票号码 | 8位数字 |
| issue_date | 开票日期 | YYYY-MM-DD |
| purchaser_name | 购买方名称 | |
| purchaser_tax_id | 购买方纳税人识别号 | |
| seller_name | 销售方名称 | |
| seller_tax_id | 销售方纳税人识别号 | |
| total_amount | 合计金额 | 允许为0 |
| total_tax | 合计税额 | 允许为0 |
| total_amount_with_tax | 价税合计 | 允许为0 |
| payee | 收款人 | |
| drawer | 开票人 | |

## 普通发票额外必填

| 字段名 | 中文名称 |
|--------|----------|
| check_code | 校验码 |

## 建议字段（缺失时 WARNING）

| 字段名 | 中文名称 |
|--------|----------|
| purchaser_address | 购买方地址电话 |
| purchaser_bank | 购买方开户行及账号 |
| seller_address | 销售方地址电话 |
| seller_bank | 销售方开户行及账号 |
| line_items | 商品明细 |
| checker | 复核人 |
