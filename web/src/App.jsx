import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Categories from './pages/Categories';
import Transactions from './pages/Transactions';
import Analytics from './pages/Analytics';
import SpaAnalytics from './pages/SpaAnalytics';
import SpaCommissions from './pages/SpaCommissions';
import SpaSchedule from './pages/SpaSchedule';
// Merged hub pages (2026-08 menu reorg). Each one replaces 3–5 former sidebar entries;
// the original page components are unchanged and now render inside tabs.
import AdminUsers from './pages/AdminUsers';
import AdminPropertiesHub from './pages/AdminPropertiesHub';
import AdminSpaCatalog from './pages/AdminSpaCatalog';
// "Ответы бота" and CRM "Статистика" moved to crm.balandda.uz/panel (V2, 2026-07).
// AdminBotTemplates.jsx / Stats.jsx are kept on disk unrouted for easy rollback.
// DashboardLayout.jsx likewise — Analytics no longer nests a second sidebar.
import AdminShop from './pages/AdminShop';
import AdminReports from './pages/AdminReports';
import Prepayments from './pages/Prepayments';
import Calendar from './pages/Calendar';
import ChangeLog from './pages/ChangeLog';
import Wallets from './pages/Wallets';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      setUser(JSON.parse(stored));
    }
    setLoading(false);
  }, []);

  const handleLogin = (userData, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  // Front-office domain (calendar.balandda.uz): agents see ONLY the booking calendar.
  const frontOffice = window.location.hostname === 'calendar.balandda.uz';
  if (frontOffice) {
    return (
      <Layout user={user} onLogout={handleLogout} frontOffice>
        <Routes>
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/pool" element={<Calendar businessUnit="RESTAURANT" autoPrice={false} title="Бассейн" showImport={false} expires={false} />} />
          <Route path="/spa-schedule" element={<SpaSchedule />} />
          <Route path="/changelog" element={<ChangeLog />} />
          <Route path="*" element={<Navigate to="/calendar" />} />
        </Routes>
      </Layout>
    );
  }

  return (
    <Layout user={user} onLogout={handleLogout}>
      <Routes>
        <Route path="/" element={<Dashboard user={user} />} />

        {/* Финансы */}
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/prepayments" element={<Prepayments />} />
        <Route path="/wallets" element={<Wallets />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/admin/reports" element={<AdminReports user={user} />} />

        {/* SPA */}
        <Route path="/spa-analytics" element={<SpaAnalytics />} />
        <Route path="/spa-commissions" element={<SpaCommissions />} />
        <Route path="/admin/spa" element={<AdminSpaCatalog />} />

        {/* Управление */}
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/properties" element={<AdminPropertiesHub />} />
        <Route path="/admin/shop" element={<AdminShop />} />

        {/* Booking views live on calendar.balandda.uz and are no longer in the
            sidebar here, but the routes stay so existing deep links keep working. */}
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/pool" element={<Calendar businessUnit="RESTAURANT" autoPrice={false} title="Бассейн" showImport={false} expires={false} />} />
        <Route path="/spa-schedule" element={<SpaSchedule />} />
        <Route path="/changelog" element={<ChangeLog />} />

        {/* Legacy paths → merged hub pages (keeps old bookmarks alive) */}
        <Route path="/users" element={<Navigate to="/admin/users" replace />} />
        <Route path="/registration" element={<Navigate to="/admin/users?tab=requests" replace />} />
        <Route path="/admin/staff" element={<Navigate to="/admin/users?tab=staff" replace />} />
        <Route path="/admin/type-labels" element={<Navigate to="/admin/properties?tab=type-labels" replace />} />
        <Route path="/admin/blocked-dates" element={<Navigate to="/admin/properties?tab=blocked-dates" replace />} />
        <Route path="/admin/services" element={<Navigate to="/admin/spa" replace />} />
        <Route path="/admin/service-types" element={<Navigate to="/admin/spa?tab=types" replace />} />
        <Route path="/admin/service-categories" element={<Navigate to="/admin/spa?tab=categories" replace />} />
        <Route path="/admin/spa-locations" element={<Navigate to="/admin/spa?tab=locations" replace />} />
        <Route path="/admin/spa-masters" element={<Navigate to="/admin/spa?tab=masters" replace />} />
        <Route path="/admin/minibar" element={<Navigate to="/admin/shop" replace />} />
        <Route path="/analytics/income" element={<Navigate to="/analytics?tab=income" replace />} />
        <Route path="/analytics/expenses" element={<Navigate to="/analytics?tab=expenses" replace />} />
        <Route path="/analytics/properties" element={<Navigate to="/analytics?tab=properties" replace />} />
        <Route path="/analytics/reports" element={<Navigate to="/analytics?tab=reports" replace />} />

        <Route path="/login" element={<Navigate to="/" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  );
}
