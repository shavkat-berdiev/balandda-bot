import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Grid3x3,
  FileText,
  Menu,
  X,
  Calendar,
  LogOut,
} from 'lucide-react';

const navItems = [
  { path: '/analytics', label: 'Обзор', icon: BarChart3 },
  { path: '/analytics/income', label: 'Доходы', icon: TrendingUp },
  { path: '/analytics/expenses', label: 'Расходы', icon: TrendingDown },
  { path: '/analytics/properties', label: 'Объекты', icon: Grid3x3 },
  { path: '/analytics/reports', label: 'Отчёты', icon: FileText },
];

const dateRangeOptions = [
  { label: 'Сегодня', value: 'today' },
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: 'Произвольный', value: 'custom' },
];

export default function DashboardLayout({ user, onLogout, children, dateRange, onDateRangeChange }) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);

  const getDateRangeLabel = () => {
    const option = dateRangeOptions.find((o) => o.value === dateRange);
    return option?.label || dateRange;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile header */}
      <div className="lg:hidden bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <button onClick={() => setSidebarOpen(true)} className="text-gray-600">
          <Menu size={24} />
        </button>
        <h1 className="text-lg font-semibold text-gray-800">Balandda Analytics</h1>
        <div className="w-6" />
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="fixed inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-xl z-50">
            <SidebarContent
              location={location}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-col flex-grow" style={{ backgroundColor: '#1a5676' }}>
          <SidebarContent location={location} />
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top bar with date range picker */}
        <div className="bg-white border-b border-gray-200 px-6 py-4 lg:px-8">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-800">Аналитика</h2>
            <div className="relative">
              <button
                onClick={() => setShowDatePicker(!showDatePicker)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-50 hover:bg-gray-100 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 transition-colors"
              >
                <Calendar size={18} />
                {getDateRangeLabel()}
              </button>
              {showDatePicker && (
                <div className="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
                  {dateRangeOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => {
                        onDateRangeChange(option.value);
                        setShowDatePicker(false);
                      }}
                      className={`block w-full text-left px-4 py-2 text-sm transition-colors ${
                        dateRange === option.value
                          ? 'bg-blue-50 text-blue-700 font-medium'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <main className="p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

function SidebarContent({ location, onClose }) {
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-opacity-20 border-white flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Balandda</h1>
          <p className="text-xs text-white text-opacity-70">Analytics</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-white text-opacity-70">
            <X size={20} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path || location.pathname.startsWith(path);
          return (
            <Link
              key={path}
              to={path}
              onClick={onClose}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? 'bg-white bg-opacity-20 text-white'
                  : 'text-white text-opacity-70 hover:bg-white hover:bg-opacity-10 hover:text-white'
              }`}
            >
              <Icon size={20} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-opacity-20 border-white text-xs text-white text-opacity-60">
        <p>© 2026 Balandda</p>
      </div>
    </div>
  );
}
