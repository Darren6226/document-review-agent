# 文档审核后端服务

基于 FastAPI + Deep Agents 的文档审核系统后端，支持发票和合同的智能识别与审查。

## 📁 目录结构

```
backend/
├── main.py                          # FastAPI 主服务入口
├── __init__.py                      # 包初始化文件
├── requirements.txt                 # Python 依赖
├── .env                            # 环境变量配置
│
├── services/                       # 业务服务层
│   ├── __init__.py
│   ├── invoice_verification.py     # 发票 OCR 识别与提取
│   ├── invoice_agent.py            # 发票智能校验 (Deep Agent + Skills)
│   └── contract_extraction.py      # 合同关键信息提取
│
├── models/                         # 数据模型
│   ├── __init__.py
│   └── validation.py               # 校验结果 Pydantic 模型
│
├── skills/                         # Deep Agent Skills
│   ├── completeness/               # 完整性校验技能
│   ├── format/                     # 格式校验技能
│   ├── calculation/                # 计算校验技能
│   └── business/                   # 业务规则校验技能
│
├── prompts/                        # 提示词模板
│   ├── __init__.py
│   └── contract_audit_prompt.py    # 合同专业审核提示词
│
└── uploads/                        # 上传文件存储目录
```

## 🚀 功能模块

### 1. 发票处理 (`services/invoice_verification.py`)
- **功能**: 基于视觉大模型的发票 OCR 识别
- **支持**: 增值税专用发票、普通发票、电子发票
- **模型**: Qwen3-VL-32B-Instruct (通过硅基流动 API)
- **输入**: 发票图片 (PNG/JPG)
- **输出**: 结构化的发票信息 (JSON)

**使用示例**:
```python
from services.invoice_verification import InvoiceExtractionSystem

system = InvoiceExtractionSystem(
    api_key="your-api-key",
    model_name="Qwen/Qwen3-VL-32B-Instruct"
)

invoice = system.extract_from_image("./invoice.png")
print(invoice.to_json())
```

### 2. 发票校验 (`services/invoice_agent.py`)
- **功能**: 基于 Deep Agents + Skills 机制的发票智能校验
- **框架**: [Deep Agents](https://github.com/langchain-ai/deep-agents) (v0.4.12)
- **校验维度** (通过 Skills 实现):
  - 完整性校验：验证必填字段
  - 格式校验：验证发票代码、号码、税号格式
  - 计算校验：验证金额、税额计算
  - 业务规则校验：验证税率、日期等逻辑
- **输出**: 结构化校验报告 (`FinalValidationReport`)

**使用示例**:
```python
from services.invoice_agent import create_invoice_agent, validate_invoice_with_agent_sync

# 创建 Agent（传入 ChatOpenAI 实例避免 event loop 冲突）
agent = create_invoice_agent(
    model="Qwen/Qwen3.6-27B",
    debug=False
)

# 执行校验
report = validate_invoice_with_agent_sync(invoice_data, agent)
print(f"状态: {report.overall_status}")
print(f"总结: {report.summary}")
```

**Skills 机制**:
- 每个校验维度对应一个 Skill 目录 (`skills/<name>/`)
- `SKILL.md`：YAML frontmatter + Markdown 描述
- `references/`：参考资料文档
- Deep Agent 自动加载并调用相关 Skill

### 3. 合同信息提取 (`services/contract_extraction.py`)
- **功能**: 从合同文本中提取关键信息
- **提取内容**:
  - 合同类型、标题
  - 甲方、乙方信息
  - 合同金额、币种
  - 生效日期、到期日期
  - 关键条款摘要
- **模型**: Qwen3-VL-32B-Instruct

**使用示例**:
```python
from services.contract_extraction import extract_contract_info_dict

result = extract_contract_info_dict(contract_text)
print(result['party_a'])  # 甲方
print(result['total_amount'])  # 金额
```

### 4. 合同审核提示词 (`prompts/contract_audit_prompt.py`)
- **功能**: 提供专业的合同审核提示词模板
- **审核规则**:
  - 文本规范性（错别字、标点、语法）
  - 法律术语规范性
  - 权利义务对等性
  - 金额与数字准确性
  - 逻辑一致性
  - 法律合规性
- **输出**: 结构化的审核结果 (问题列表、修改建议、风险等级)

**使用示例**:
```python
from prompts import create_professional_contract_audit_prompt, AuditResult
from langchain_openai import ChatOpenAI

prompt = create_professional_contract_audit_prompt()
llm = ChatOpenAI(model="Qwen/Qwen3-VL-32B-Instruct", temperature=0.1)

structured_llm = llm.with_structured_output(AuditResult)
audit_chain = prompt | structured_llm

result = audit_chain.invoke({
    "rules": PROFESSIONAL_CONTRACT_AUDIT_RULES,
    "text": contract_text
})

print(f"发现问题：{len(result.issues)}")
print(f"风险等级：{result.overall_risk_level}")
```

## 🔧 API 配置

### 快速开始

1. **复制模板文件**:
```bash
cp .env.example .env
```

2. **编辑 `.env` 文件**，填写你的真实 API密钥:
```bash
# LLM API (硅基流动 - 推荐)
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_BASE_URL=https://api.siliconflow.cn/v1

# MinerU PDF 解析服务
MINERU_API_KEY=your-mineru-api-token-here
MINERU_BASE_URL=https://mineru.net
```

3. **验证配置**:
```bash
python -c "from services.invoice_agent import create_invoice_agent; print('OK')"
```

### 详细说明

- 📄 **`.env.example`**: 配置模板（可提交到 Git）
- 🔐 **`.env`**: 实际配置（**禁止提交**，已添加到 `.gitignore`）
- 📚 **完整指南**: 查看项目根目录的 [`API_KEY_SETUP.md`](../API_KEY_SETUP.md)

### 支持的 AI 服务商

| 服务商 | 用途 | 推荐模型 |
|--------|------|----------|
| 硅基流动 | LLM 调用 | `Qwen/Qwen3.6-27B` |
| 阿里云 DashScope | 备选方案 | `qwen-vl-max` |
| MinerU | PDF 解析 | - |

⚠️ **安全警告**: 永远不要将真实的 API密钥提交到 Git！

## 🌐 API 端点

启动服务后访问 `http://localhost:8000/docs` 查看完整的 API 文档。

**主要端点**:
- `POST /api/invoice/upload` - 上传发票图片进行 OCR 识别
- `POST /api/invoice/validate` - 执行发票校验 (Deep Agent)
- `POST /api/contract/overview` - 合同关键信息提取
- `GET /api/health` - 健康检查

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

**核心依赖**:
- `fastapi` - Web 框架
- `uvicorn` - ASGI 服务器
- `deepagents` - Deep Agents 框架 (v0.4.12+)
- `langchain` - LLM 应用框架
- `langchain_openai` - OpenAI API 兼容客户端
- `pydantic` - 数据验证
- `python-multipart` - 文件上传支持
- `python-dotenv` - 环境变量管理

## ▶️ 运行服务

```bash
cd DocumentAgent/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问前端界面：`http://localhost:3000`

## 🧪 测试模块

```bash
# 测试发票识别
python services/invoice_verification.py

# 测试合同信息提取
python services/contract_extraction.py

# 测试发票校验 (Deep Agent)
python services/invoice_agent.py
```

## 📝 注意事项

1. **API密钥安全**: 不要将 `.env` 文件提交到 Git
2. **跨平台路径**: 所有文件路径使用 `pathlib.Path` 确保跨平台兼容
3. **超时设置**: Deep Agent 调用可能需要 2-3 分钟，请耐心等待
4. **错误处理**: 所有外部调用都包含异常捕获和友好提示
5. **日志输出**: 关键操作都有详细的调试日志
6. **Event Loop**: FastAPI 使用 `def` 端点避免与 Deep Agent 的 event loop 冲突

## 🔗 相关文档

- [Deep Agents 官方文档](https://github.com/langchain-ai/deep-agents)
- [部署指南](../DEPLOYMENT_GUIDE.md)
- [前端文档](../frontend/README.md)
- [快速开始](../frontend/QUICKSTART.md)
