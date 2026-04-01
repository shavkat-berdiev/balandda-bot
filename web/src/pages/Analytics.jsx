import { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import AnalyticsOverview from './AnalyticsOverview';
import IncomePage from './IncomePage';
import ExpensePage from './ExpensePage';
import PropertiesPage from './PropertiesPage';
import ReportsPage from './ReportsPage';

export default function Analytics({ user, onLogout }) {
  const [dateRange, setDateRange] = useState('month');

  return (
    <DashboardLayout
      user={user}
      onLogout={onLogout}
      dateRange={dateRange}
      onDateRangeChange={setDateRange}
    >
      <Routes>
        <Route path="/" element={<AnalyticsOverview dateRange={dateRange} />} />
        <Route path="/income" element={<IncomePage dateRange={dateRange} />} />
        <Route path="/expenses" element={<ExpensePage dateRange={dateRange} />} />
        <Route path="/properties" element={<PropertiesPage dateRange={dateRange} />} />
        <Route path="/reports" element={<ReportsPage dateRange={dateRange} />} />
        <Route path="*" element={<Navigate to="/analytics" />} />
      </Routes>
    </DashboardLayout>
  );
}
