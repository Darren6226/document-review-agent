import { FileText, FileCheck } from 'lucide-react';

interface SidebarProps {
  activeMenu: string;
  onMenuChange: (menu: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({ activeMenu, onMenuChange, collapsed, onToggleCollapse }: SidebarProps) {
  const menuItems = [
    { icon: FileText, label: '票据审查', disabled: false },
    { icon: FileCheck, label: '合同审查', disabled: false },
  ];

  return (
    <div className={`glass-effect-dark border-r border-white/50 flex flex-col shadow-premium transition-all duration-300 ${
      collapsed ? 'w-16' : 'w-56'
    }`}>
      {/* 主菜单 */}
      <div className="flex-1 py-2 overflow-y-auto">
        {menuItems.map((item) => (
          <button
            key={item.label}
            onClick={() => onMenuChange(item.label)}
            className={`w-full px-4 py-2.5 flex items-center gap-3 transition-all duration-300 relative group ${
              activeMenu === item.label
                ? 'bg-gradient-to-r from-blue-500/10 to-purple-500/10 text-gray-900'
                : 'text-gray-600 hover:bg-white/60'
            }`}
            title={collapsed ? item.label : ''}
          >
            {activeMenu === item.label && (
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-blue-500 to-purple-500 rounded-r-full" />
            )}
            <item.icon className={`w-4 h-4 transition-transform duration-300 group-hover:scale-110 ${
              activeMenu === item.label ? 'text-blue-600' : ''
            } ${collapsed ? 'mx-auto' : ''}`} />
            {!collapsed && <span className="text-sm">{item.label}</span>}
          </button>
        ))}
      </div>

    </div>
  );
}