import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Categories from './pages/Categories';
import Users from './pages/Users';
import Transactions from './pages/Transactions';
import Analytics from './pages/Analytics';
import AdminProperties from './pages/AdminProperties';
import AdminServices from './pages/AdminServices';
import AdminMinibar from './pages/AdminMinibar';
import AdminStaff from './pages/AdminStaff';
import AdminReports from './pages/AdminReports';
import Prepayments from './pages/Prepayments';
import Wallets from './pages/Wallets';
import RegistrationRequests from './pages/RegistrationRequests';

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

  return (
    <Layout user={user} onLogout={handleLogout}>
      <Routes>
        <Route path="/" element={<Dashboard user={user} />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/users" element={<Users />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/analytics/*" element={<Analytics user={user} onLogout={handleLogout} />} />
        <Route path="/admin/properties" element={<AdminProperties />} />
        <Route path="/admin/services" element={<AdminServices />} />
        <Route path="/admin/minibar" element={<AdminMinibar />} />
        <Route path="/admin/staff" element={<AdminStaff />} />
        <Route path="/admin/reports" element={<AdminReports user={user} />} />
        <Route path="/prepayments" element={<Prepayments />} />
        <Route path="/wallets" element={<Wallets />} />
        <Route path="/registration" element={<RegistrationRequests />} />
        <Route path="/login" element={<Navigate to="/" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  );
}
