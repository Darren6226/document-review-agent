---
name: business
description: 发票业务规则校验 - 验证税率、日期、发票类型等业务逻辑
---

# 发票业务规则校验 Skill

## 职责

验证发票的业务逻辑规则，包括税率合规性、发票类型与字段匹配、金额合理性等。

## 前置依赖与降级

- 本 Skill 依赖 `tax_rate / invoice_type / purchaser_tax_id / seller_tax_id / total_amount_with_tax` 等字段**存在且格式正确**。
- 若前置字段缺失（应由 `completeness` 判 ERROR），**跳过对应业务项**，仅输出一条 INFO："因前置字段缺失，未执行[具体项]业务校验"，**不得重复报 ERROR**。
- 目的：避免与 `completeness` 产生重复告警；仅当字段存在时才做业务判断。

## 校验规则

### 1. 税率合规性校验

**中国增值税标准税率**：
```python
VALID_TAX_RATES = [0.00, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13]
```

- 逐项检查 `line_items` 中的 `tax_rate`
- 找到最接近的标准税率，计算差值
- 差值 > 0.001 → WARNING
- **提示**: "中国增值税标准税率为: 0%, 1%, 3%, 5%, 6%, 9%, 13%"

### 2. 发票类型与字段匹配校验

**职责边界**：字段必填性（如 `purchaser_tax_id`、`payee`、`drawer` 是否存在）由 `completeness` Skill 负责，本 Skill **不再重复判定**。

**业务层面的类型匹配**：
- 当 `invoice_type` 含"专用"时，若 `purchaser_tax_id` 与 `seller_tax_id` 相同（买卖双方为同一主体）→ WARNING（虚开发票高风险）

**判断逻辑**：
```python
is_special = '专用' in invoice_type
same_party = is_special and purchaser_tax_id == seller_tax_id
```

### 3. 金额合理性校验

- 非红字发票的含税金额为负数 → ERROR
- 红字发票（退票/折让，`invoice_type` 含"红"或 `is_red_letter=True`）金额为负属正常，需配合《红字增值税专用发票信息表》，不在此判错
- 含税金额超过1000万 → WARNING（异常大额，需人工复核）

### 4. 深度业务校验（由 Agent 推理）

除上述结构化规则外，Agent 应基于常识与领域知识，对以下维度做**自由推理**（无需独立工具，直接体现在 `message` 中）：
- 购买方与销售方是否疑似同一主体（与第 2 节互补：此处关注名称/地址高度相似）
- 商品或服务描述是否清晰合理（如"办公用品"无明细）
- 单价、数量、金额之间是否合理匹配
- 是否存在明显的数据异常（如整数金额扎堆、税额凑整）

> 说明：本 Skill 运行于 Deep Agent 内部，Agent 本身即具备 LLM 推理能力，因此无需"配置 LLM"，上述维度由 Agent 直接判断。

## 输出格式

```python
{
    "agent_name": "业务规则校验Agent",
    "level": "error|warning|info",
    "category": "业务规则校验",
    "message": "校验结果描述",
    "field": "字段名",
    "expected": "期望值",
    "actual": "实际值",
    "suggestion": "修正建议"
}
```

## 级别定义

- **ERROR**: 违反强制性业务规则
- **WARNING**: 不符合常规业务逻辑，需人工确认
- **INFO**: 业务规则校验通过
