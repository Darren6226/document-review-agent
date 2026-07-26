# 快速开始指南

## ✅ 项目已成功配置!

你的 React 前端项目已经完全配置好,可以直接运行了!

## 🚀 立即开始

### 1. 启动开发服务器

项目已经在后台运行中,访问:

**http://localhost:3000**

### 2. 重新启动(如需要)

```bash
cd /home/MuyuWorkSpace/07_DocumentReviewAgent/DocumentAgent/frontend
npm run dev
```

### 3. 构建生产版本

```bash
npm run build
```

构建产出在 `build` 目录

## 📁 项目结构

```
frontend/
├── src/
│   ├── components/        # 所有React组件
│   │   ├── Sidebar.tsx   # 侧边栏
│   │   ├── DocumentUpload.tsx
│   │   ├── DocumentPreview.tsx
│   │   ├── OCRResults.tsx
│   │   ├── ReviewResults.tsx
│   │   └── HistoryPanel.tsx
│   ├── styles/
│   │   └── globals.css   # 全局样式(保留所有UI效果)
│   ├── App.tsx           # 主应用
│   └── main.tsx          # 入口文件
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 🎨 UI 特色(完全保留)

✅ 毛玻璃效果 (glass-effect)
✅ 渐变动画 (animate-gradient)
✅ 浮动动画 (animate-float)
✅ 高级阴影 (shadow-premium)
✅ 动态背景 (dynamic-bg)
✅ 所有自定义 CSS 动画

## 🔧 技术栈

- React 18.3.1
- TypeScript 5.3.3
- Vite 6.4.1
- Tailwind CSS 3.4.18
- Radix UI 组件库
- Lucide Icons

## 📝 下一步 - 接入后端

当你准备接入 FastAPI 后端时:

1. 创建 API 服务层:
```typescript
// src/services/api.ts
export const API_BASE_URL = 'http://localhost:8000';

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  });
  return response.json();
}
```

2. 在组件中调用API:
```typescript
const handleDocumentUpload = async (file: File) => {
  setIsProcessing(true);
  try {
    const result = await uploadDocument(file);
    setOcrData(result);
  } catch (error) {
    console.error(error);
  } finally {
    setIsProcessing(false);
  }
};
```

3. 配置 CORS (FastAPI 后端):
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## ⚡ 常见问题

**Q: 端口被占用?**
修改 `vite.config.ts` 中的 `server.port` 为其他端口

**Q: 样式没有生效?**
确保 `src/styles/globals.css` 被正确导入

**Q: TypeScript 报错?**
运行 `npm run build` 查看具体错误

## 📚 更多资源

- [React 文档](https://react.dev/)
- [Vite 文档](https://vitejs.dev/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Radix UI](https://www.radix-ui.com/)

祝开发顺利! 🎉
