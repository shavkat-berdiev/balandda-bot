import { useState } from 'react';
import { BarChart3, TrendingUp, TrendingDown, Grid3x3, FileText, Calendar } from 'lucide-react';
import Tabs from '../components/Tabs';
import AnalyticsOverview from './AnalyticsOverview';
import IncomePage from './IncomePage';
import ExpensePage from './ExpensePage';
import PropertiesPage from './PropertiesPage';
import ReportsPage from './ReportsPage';

const dateRangeOptions = [
  { label: 'Сегодня', value: 'today' },
  { label: 'Неделя', value: 'week' },
  { label: 'Месяц', value: 'month' },
  { label: 'Произвольный', value: 'custom' },
];

/**
 * Финансовая аналитика — was previously a nested sub-app wrapped in its own
 * DashboardLayout, which rendered a second sidebar inside the main one and so
 * never appeared in the menu. Now a single tabbed page inside the main Layout.
 * DashboardLayout.jsx is left on disk unrouted for rollback.
 */
export default function Analytics() {
  const [dateRange, setDateRange] = useState('month');
  const [showDatePicker, setShowDatePicker] = useState(false);
  const rangeLabel = dateRangeOptions.find((o) => o.value === dateRange)?.label || dateRange;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Финансовая аналитика</h1>
          <p className="text-gray-500 text-sm mt-1">Доходы, расходы и сводные отчёты по объектам</p>
        </div>
        <div className="relative">
          <button
            onClick={() => setShowDatePicker(!showDatePicker)}
            className="flex items-center gap-2 px-4 py-2 bg-white hover:bg-gray-50 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 transition-colors"
          >
            <Calendar size={18} />
            {rangeLabel}
          </button>
          {showDatePicker && (
            <div className="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
              {dateRangeOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => {
                    setDateRange(option.value);
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

      <Tabs
        tabs={[
          { key: 'overview', label: 'Обзор', icon: BarChart3, render: () => <AnalyticsOverview dateRange={dateRange} /> },
          { key: 'income', label: 'Доходы', icon: TrendingUp, render: () => <IncomePage dateRange={dateRange} /> },
          { key: 'expenses', label: 'Расходы', icon: TrendingDown, render: () => <ExpensePage dateRange={dateRange} /> },
          { key: 'properties', label: 'По объектам', icon: Grid3x3, render: () => <PropertiesPage dateRange={dateRange} /> },
          { key: 'reports', label: 'Сводные отчёты', icon: FileText, render: () => <ReportsPage dateRange={dateRange} /> },
        ]}
      />
    </div>
  );
}
