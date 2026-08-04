import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  BarChart3, FolderOpen, Users, ArrowLeftRight, LogOut, Menu, X, Home, Sparkles, Wine,
  FileText, CreditCard, Wallet, CalendarDays, History, Waves, Layers, CalendarClock,
  MessageSquare, ChevronDown, PieChart,
} from 'lucide-react';

/**
 * Sidebar structure (2026-08 reorg).
 *
 * Booking views (Календарь, Бассейн, Расписание SPA, Журнал броней) are no longer
 * listed here — they live on calendar.balandda.uz. Their routes are kept in App.jsx
 * for the front-office domain and for old bookmarks.
 *
 * Related admin screens are merged into tabbed hub pages, so one menu entry now
 * covers what used to be 3–5 entries.
 */
const navSections = [
  {
    // Top-level, no section header.
    items: [
      { path: '/', label: 'Дашборд', icon: BarChart3 },
    ],
  },
  {
    title: 'Финансы',
    key: 'finance',
    items: [
      { path: '/analytics', label: 'Финансовая аналитика', icon: PieChart },
      { path: '/transactions', label: 'Транзакции', icon: ArrowLeftRight },
      { path: '/prepayments', label: 'Предоплаты', icon: CreditCard },
      { path: '/wallets', label: 'Кошельки', icon: Wallet },
      { path: '/categories', label: 'Категории операций', icon: FolderOpen },
      { path: '/admin/reports', label: 'Отчёты', icon: FileText },
    ],
  },
  {
    title: 'SPA',
    key: 'spa',
    items: [
      { path: '/spa-analytics', label: 'Аналитика SPA', icon: Sparkles },
      { path: '/spa-commissions', label: 'Комиссии SPA', icon: Wallet },
      { path: '/admin/spa', label: 'Справочник SPA', icon: Layers },
    ],
  },
  {
    title: 'Управление',
    key: 'admin',
    items: [
      { path: '/admin/users', label: 'Пользователи', icon: Users },
      { path: '/admin/properties', label: 'Объекты', icon: Home },
      { path: '/admin/shop', label: 'Мини бар и шоп', icon: Wine },
    ],
  },
];

const frontOfficeItems = [
  { path: '/calendar', label: 'Календарь', icon: CalendarDays },
  { path: '/pool', label: 'Бассейн', icon: Waves },
  { path: '/spa-schedule', label: 'Расписание SPA', icon: CalendarClock },
  { path: '/changelog', label: 'Журнал броней', icon: History },
];

export default function Layout({ user, onLogout, children, frontOffice }) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const roleLabels = {
    owner: 'Owner',
    OWNER: 'Владелец',
    admin: 'Administrator',
    ADMIN: 'Администратор',
    resort_manager: 'Resort Manager',
    RESORT_MANAGER: 'Менеджер курорта',
    restaurant_manager: 'Restaurant Manager',
    RESTAURANT_MANAGER: 'Менеджер ресторана',
    operator: 'Operator',
    OPERATOR: 'Оператор',
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile header */}
      <div className="lg:hidden bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <button onClick={() => setSidebarOpen(true)} className="text-gray-600">
          <Menu size={24} />
        </button>
        <h1 className="text-lg font-semibold text-gray-800">{frontOffice ? 'Balandda · Бронирование' : 'Balandda Analytics'}</h1>
        <div className="w-6" />
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="fixed inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-xl z-50">
            <SidebarContent
              user={user}
              roleLabels={roleLabels}
              location={location}
              onLogout={onLogout}
              frontOffice={frontOffice}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-col h-full overflow-hidden bg-white border-r border-gray-200">
          <SidebarContent user={user} roleLabels={roleLabels} location={location} onLogout={onLogout} frontOffice={frontOffice} />
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        <main className="p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

function NavLink({ item, location, onClose }) {
  const { path, label, icon: Icon } = item;
  // Hub pages keep their sub-screen in ?tab=, so pathname comparison is enough.
  const active = location.pathname === path;
  return (
    <Link
      to={path}
      onClick={onClose}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
      }`}
    >
      <Icon size={20} />
      {label}
    </Link>
  );
}

function SidebarContent({ user, roleLabels, location, onLogout, onClose, frontOffice }) {
  // Sections stay open by default; a section containing the active route can't be collapsed shut.
  const [collapsed, setCollapsed] = useState({});

  function toggle(key) {
    setCollapsed((c) => ({ ...c, [key]: !c[key] }));
  }

  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-800">Balandda</h1>
          <p className="text-xs text-gray-500">{frontOffice ? 'Бронирование' : 'Analytics Dashboard'}</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-gray-400">
            <X size={20} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 min-h-0 overflow-y-auto px-3 py-4 space-y-1">
        {frontOffice ? (
          frontOfficeItems.map((item) => (
            <NavLink key={item.path} item={item} location={location} onClose={onClose} />
          ))
        ) : (
          <>
            {navSections.map((section, i) => {
              const hasActive = section.items.some((it) => it.path === location.pathname);
              const isOpen = hasActive || !collapsed[section.key];
              return (
                <div key={section.key || `section-${i}`} className={section.title ? 'pt-3' : ''}>
                  {section.title && (
                    <button
                      onClick={() => toggle(section.key)}
                      className="w-full flex items-center justify-between px-3 py-1 mb-1 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-gray-600 transition-colors"
                    >
                      {section.title}
                      <ChevronDown
                        size={14}
                        className={`transition-transform ${isOpen ? '' : '-rotate-90'}`}
                      />
                    </button>
                  )}
                  {isOpen && (
                    <div className="space-y-1">
                      {section.items.map((item) => (
                        <NavLink key={item.path} item={item} location={location} onClose={onClose} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Bot replies, comment automation, leads & bot stats live in the CRM now */}
            <div className="pt-4">
              <a
                href="https://crm.balandda.uz/panel"
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors"
              >
                <MessageSquare size={20} />
                CRM · боты и заявки ↗
              </a>
              <a
                href="https://calendar.balandda.uz"
                target="_blank"
                rel="noreferrer"
                className="mt-1 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition-colors"
              >
                <CalendarDays size={20} />
                Календарь броней ↗
              </a>
            </div>
          </>
        )}
      </nav>

      {/* User info */}
      <div className="px-4 py-4 border-t border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
            {user.full_name?.charAt(0) || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800 truncate">{user.full_name}</p>
            <p className="text-xs text-gray-500">{roleLabels[user.role] || user.role}</p>
          </div>
          <button
            onClick={onLogout}
            className="text-gray-400 hover:text-red-500 transition-colors"
            title="Logout"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
