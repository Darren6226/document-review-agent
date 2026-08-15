# 文档审核 Agent 系统

基于 **Deep Agents 框架**的智能文档审核系统，支持**发票审核**与**合同审核**两大场景。系统将 LLM 的语义理解能力与确定性代码校验管线结合，通过 Skills 机制注入领域审核规则，实现可解释、可追溯的专业级文档审查。

## 核心特性

### 发票审核：主 Agent 三阶段编排 + 4 维度 Sub-Agent

```
                    ┌─────────────────────────────┐
                    │        主 Agent 编排         │
                    │  完整性(串行) → 格式(串行)    │
                    │  → 计算 ∥ 业务(并行)         │
                    └──────────┬──────────────────┘
           ┌──────────┬────────┴───────┬──────────┐
           ▼          ▼                ▼          ▼
      ┌─────────┐ ┌─────────┐   ┌──────────┐ ┌─────────┐
      │ 完整性   │ │  格式   │   │   计算   │ │  业务   │
      │Sub-Agent│ │Sub-Agent│   │Sub-Agent │ │Sub-Agent│
      └────┬────┘ └────┬────┘   └────┬─────┘ └────┬────┘
           └───────────┴─────┬──────┴─────────────┘
                             ▼
                  汇总组装 FinalValidationReport
```

- 每个维度 Sub-Agent 通过 `FilesystemBackend` 按需读取专属 `SKILL.md` 规则正文作为校验依据
- 单 skill 包装目录优化：各 Sub-Agent 仅注入本维度 skill 元数据，减少无关 token 与解析开销
- 结构化输出主路径 + Python 解析兜底，保证四维分项始终存在

### 合同审核：Harness Engineering v2 架构

- **确定性下沉**：金额大小写、日期合法性、条款引用、甲乙方一致性由代码管线（正则 + 规则工具）先行判定，LLM 不重复判定
- **类型识别 + 动态 Skill**：轻量 LLM 识别合同类型（劳动/租赁/借款/销售），按需加载专属审核规则
- **单 Agent + VFS + Planner**：合同写入虚拟文件系统，Agent 自规划审核顺序，system prompt 仅约束必审维度清单
- **流式 SSE 输出**：审核过程逐事件推送（阶段进度 / LLM 增量 token / 最终报告 / 错误）

### 工程化设计

- **MinerU PDF 解析缓存**：overview 阶段解析结果按 `parse_id` 缓存复用，避免同一 PDF 重复调用解析服务；TTL 过期缓存由后台任务定期清理
- **Pydantic 边界校验**：请求/响应模型统一由 Pydantic 在 API 边界校验，内部信任已验证数据
- **历史记录持久化**：审核结果落盘存储，支持前端回看
- **优雅降级**：LLM 超时/异常时明确返回失败状态而非静默吞错

## 技术栈

| 层级 | 技术 |
|---|---|
| Agent 框架 | Deep Agents（deepagents）、LangChain、LangGraph |
| LLM 服务 | 硅基流动（发票审核）、阿里云 DashScope（合同审核），OpenAI 兼容协议 |
| PDF 解析 | MinerU API（PDF → Markdown） |
| 后端 | Python + FastAPI + Pydantic + SSE |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS + Radix UI |

## 项目结构

```
DocumentAgent/
├── backend/
│   ├── main.py                    # FastAPI 入口，API 路由与解析缓存管理
│   ├── requirements.txt
│   ├── .env.example               # 环境变量模板
│   ├── start_backend.bat          # Windows 一键启动脚本
│   ├── services/
│   │   ├── invoice_agent.py       # 发票审核：三阶段编排 + 4 维度 Sub-Agent
│   │   ├── invoice_verification.py# 发票 OCR 识别与结构化提取
│   │   ├── contract_agent.py      # 合同审核：单 Agent + VFS + Planner
│   │   ├── contract_classifier.py # 合同类型轻量识别
│   │   ├── contract_deterministic.py # 确定性校验管线
│   │   ├── contract_extraction.py # 合同要素提取
│   │   └── history_store.py       # 审核历史持久化
│   ├── tools/
│   │   ├── invoice_tools.py       # 发票计算校验工具
│   │   └── contract_tools.py      # 合同提取/校验工具（供 Agent 调用）
│   ├── skills/                    # 各维度审核规则（SKILL.md + references）
│   │   ├── completeness/ format/ calculation/ business/   # 发票四维度
│   │   └── contract_audit/        # 合同语义审核 + 分类型规则
│   ├── prompts/                   # 合同审核 system prompt
│   └── models/
│       └── validation.py          # Pydantic 报告模型
└── frontend/
    ├── src/
    │   ├── App.tsx                # 主应用（票据/合同双 Tab）
    │   ├── components/            # 上传、预览、审核结果、历史面板
    │   └── services/api.ts        # API 层（含 SSE 流式解析）
    └── package.json
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- 三个 API Key：[硅基流动](https://cloud.siliconflow.cn/)（发票审核）、[阿里云 DashScope](https://dashscope.console.aliyun.com/)（合同审核）、[MinerU](https://mineru.net)（PDF 解析）

### 1. 配置后端

```bash
cd DocumentAgent/backend
pip install -r requirements.txt

# Windows 可直接复制
copy .env.example .env
# Linux/Mac
cp .env.example .env
```

编辑 `.env`，填入三个服务的 API Key（模板内有获取方式说明）。

### 2. 启动后端

```bash
# 方式一：直接启动
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 方式二（Windows）：后台启动，日志写入 logs/
start_backend.bat
```

### 3. 配置并启动前端

```bash
cd DocumentAgent/frontend
npm install
npm run dev
```

访问 http://localhost:3000 即可使用。后端地址默认 `http://localhost:8000`，可通过前端 `VITE_API_URL` 环境变量覆盖。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/invoice/upload` | 上传发票图片/PDF，OCR 识别并结构化 |
| POST | `/api/invoice/validate` | 发票四维度审核（完整性/格式/计算/业务） |
| POST | `/api/contract/overview` | 上传合同 PDF，解析并返回要素概览 |
| POST | `/api/contract/audit` | 合同深度审核，`text/event-stream` 流式返回 |
| GET | `/api/history` | 查询审核历史 |
| GET | `/api/health` | 健康检查 |

合同审核 SSE 事件协议：

```
data: {"type":"stage","stage":"...","message":"..."}   # 阶段进度
data: {"type":"token","content":"..."}                 # LLM 增量输出
data: {"type":"done","report":{...}}                   # 最终完整报告
data: {"type":"error","message":"..."}                 # 致命错误
```

## 关键设计决策

**为什么发票用多 Sub-Agent、合同用单 Agent？**
发票审核四个维度（完整性/格式/计算/业务）相互独立、规则明确，适合并行编排、各自加载专属 Skill；合同审核维度间存在语义关联（如违约条款依赖对权利义务的理解），单 Agent + Planner 自规划更合适——同时规避了嵌套 Sub-Agent 在手动事件循环中可能不收敛挂起的问题。

**为什么确定性规则下沉到代码？**
金额大小写一致性、日期合法性等校验用正则和规则代码判定是 100% 可靠的，交给 LLM 既浪费 token 又可能出错。LLM 只负责真正需要语义理解的判定（法律术语、风险条款、逻辑一致性），各司其职。

## License

MIT
