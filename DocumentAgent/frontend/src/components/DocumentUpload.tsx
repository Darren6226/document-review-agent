import { Upload } from 'lucide-react';
import { useRef, useState } from 'react';

interface DocumentUploadProps {
  onUpload: (file: File) => void;
  activeMenu: string;
}

export function DocumentUpload({ onUpload, activeMenu }: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      onUpload(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const title = activeMenu === '票据审查' ? '票据审查，一键开启审查' : '合同审查，一键开启审查';
  const description = activeMenu === '票据审查' 
    ? '快速审查票据的合规性风险，提供专业的识别提示与优化建议'
    : '快速审查合同的合规性风险，提供专业的识别提示与优化建议';

  return (
    <div className="flex flex-col items-center justify-center h-full px-8 relative">
      {/* 装饰性背景元素 */}
      <div className="absolute top-20 right-20 w-72 h-72 bg-gradient-to-br from-blue-200/30 to-purple-200/30 rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-20 left-20 w-60 h-60 bg-gradient-to-br from-pink-200/30 to-blue-200/30 rounded-full blur-3xl animate-float" style={{ animationDelay: '2s' }} />
      
      <div className="max-w-2xl w-full relative z-10">
        <h1 className="text-center mb-2 gradient-text">{title}</h1>
        <p className="text-center text-gray-500 mb-8">
          {description}
        </p>

        <div className="flex gap-2 justify-center mb-8">
          <button className="px-6 py-2.5 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-xl hover:from-blue-600 hover:to-blue-700 transition-all duration-300 shadow-lg hover:shadow-xl hover:scale-105">
            {activeMenu === '票据审查' ? '票据审查' : '合同审查'}
          </button>
          <button className="px-6 py-2.5 glass-effect text-gray-700 rounded-xl hover:bg-white/90 transition-all duration-300 shadow-md hover:shadow-lg hover:scale-105">
            对比审查
          </button>
        </div>

        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300 cursor-pointer shadow-premium hover:shadow-premium-lg ${
            isDragging 
              ? 'border-blue-400 bg-gradient-to-br from-blue-50 to-purple-50 scale-105' 
              : 'border-gray-300 glass-effect hover:border-blue-300'
          }`}
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="flex justify-center mb-4">
            <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300 ${
              isDragging 
                ? 'bg-gradient-to-br from-blue-500 to-purple-500 scale-110' 
                : 'bg-gradient-to-br from-blue-100 to-purple-100'
            }`}>
              <Upload className={`w-8 h-8 ${isDragging ? 'text-white' : 'text-blue-500'} transition-colors duration-300`} />
            </div>
          </div>
          
          <div className="mb-2">点击或将{activeMenu === '票据审查' ? '票据' : '合同'}拖拽到这里上传</div>
          <div className="text-sm text-gray-500">
            单个文件不超过20M，限20份文件，限定格式：pdf/doc/docx/png/jpg/jpeg
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

        <div className="mt-6 flex items-center gap-2 text-sm text-gray-600 glass-effect rounded-lg p-3">
          <svg className="w-4 h-4 text-blue-500" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 13A6 6 0 1114 8a6 6 0 01-6 6z"/>
            <path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1h-3v3a.5.5 0 01-1 0v-3h-3a.5.5 0 010-1h3v-3A.5.5 0 018 4z"/>
          </svg>
          <span>{activeMenu}尚处在测试阶段</span>
          <button className="text-blue-500 hover:text-blue-600 hover:underline transition-colors text-xs">
            发现缺陷？反馈 →
          </button>
        </div>
      </div>
    </div>
  );
}