# 文档审核系统 - 前端项目

这是一个基于 React + TypeScript + Vite + Tailwind CSS 的文档审核系统前端项目。

## 项目特点

- ✨ 完整的 UI 设计,包含毛玻璃效果、渐变动画等现代化样式
- 🎨 使用 Tailwind CSS 3.4.18 进行样式开发
- ⚡️ Vite 6.x 提供极速的开发体验
- 📦 使用 React 18.3 和 TypeScript 5.x
- 🎯 包含完整的票据审查和合同审查功能界面
- 🔧 集成多个 Radix UI 组件库

## 技术栈

- **框架**: React 18.3.1
- **构建工具**: Vite 6.3.5
- **语言**: TypeScript 5.3.3
- **样式**: Tailwind CSS 3.4.18
- **UI 组件**: Radix UI 系列组件
- **图标**: Lucide React

## 开始使用

### 1. 安装依赖

```bash
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

项目将在 http://localhost:3000 自动打开

### 3. 构建生产版本

```bash
npm run build
```

### 4. 预览生产构建

```bash
npm run preview
```

## 主要功能

- **票据审查**: 文档上传、OCR识别、验证
- **合同审查**: 文档预览、合规检查
- **历史记录**: 审查历史、收藏功能

## 注意事项

1. 前端通过 `src/services/api.ts` 接入 FastAPI 后端（默认 `http://localhost:8000`，可用 `VITE_API_URL` 环境变量覆盖）
2. 本地开发需在后端启用 CORS（允许 `http://localhost:3000` 来源）
3. 后端 API 配置（密钥、MinerU 等）参见项目根目录 README 或后端 `.env.example`

## 许可证

学习演示项目
