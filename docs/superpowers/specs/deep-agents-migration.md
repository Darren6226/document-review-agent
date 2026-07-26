# Deep Agents 迁移方案

## 1. 项目背景

将现有文档审核项目从 LangChain Agent 迁移到 Deep Agents 框架，展示 harness engineer 思想。

### 核心改动
- Agent 框架：LangChain → Deep Agents
- 扩展机制：自定义 Agent 类 → Skills
- 结构化输出：保留 Pydantic 模型
- 部署方式：FastAPI 不变

## 2. 技术选型

### 框架信息
- **Deep Agents**: `deepagents==0.4.12`
- **官方文档**: https://docs.langchain.com/oss/python/deepagents/overview
- **底层框架**: 基于 LangGraph
- **默认模型**: `claude-sonnet-4-6`（可通过 `model` 参数切换）

### 组件对照

| 组件 | 现有 | 目标 |
|------|------|------|
| Agent 框架 | LangChain Agent | Deep Agents (`create_deep_agent`) |
| 扩展机制 | 4 个独立 Agent 类 | 4 个 Skills (SKILL.md) |
| 输出解析 | Pydantic 结构化 | `response_format` 参数 |
| 入口服务 | FastAPI | FastAPI（保留） |
| 部署 | 自部署 | 自部署（不依赖 Managed） |

### 核心 API 签名
```python
create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable] | None = None,
    *,
    system_prompt: str | None = None,
    skills: list[str] | None = None,      # Skill 路径列表
    response_format: ToolStrategy | ProviderStrategy | AutoStrategy | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent] | None = None,
    backend: BackendProtocol | None = None,
    # ... 其他参数
) -> CompiledStateGraph
```

## 3. 目录结构

```
DocumentAgent/
├── backend/
│   ├── main.py                    # FastAPI 入口（改造）
│   ├── skills/                    # 新增：Skills 目录
│   │   ├── completeness/
│   │   │   ├── SKILL.md           # 完整性校验 Skill
│   │   │   └── references/
│   │   │       └── rules.md       # 校验规则详情
│   │   ├── format/
│   │   │   ├── SKILL.md           # 格式校验 Skill
│   │   │   └── references/
│   │   │       └── patterns.md    # 正则表达式集合
│   │   ├── calculation/
│   │   │   ├── SKILL.md           # 计算校验 Skill
│   │   │   └── references/
│   │   │       └── formulas.md    # 计算公式
│   │   └── business/
│   │       ├── SKILL.md           # 业务规则 Skill
│   │       └── references/
│   │           └── policies.md    # 业务政策
│   ├── services/
│   │   ├── invoice_agent.py       # 新增：Deep Agent 入口
│   │   └── multi_model_router.py  # 保留
│   ├── models/                    # 保留 Pydantic 模型
│   │   └── validation.py
│   └── prompts/                   # 保留，迁移到 SKILL.md
├── requirements.txt               # 新增 deepagents 依赖
└── docs/
    └── superpowers/
        └── specs/
            └── deep-agents-migration.md  # 本文档
```

## 4. 实施步骤

### Step 1: 环境准备
- 安装 `deepagents` 包
- 验证 import 可用

### Step 2: 创建 Skills ✅
将现有 4 个 Validation Agent 转换为 4 个 Skill：
1. `completeness` - 必填字段完整性校验 ✅
2. `format` - 格式校验（税号、日期、代码格式） ✅
3. `calculation` - 金额计算校验 ✅
4. `business` - 业务规则校验 ✅

每个 Skill 包含：
- `SKILL.md`：从现有 Agent 的 system_prompt 提取 ✅
- `references/`：校验规则、正则表达式等参考文档 ✅

**Skills 目录结构：**
```
skills/
├── business/
│   ├── SKILL.md
│   └── references/
│       └── policies.md
├── calculation/
│   ├── SKILL.md
│   └── references/
│       └── formulas.md
├── completeness/
│   ├── SKILL.md
│   └── references/
│       └── rules.md
└── format/
    ├── SKILL.md
    └── references/
        └── patterns.md
```

### Step 3: 创建 Deep Agent ✅

**创建的文件：**

1. `models/validation.py` - Pydantic 数据模型
   - `ValidationLevel` - 校验级别枚举
   - `ValidationResult` - 单个校验结果
   - `AgentValidationReport` - Agent 校验报告
   - `FinalValidationReport` - 最终校验报告

2. `models/__init__.py` - 模块导出

3. `services/invoice_agent.py` - Deep Agent 入口
   - `create_invoice_agent()` - 创建 Agent
   - `validate_invoice_with_agent()` - 异步校验
   - `validate_invoice_with_agent_sync()` - 同步校验（兼容 FastAPI）

**核心代码：**
```python
from deepagents import create_deep_agent
from models.validation import FinalValidationReport

agent = create_deep_agent(
    model="openai:gpt-4o",
    skills=[
        "/skills/completeness",
        "/skills/format",
        "/skills/calculation",
        "/skills/business"
    ],
    system_prompt=SYSTEM_PROMPT,
    response_format=FinalValidationReport,
    debug=False,
    name="invoice-auditor"
)
```

### Step 4: 改造 FastAPI 入口 ✅

**修改内容：**
1. 删除旧的 `InvoiceValidationSystem` 导入和初始化
2. 新增 `invoice_agent` 导入和初始化
3. 修改 `validate_invoice` 端点使用 Deep Agent
4. 更新版本号为 `2.0.0`
5. 更新健康检查接口返回 Agent 状态

**关键变化：**
```python
# 旧代码
from services.invoice_validation import InvoiceValidationSystem, FinalValidationReport
validation_system = InvoiceValidationSystem(...)
report = validation_system.validate_invoice(invoice_data)

# 新代码
from services.invoice_agent import create_invoice_agent, validate_invoice_with_agent_sync
invoice_agent = create_invoice_agent(model="openai:gpt-4o")
report = validate_invoice_with_agent_sync(invoice_data, invoice_agent)
```

### Step 5: 测试验证
- 测试发票审查功能
- 验证结构化输出正确
- 确认降级机制正常

## 5. 关键设计决策

### 5.1 Skill 粒度
保持 4 个独立 Skill，而非合并为 1 个：
- 符合 SRP 原则
- 展示 Skills 机制
- 便于单独测试/复用

### 5.2 Prompt 处理
- 现有 Agent 的 system_prompt → 迁移到 SKILL.md body
- 校验规则细节 → 放入 references/ 目录
- 遵循 Progressive Disclosure 原则

### 5.3 结构化输出
保留现有 Pydantic 模型（`ValidationResult`、`FinalValidationReport`），Deep Agent 原生支持。

### 5.4 多模型路由
保留 `multi_model_router.py`，在 Skill 内部调用时使用。

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Deep Agents API 变化 | 中 | 锁定版本 `==0.4.12` |
| Skill 加载失败 | 低 | 降级到默认 prompt |
| 结构化输出不兼容 | 中 | 使用 `response_format` 参数 |
| 中文 SKILL.md 解析 | 高 | 测试验证，必要时用英文 |
| Skill 加载性能 | 中 | 基准测试，必要时合并 |
| 前端兼容性 | 高 | 返回格式保持一致 |
| 回滚困难 | 高 | Git 分支，保留旧代码 |

### 回滚方案
- Git 分支：`feature/deep-agents-migration`
- 触发条件：测试用例失败率 > 20%
- 回滚操作：`git checkout main`

## 7. 验收标准

### 环境验证
- [ ] `pip show deepagents` 显示版本 `0.4.12`
- [ ] `python -c "from deepagents import create_deep_agent"` 无报错

### Skill 验证
- [x] 4 个 Skill 目录创建完成（completeness/format/calculation/business）
- [x] 每个 Skill 包含 `SKILL.md`，格式为 YAML frontmatter + Markdown body
- [x] SKILL.md 文件大小 < 10MB，body < 500 行

### Agent 验证
- [x] `create_deep_agent(skills=[...])` 调用成功，返回 `CompiledStateGraph`
- [ ] Agent 可以正常 invoke，返回消息无报错
- [ ] `response_format=FinalValidationReport` 结构化输出无 ValidationError

### API 验证
- [x] `/api/invoice/upload` 端点正常工作
- [ ] `/api/invoice/validate` 返回格式与迁移前一致（字段名、类型、嵌套结构）
- [ ] 使用现有 mock 数据测试，`overall_status` 结果与迁移前一致
- [ ] 错误场景（缺失字段、格式错误）的校验结果与迁移前一致

### 兼容性验证
- [x] `/api/contract/overview` 端点不受影响（本次不迁移）
