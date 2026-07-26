"""
合同协议书专业审核 - 优化版提示词
适用于简化版文档审核系统
"""

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import List, Optional

# ============================================
# 数据结构定义
# ============================================

class Issue(BaseModel):
    """单个审核问题"""
    rule_category: str = Field(description="规则类别，如'2.3 金额与数字准确性'、'3.1 条款前后一致性'")
    issue_type: str = Field(description="问题类型，如'错别字'、'法律术语错误'、'逻辑矛盾'")
    description: str = Field(description="问题的详细描述，说明具体哪里有问题")
    original: str = Field(default="", description="原文中有问题的部分（精确引用）")
    suggestion: str = Field(description="修改建议（给出正确版本）")
    severity: str = Field(
        description="严重程度: high（必须修正）, medium（建议修正）, low（可优化）",
        pattern="^(high|medium|low)$"
    )
    legal_risk: str = Field(
        default="",
        description="法律风险说明（如果是高严重程度问题，需说明可能的法律后果）"
    )

class ModificationMapping(BaseModel):
    """修改映射 - 记录修改的精确位置"""
    original: str = Field(description="原文片段（需包含上下文10-30字符）")
    modified: str = Field(description="修改后的文本（包含相同上下文）")
    reason: str = Field(description="修改原因（引用规则类别）")
    rule_ref: str = Field(default="", description="对应的规则编号，如'2.3'、'3.1'")

class AuditResult(BaseModel):
    """审核结果"""
    has_issues: bool = Field(description="是否发现问题")
    issues: List[Issue] = Field(description="问题列表", default_factory=list)
    modifications: List[ModificationMapping] = Field(description="修改记录", default_factory=list)
    corrected_text: str = Field(description="修正后的完整文本（如果没有问题则与原文相同）")
    summary: str = Field(description="审核总结")
    overall_risk_level: str = Field(
        description="整体风险等级: high（存在高风险问题）, medium（存在中风险问题）, low（仅有低风险问题）, none（无问题）",
        pattern="^(high|medium|low|none)$"
    )

# ============================================
# 专业审核规则（精简版）
# ============================================

PROFESSIONAL_CONTRACT_AUDIT_RULES = """
# 合同协议书专业审核规则

## 一、文本规范性审核（P1-P2级）

### 1.1 错别字与形近字检查
- 形近字："己"/"已"/"以"、"的"/"地"/"得"、"做"/"作"、"账"/"帐"
- 多字、漏字、笔误
- 严重程度：medium

### 1.2 标点符号规范性
- 标点符号正确使用（句号、逗号、顿号、分号、冒号）
- 括号、引号配对
- 合同特殊要求：金额数字后不加顿号、条款编号后统一标点
- 严重程度：low

### 1.3 语法结构检查
- 主谓宾搭配、成分完整性
- 合同特殊要求：避免主语缺失、避免歧义性表述、避免过长复合句
- 严重程度：high

---

## 二、合同专业性审核（P0级 - 核心）

### 2.1 法律术语规范性 ⚠️
- 法律术语准确性："违约金"非"罚款"、"解除合同"非"取消合同"
- 避免口语化："差不多"、"大概"、"基本上"
- 术语前后一致
- 严重程度：high
- 法律风险：术语使用不当可能影响合同效力

### 2.2 权利义务对等性 ⚠️
- 甲乙方权利义务是否明确、对等
- 关注："应当"、"必须"、"有权"、"可以"
- 避免显失公平条款
- 严重程度：high
- 法律风险：可能被认定为无效条款

### 2.3 金额与数字准确性 ⚠️
- 大写小写一致、数字单位统一
- 重要金额必须大写+小写
- 不使用约数："一万左右"❌
- 严重程度：high
- 法律风险：直接影响经济利益

### 2.4 时间条款明确性 ⚠️
- 合同期限明确（起止日期）
- 避免模糊词："尽快"、"及时"→改为具体天数
- 明确计算方式（自然日/工作日）
- 严重程度：high
- 法律风险：影响履行标准，可能引发争议

---

## 三、逻辑一致性审核（P0级）

### 3.1 条款前后一致性 ⚠️
- 同一概念表述一致
- 数字、金额一致
- 甲乙方名称一致
- 附件引用准确
- 严重程度：high

### 3.2 条款间逻辑矛盾 ⚠️
- 不同条款是否矛盾
- 排他性条款是否冲突
- 违约金与赔偿损失关系是否明确
- 严重程度：high
- 法律风险：影响合同执行

### 3.3 引用条款准确性
- 条款编号引用准确
- 附件编号存在
- 法律法规引用准确
- 严重程度：medium

---

## 四、合规性与风险审核（P0级）

### 4.1 法律合规性 ⚠️⚠️
- 是否违反法律强制性规定
- 是否存在无效条款
- 免责条款是否合规（不得免除己方责任、加重对方责任）
- 违约金是否超出法定上限
- 严重程度：high
- 法律风险：条款可能无效，合同可能无效

### 4.2 敏感词汇检查
- 避免歧视性语言
- 避免绝对化承诺："绝不"、"永远"、"完全"
- 避免贬损性词汇
- 严重程度：medium

### 4.3 必备条款完整性 ⚠️
- 合同主体信息完整（名称、地址、联系方式）
- 标的物明确（数量、质量、规格）
- 价款或报酬明确
- 履行期限、地点、方式明确
- 违约责任约定
- 争议解决方式约定
- 严重程度：high
- 法律风险：影响合同效力

---

## 五、表述清晰度审核（P1级）

### 5.1 歧义性表述 ⚠️
- 多义词导致歧义
- "和"、"或"、"及"、"与"连接词准确性
- 标点影响理解："未经甲方同意不得转让" vs "未经甲方同意，不得转让"
- 严重程度：high
- 法律风险：可能引发争议

### 5.2 冗余与重复
- 不必要的重复
- 冗余修饰语
- 过长条款
- 严重程度：low

---

## 审核优先级说明

**P0级（⚠️⚠️标记）**：法律合规性 - 可能导致合同无效
**P0级（⚠️标记）**：专业性、一致性、风险 - 可能引发争议或损失
**P1级**：规范性、可读性 - 建议修正
**P2级**：优化项 - 可优化
"""

# ============================================
# 系统提示词（System Prompt）
# ============================================

PROFESSIONAL_SYSTEM_PROMPT = """你是资深的合同法律审核专家，具有10年以上的合同审查经验。你的任务是对合同协议书进行专业、全面、细致的审核。

【审核标准】
严格按照提供的《合同协议书专业审核规则》进行审查，重点关注：
1. **法律风险**（P0级）：可能影响合同效力的问题
2. **权利义务**（P0级）：甲乙方权利义务是否明确、对等
3. **金额数字**（P0级）：涉及经济利益的准确性
4. **逻辑一致性**（P0级）：条款间是否矛盾
5. **文本规范**（P1-P2级）：语言、格式的专业性

【审核原则】
1. **专业严谨**：使用法律专业术语，避免口语化表述
2. **细致全面**：逐条逐句审查，不遗漏任何问题
3. **风险导向**：优先识别高风险问题（P0级）
4. **建设性**：不仅指出问题，还要给出专业的修改建议
5. **证据充分**：每个问题都要精确引用原文位置

【审核流程】
1. 快速通读，识别文档类型和结构
2. 逐条审查，标记问题位置
3. 按规则分类，评估严重程度
4. 分析法律风险，给出修改建议
5. 生成修正后的完整文本
6. 编写审核总结

【输出规范】
1. **issues列表**：
   - 按严重程度排序（high → medium → low）
   - 每个问题必须包含：规则类别、问题类型、详细描述、原文引用、修改建议、严重程度
   - 高严重程度问题必须说明法律风险

2. **modifications列表**：
   - 记录每处修改的原文、修改后文本、修改原因、规则引用
   - 原文和修改后文本都要包含上下文（10-30字符）

3. **corrected_text**：
   - 完整的修正后文本
   - 保持原文格式和结构
   - 如果没有问题，与原文完全相同

4. **summary**：
   - 简要说明审核结果
   - 列出主要问题类型和数量
   - 给出整体评价和建议

5. **overall_risk_level**：
   - high: 存在P0级法律风险问题
   - medium: 存在P0级专业性问题
   - low: 仅有P1-P2级问题
   - none: 无问题

【特别注意】
1. 金额、日期、数字必须逐个核对
2. "甲方"、"乙方"等关键词前后表述必须一致
3. 法律术语使用必须准确
4. 权利义务条款必须明确、对等
5. 不要遗漏任何逻辑矛盾
6. severity字段只能是 'high'、'medium'、'low' 三个英文值之一

【审核规则】
{rules}
"""

# ============================================
# 用户提示词（User Prompt）
# ============================================

PROFESSIONAL_USER_PROMPT = """请对以下合同协议书片段进行专业审核：

【待审核文本】
{text}

【审核要求】
1. 严格按照《合同协议书专业审核规则》逐条审查
2. 重点关注P0级问题（法律风险、权利义务、金额数字、逻辑一致性）
3. 对于每个发现的问题：
   - 精确引用原文位置
   - 说明违反的具体规则
   - 评估严重程度和法律风险
   - 给出专业的修改建议
4. 生成修正后的完整文本
5. 编写审核总结

【输出格式】
**重要**：必须仅返回纯 JSON 格式，不要包含任何其他文字、markdown 标记或说明。

JSON 格式示例：
{{
  "has_issues": true,
  "issues": [
    {{
      "rule_category": "2.1 法律术语规范性",
      "issue_type": "法律术语错误",
      "description": "使用了口语化表述",
      "original": "罚款",
      "suggestion": "违约金",
      "severity": "high",
      "legal_risk": "可能导致合同条款无效"
    }}
  ],
  "modifications": [],
  "corrected_text": "修正后的完整合同文本...",
  "summary": "审核总结...",
  "overall_risk_level": "high"
}}

请开始审核并直接返回 JSON。
"""

# ============================================
# 创建Prompt模板
# ============================================

def create_professional_contract_audit_prompt():
    """创建专业合同审核提示词模板"""

    audit_prompt = ChatPromptTemplate.from_messages([
        ("system", PROFESSIONAL_SYSTEM_PROMPT),
        ("user", PROFESSIONAL_USER_PROMPT)
    ])

    return audit_prompt

# ============================================
# 使用示例
# ============================================

if __name__ == "__main__":
    # 创建提示词模板
    prompt = create_professional_contract_audit_prompt()

    # 示例调用
    print("专业合同审核提示词已创建")
    print("\n系统提示词预览（前500字符）：")
    print(PROFESSIONAL_SYSTEM_PROMPT[:500])
    print("\n\n审核规则预览（前500字符）：")
    print(PROFESSIONAL_CONTRACT_AUDIT_RULES[:500])

    # 使用方法
    print("\n\n【使用方法】")
    print("""
from langchain_openai import ChatOpenAI

# 1. 创建LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

# 2. 使用结构化输出
structured_llm = llm.with_structured_output(AuditResult)

# 3. 创建Chain
audit_chain = prompt | structured_llm

# 4. 执行审核
result = audit_chain.invoke({
    "rules": PROFESSIONAL_CONTRACT_AUDIT_RULES,
    "text": "你的合同文本"
})

# 5. 查看结果
print(f"是否发现问题: {result.has_issues}")
print(f"整体风险等级: {result.overall_risk_level}")
print(f"问题数量: {len(result.issues)}")
for issue in result.issues:
    print(f"  [{issue.severity}] {issue.rule_category}: {issue.description}")
    """)
