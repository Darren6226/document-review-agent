import { X, Search } from 'lucide-react';
import { useState } from 'react';

interface HistoryPanelProps {
  onClose: () => void;
}

export function HistoryPanel({ onClose }: HistoryPanelProps) {
  const [activeTab, setActiveTab] = useState<'history' | 'favorite'>('history');
  const [searchQuery, setSearchQuery] = useState('');

  const historyItems = [
    {
      id: 1,
      type: '合同审查',
      title: '解除、终止劳动合同协议书',
      date: '2024-11-17 14:30',
      status: '已完成'
    },
    {
      id: 2,
      type: '对比审查',
      title: '租赁合同对比分析',
      date: '2024-11-17 10:15',
      status: '已完成'
    },
    {
      id: 3,
      type: '票据审查',
      title: '增值税专用发票',
      date: '2024-11-16 16:45',
      status: '已完成'
    },
    {
      id: 4,
      type: '合同审查',
      title: '采购合同-设备类',
      date: '2024-11-16 09:20',
      status: '已完成'
    },
  ];

  const favoriteItems = [
    {
      id: 1,
      type: '合同审查',
      title: '标准劳动合同模板',
      date: '2024-11-15 11:30',
      status: '已收藏'
    },
  ];

  const currentItems = activeTab === 'history' ? historyItems : favoriteItems;

  const filteredItems = currentItems.filter(item =>
    item.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <>
      {/* 遮罩层 */}
      <div 
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />

      {/* 侧边面板 */}
      <div className="fixed right-0 top-0 bottom-0 w-96 glass-effect-dark shadow-premium-lg z-50 flex flex-col animate-slide-in border-l border-white/30">
        {/* 头部 */}
        <div className="flex items-center border-b border-white/30">
          <button
            onClick={() => setActiveTab('history')}
            className={`flex-1 px-6 py-4 transition-all duration-300 relative ${
              activeTab === 'history' ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <span>历史</span>
            {activeTab === 'history' && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-purple-500 rounded-t-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('favorite')}
            className={`flex-1 px-6 py-4 transition-all duration-300 relative ${
              activeTab === 'favorite' ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <span>收藏</span>
            {activeTab === 'favorite' && (
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-purple-500 rounded-t-full" />
            )}
          </button>
          <button
            onClick={onClose}
            className="p-4 hover:bg-white/60 transition-all duration-300 hover:scale-110"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 搜索栏 */}
        <div className="p-4 border-b border-white/30">
          <div className="flex gap-2">
            <button className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-lg text-sm shadow-md hover:shadow-lg transition-all duration-300 hover:scale-105">
              {activeTab === 'history' ? '合同审查' : '全部'}
            </button>
            <button className="px-4 py-2 glass-effect text-gray-600 rounded-lg text-sm hover:bg-white/90 transition-all duration-300 hover:scale-105">
              对比审查
            </button>
            <button className="p-2 hover:bg-white/60 rounded-lg transition-all duration-300 hover:scale-110">
              <Search className="w-4 h-4 text-gray-600" />
            </button>
          </div>
        </div>

        {/* 列表内容 */}
        <div className="flex-1 overflow-y-auto">
          {filteredItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <div className="w-20 h-20 bg-gradient-to-br from-blue-100 to-purple-100 rounded-2xl flex items-center justify-center mb-4">
                <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-gray-700">暂无{activeTab === 'history' ? '历史' : '收藏'}记录</p>
            </div>
          ) : (
            <div className="p-4 space-y-3">
              {filteredItems.map((item, index) => (
                <div
                  key={item.id}
                  className="p-4 glass-effect border border-white/30 rounded-xl hover:bg-white/60 cursor-pointer transition-all duration-300 hover:shadow-lg hover:scale-105"
                  style={{ animationDelay: `${index * 0.05}s` }}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="inline-block px-2 py-1 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-lg text-xs shadow-md">
                          {item.type}
                        </span>
                        <span className="text-xs text-gray-500">{item.date}</span>
                      </div>
                      <div className="text-sm">{item.title}</div>
                    </div>
                    <button className="p-1.5 hover:bg-white/60 rounded-lg transition-all duration-300 hover:scale-110">
                      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                      </svg>
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-green-600 flex items-center gap-1">
                      <div className="w-1.5 h-1.5 bg-green-600 rounded-full animate-pulse"></div>
                      {item.status}
                    </span>
                    <button className="text-blue-500 hover:text-blue-600 hover:underline transition-colors">查看详情</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}