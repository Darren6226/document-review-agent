# 文档审核系统 - 完整部署指南

## 项目结构

```
DocumentAgent/
├── backend/                  # FastAPI 后端
│   ├── main.py              # 主服务器文件
│   ├── requirements.txt     # Python 依赖
│   └── uploads/             # 上传文件目录(自动创建)
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── services/api.ts  # API 服务层
│   │   ├── components/      # UI 组件
│   │   └── App.tsx          # 主应用(已连接API)
│   ├── package.json
│   └── vite.config.ts
├── invoice_verification.py   # OCR识别核心代码
└── invoice_validation_agents.py  # 审查核心代码
```

## 快速启动

### 1. 后端启动

```bash
# 进入后端目录
cd /home/MuyuWorkSpace/07_DocumentReviewAgent/DocumentAgent/backend

# 安装依赖
pip install -r requirements.txt

# 设置API密钥(可选,不设置将使用测试模式)
export DASHSCOPE_API_KEY="your-api-key"

# 启动服务器
python main.py
```

后端将在 http://localhost:8000 启动

### 2. 前端启动

```bash
# 进入前端目录
cd /home/MuyuWorkSpace/07_DocumentReviewAgent/DocumentAgent/frontend

# 启动开发服务器(已经在运行中)
npm run dev
```

前端将在 http://localhost:3000 启动

## API 接口

### 1. 上传发票并OCR识别

**端点**: `POST /api/invoice/upload`

**请求**: 
- Content-Type: multipart/form-data
- 字段: file (图片文件)

**响应**:
```json
{
  "success": true,
  "message": "发票识别成功",
  "data": {
    "invoice_code": "3100153130",
    "invoice_number": "14641426",
    ...
  },
  "invoice_id": "3100153130_14641426"
}
```

### 2. 执行发票审查

**端点**: `POST /api/invoice/validate`

**请求**:
```json
{
  "invoice_id": "3100153130_14641426",
  "invoice_data": { ... }
}
```

**响应**:
```json
{
  "success": true,
  "message": "发票审查完成",
  "report": {
    "overall_status": "PASSED",
    "agent_reports": [ ... ]
  }
}
```

## 前后端集成

### 前端已实现:

1. **App.tsx** - 主应用组件
   - ✅ 调用 `uploadInvoice()` 上传发票
   - ✅ 调用 `validateInvoice()` 执行审查
   - ✅ 错误处理和加载状态

2. **API服务层** (`src/services/api.ts`)
   - ✅ `uploadInvoice(file)` - 上传并OCR识别
   - ✅ `validateInvoice(invoiceId, invoiceData)` - 执行审查
   - ✅ 完整的TypeScript类型定义

3. **ReviewResults组件**
   - ✅ 显示真实的审查报告
   - ✅ 按Agent分组显示结果
   - ✅ 错误/警告/信息分级显示

## 测试流程

1. 确保后端在 http://localhost:8000 运行
2. 确保前端在 http://localhost:3000 运行
3. 在前端上传发票图片
4. 查看OCR识别结果
5. 点击"开始审查"按钮
6. 查看审查报告

## 注意事项

- 未设置 DASHSCOPE_API_KEY 时,系统使用测试模式(返回模拟数据)
- 设置 API 密钥后,将使用真实的 AI 模型进行OCR和审查
- 支持的文件格式: PNG, JPG, JPEG, PDF
- 文件大小限制: 20MB

## 环境变量

### 后端
```bash
DASHSCOPE_API_KEY=your-api-key  # 阿里云DashScope API密钥
```

### 前端
```bash
VITE_API_URL=http://localhost:8000  # 后端API地址(可选)
```

## 生产部署建议

1. 后端使用 gunicorn 或 uvicorn 部署
2. 前端执行 `npm run build` 构建生产版本
3. 使用 Nginx 反向代理
4. 配置 HTTPS
5. 设置文件上传大小限制
6. 配置日志记录

祝部署顺利! 🎉
