import { ZoomIn, ZoomOut, RotateCw } from 'lucide-react';
import { useState, useRef } from 'react';
import { ImageWithFallback } from './figma/ImageWithFallback';

interface DocumentPreviewProps {
  imageUrl: string;
  onStartReview: () => void;
  isProcessing: boolean;
}

export function DocumentPreview({ imageUrl, onStartReview, isProcessing }: DocumentPreviewProps) {
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 检测是否为PDF文件
  const isPDF = imageUrl?.startsWith('data:application/pdf');

  const handleZoomIn = () => {
    setZoom(prev => Math.min(prev + 10, 200));
  };

  const handleZoomOut = () => {
    setZoom(prev => Math.max(prev - 10, 50));
  };

  const handleRotate = () => {
    setRotation(prev => (prev + 90) % 360);
  };

  const handleLocalUpload = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="flex-1 bg-gradient-to-br from-gray-800 to-gray-900 flex flex-col shadow-premium-lg">
      {/* 工具栏 */}
      <div className="glass-effect bg-gray-900/80 p-3 flex items-center justify-between border-b border-white/10">
        <div className="flex items-center gap-2">
          <button
            onClick={handleZoomIn}
            className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-all duration-300 hover:scale-110"
          >
            <ZoomIn className="w-5 h-5" />
          </button>
          <div className="px-3 py-1 bg-gray-700 rounded-lg">
            <span className="text-white text-sm">{zoom}%</span>
          </div>
          <button
            onClick={handleZoomOut}
            className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-all duration-300 hover:scale-110"
          >
            <ZoomOut className="w-5 h-5" />
          </button>
          {!isPDF && (
            <button
              onClick={handleRotate}
              className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-all duration-300 hover:scale-110 hover:rotate-90"
            >
              <RotateCw className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3 items-center">
          <button
            onClick={handleLocalUpload}
            className="px-6 py-2.5 bg-gray-600 text-white rounded-xl hover:bg-gray-700 text-sm transition-all duration-300 hover:scale-105 whitespace-nowrap flex items-center gap-2 shadow-lg"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            本地上传
          </button>
          <button
            onClick={onStartReview}
            disabled={isProcessing}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 text-sm transition-all duration-300 disabled:bg-gray-500 disabled:cursor-not-allowed hover:scale-105 whitespace-nowrap flex items-center gap-2 shadow-lg"
          >
            {isProcessing ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                识别中...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                开始审查
              </>
            )}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            className="hidden"
          />
        </div>
      </div>

      {/* 文档预览区 */}
      <div className="flex-1 flex items-center justify-center p-4 overflow-auto">
        {isPDF ? (
          // PDF预览 - 使用iframe
          <div
            className="w-full h-full bg-white shadow-premium-lg rounded-lg overflow-hidden"
            style={{
              transform: `scale(${zoom / 100})`,
              transformOrigin: 'center center'
            }}
          >
            <iframe
              src={imageUrl}
              className="w-full h-full border-0"
              title="PDF Preview"
            />
          </div>
        ) : (
          // 图片预览
          <div
            className="max-w-4xl bg-white transition-all duration-500 shadow-premium-lg rounded-lg overflow-hidden"
            style={{
              transform: `scale(${zoom / 100}) rotate(${rotation}deg)`,
              width: '100%'
            }}
          >
            <ImageWithFallback
              src={imageUrl}
              alt="Document preview"
              className="w-full h-auto"
            />
          </div>
        )}
      </div>
    </div>
  );
}