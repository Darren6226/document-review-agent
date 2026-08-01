import { X, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getHistory, HistoryRecord } from '../services/api';

interface HistoryPanelProps {
  onClose: () => void;
  embedded?: boolean;
}

// 风险等级 -> 展示样式映射
const RISK_STYLES: Record<string, { label: string; className: string }> = {
  PASSED: { label: '通过', className: 'text-green-600' },
  WARNING: { label: '警告', className: 'text-amber-600' },
  FAILED: { label: '不通过', className: 'text-red-600' },
  high: { label: '高风险', className: 'text-red-600' },
  medium: { label: '中风险', className: 'text-amber-600' },
  low: { label: '低风险', className: 'text-blue-600' },
  none: { label: '无风险', className: 'text-green-600' },
};

export function HistoryPanel({ onClose, embedded = false }: HistoryPanelProps) {
  const [activeTab, setActiveTab] = useState<'history'>('history');
  const [searchQuery, setSearchQuery] = useState('');
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<'all' | '票据审查' | '合同审查'>('all');
  const [showFilterMenu, setShowFilterMenu] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getHistory()
      .then((data) => {
        if (!cancelled) setRecords(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 点击外部区域关闭筛选菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.filter-menu-container')) {
        setShowFilterMenu(false);
      }
    };
    if (showFilterMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showFilterMenu]);

  // 收藏功能后端暂未支持，历史标签展示后端返回的真实记录
  const currentItems: HistoryRecord[] = records;

  const filteredItems = currentItems.filter(item => {
    // 搜索过滤
    const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase());
    // 类型过滤
    const matchesType = filterType === 'all' || item.type === filterType;
    return matchesSearch && matchesType;
  });

  const panelContent = (
    <>
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
          onClick={onClose}
          className="p-4 hover:bg-white/60 transition-all duration-300 hover:scale-110"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 搜索栏 */}
      <div className="p-4 border-b border-white/30">
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 px-3 py-2 glass-effect rounded-lg">
            <Search className="w-4 h-4 text-gray-500 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索标题..."
              className="flex-1 bg-transparent outline-none text-sm text-gray-700 placeholder:text-gray-400"
            />
          </div>
          <div className="relative filter-menu-container">
            <button
              onClick={() => setShowFilterMenu(!showFilterMenu)}
              className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-lg text-sm shadow-md hover:shadow-lg transition-all duration-300 whitespace-nowrap"
            >
              {filterType === 'all' ? '全部类型' : filterType}
            </button>
            {showFilterMenu && (
              <div className="absolute right-0 top-full mt-1 w-32 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                <button
                  onClick={() => { setFilterType('all'); setShowFilterMenu(false); }}
                  className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-100 rounded-t-lg ${filterType === 'all' ? 'bg-blue-50 text-blue-600' : 'text-gray-700'}`}
                >
                  全部类型
                </button>
                <button
                  onClick={() => { setFilterType('票据审查'); setShowFilterMenu(false); }}
                  className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-100 ${filterType === '票据审查' ? 'bg-blue-50 text-blue-600' : 'text-gray-700'}`}
                >
                  票据审查
                </button>
                <button
                  onClick={() => { setFilterType('合同审查'); setShowFilterMenu(false); }}
                  className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-100 rounded-b-lg ${filterType === '合同审查' ? 'bg-blue-50 text-blue-600' : 'text-gray-700'}`}
                >
                  合同审查
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 列表内容 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="w-10 h-10 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-gray-700">加载历史记录中...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
            <div className="w-20 h-20 bg-gradient-to-br from-red-100 to-orange-100 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-gray-700 mb-2">加载失败</p>
            <p className="text-xs text-gray-500 text-center">{error}</p>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="w-20 h-20 bg-gradient-to-br from-blue-100 to-purple-100 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-10 h-10 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-gray-700">暂无历史记录</p>
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {filteredItems.map((item, index) => {
              const risk = item.risk_level ? RISK_STYLES[item.risk_level] : undefined;
              return (
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
                  {item.summary && (
                    <div className="text-xs text-gray-500 mb-2 line-clamp-2">{item.summary}</div>
                  )}
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-green-600 flex items-center gap-1">
                      <div className="w-1.5 h-1.5 bg-green-600 rounded-full animate-pulse"></div>
                      {item.status}
                    </span>
                    {risk && (
                      <span className={`flex items-center gap-1 ${risk.className}`}>
                        {risk.label}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );

  if (embedded) {
    return (
      <div className="h-full w-full glass-effect-dark flex flex-col border border-white/30 rounded-2xl shadow-premium-lg animate-slide-in">
        {panelContent}
      </div>
    );
  }

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />

      {/* 侧边面板 */}
      <div className="fixed right-0 top-0 bottom-0 w-96 glass-effect-dark shadow-premium-lg z-50 flex flex-col animate-slide-in border-l border-white/30">
        {panelContent}
      </div>
    </>
  );
}