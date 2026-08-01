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

  // 后端 /api/contract/audit 仅接受 PDF，其余格式会返回 400；票据审查支持更多格式
  const isContract = activeMenu === '合同审查';
  const acceptAttr = isContract ? '.pdf' : '.pdf,.doc,.docx,.png,.jpg,.jpeg';
  const formatHint = isContract ? '限定格式：pdf' : '限定格式：pdf/doc/docx/png/jpg/jpeg';

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
            单个文件不超过20M，限20份文件，{formatHint}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept={acceptAttr}
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

      </div>
    </div>
  );
}