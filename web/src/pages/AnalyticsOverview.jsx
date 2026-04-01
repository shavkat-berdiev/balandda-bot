import { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { TrendingUp, TrendingDown, DollarSign, Percent } from 'lucide-react';
import { api } from '../api';
import { formatCurrency, getDateRange } from '../utils/format';

// Mock data
const mockDailyData = [
  { date: '2026-03-25', income: 5200000, expense: 1200000 },
  { date: '2026-03-26', income: 6100000, expense: 1400000 },
  { date: '2026-03-27', income: 4800000, expense: 1100000 },
  { date: '2026-03-28', income: 7200000, expense: 1600000 },
  { date: '2026-03-29', income: 6500000, expense: 1300000 },
  { date: '2026-03-30', income: 8100000, expense: 1800000 },
  { date: '2026-03-31', income: 7800000, expense: 1500000 },
];

const mockPaymentMethods = [
  { name: 'Наличные', value: 15200000, color: '#2d8c5a' },
  { name: 'Карта', value: 18500000, color: '#1a5676' },
  { name: 'Банковский перевод', value: 12300000, color: '#f59e0b' },
  { name: 'Онлайн', value: 8700000, color: '#6b7280' },
];

const mockPropertyIncome = [
  { name: 'Люкс Suite', income: 12500000 },
  { name: 'Deluxe Room', income: 18200000 },
  { name: 'Standard Room', income: 14800000 },
  { name: 'Вилла', income: 9200000 },
];

const COLORS = ['#2d8c5a', '#1a5676', '#f59e0b', '#6b7280', '#ec4899'];

export default function AnalyticsOverview({ dateRange = 'month' }) {
  const [data, setData] = useState({
    dailyData: mockDailyData,
    paymentMethods: mockPaymentMethods,
    propertyIncome: mockPropertyIncome,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const { from, to } = getDateRange(dateRange);

        // Try to fetch real data
        try {
          const reports = await api.getDailyReports(from, to);
          const breakdown = await api.getBreakdown(from, to);

          if (reports && breakdown) {
            setData({
              dailyData: reports.data || mockDailyData,
              paymentMethods: breakdown.payment_methods || mockPaymentMethods,
              propertyIncome: breakdown.by_property || mockPropertyIncome,
            });
          }
        } catch (apiError) {
          // Fall back to mock data if API fails
          console.log('Using mock data:', apiError.message);
        }

        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [dateRange]);

  const totalIncome = mockDailyData.reduce((sum, d) => sum + d.income, 0);
  const totalExpense = mockDailyData.reduce((sum, d) => sum + d.expense, 0);
  const netProfit = totalIncome - totalExpense;
  const occupancy = 78; // Mock percentage

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KpiCard
          title="Доход за период"
          value={totalIncome}
          icon={TrendingUp}
          color="green"
        />
        <KpiCard
          title="Расходы"
          value={totalExpense}
          icon={TrendingDown}
          color="red"
        />
        <KpiCard
          title="Чистая прибыль"
          value={netProfit}
          icon={DollarSign}
          color="blue"
        />
        <KpiCard
          title="Заполняемость"
          value={occupancy}
          suffix="%"
          icon={Percent}
          color="amber"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Line Chart */}
        <div className="lg:col-span-2 bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Динамика доходов и расходов
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.dailyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip
                formatter={(value) => formatCurrency(value)}
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '0.5rem',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="income"
                stroke="#2d8c5a"
                name="Доходы"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="expense"
                stroke="#dc2626"
                name="Расходы"
                strokeWidth={2}
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Pie Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            По методам оплаты
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={data.paymentMethods}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {data.paymentMethods.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(value)} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bar Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">
          Доход по типам объектов
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data.propertyIncome}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" stroke="#6b7280" />
            <YAxis stroke="#6b7280" />
            <Tooltip
              formatter={(value) => formatCurrency(value)}
              contentStyle={{
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '0.5rem',
              }}
            />
            <Bar dataKey="income" fill="#2d8c5a" name="Доход" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          <p>Ошибка при загрузке данных: {error}</p>
        </div>
      )}
    </div>
  );
}

function KpiCard({ title, value, suffix = '', icon: Icon, color }) {
  const colorClasses = {
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
  };

  const iconBgClasses = {
    green: 'bg-green-100 text-green-600',
    red: 'bg-red-100 text-red-600',
    blue: 'bg-blue-100 text-blue-600',
    amber: 'bg-amber-100 text-amber-600',
  };

  return (
    <div className={`rounded-lg border p-6 ${colorClasses[color]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600 mb-1">{title}</p>
          <p className="text-2xl font-bold">
            {suffix ? value : formatCurrency(value)}
            {suffix}
          </p>
        </div>
        <div className={`rounded-lg p-3 ${iconBgClasses[color]}`}>
          <Icon size={24} />
        </div>
      </div>
    </div>
  );
}
