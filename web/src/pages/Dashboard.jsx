import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, DollarSign, ArrowUpDown, Calendar, FileText } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend, Area, AreaChart,
} from 'recharts';
import { api } from '../api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];

function formatUZS(amount) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(amount)) + ' UZS';
}

function formatShort(amount) {
  if (amount >= 1_000_000) return (amount / 1_000_000).toFixed(1) + 'M';
  if (amount >= 1_000) return (amount / 1_000).toFixed(0) + 'k';
  return String(amount);
}

function getDefaultDates() {
  const today = new Date();
  return {
    from: today.toISOString().split('T')[0],
    to: today.toISOString().split('T')[0],
  };
}

function getPresetRange(preset) {
  const today = new Date();
  const from = new Date(today);
  switch (preset) {
    case 'today':
      break;
    case 'week':
      from.setDate(from.getDate() - 7);
      break;
    case 'month':
      from.setDate(from.getDate() - 30);
      break;
    case 'quarter':
      from.setDate(from.getDate() - 90);
      break;
    default:
      break;
  }
  return {
    from: from.toISOString().split('T')[0],
    to: today.toISOString().split('T')[0],
  };
}

export default function Dashboard() {
  const defaults = getDefaultDates();
  const [section, setSection] = useState('resort');
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [section, dateFrom, dateTo]);

  async function loadData() {
    setLoading(true);
    try {
      const result = await api.getStructuredDashboard(section, dateFrom, dateTo);
      setData(result);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    }
    setLoading(false);
  }

  function applyPreset(preset) {
    const range = getPresetRange(preset);
    setDateFrom(range.from);
    setDateTo(range.to);
  }

  const isMultiDay = dateFrom !== dateTo;

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">
            {dateFrom === dateTo ? 'Сегодня' : `${dateFrom} — ${dateTo}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setSection('resort')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              section === 'resort'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            Курорт
          </button>
          <button
            onClick={() => setSection('restaurant')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              section === 'restaurant'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            Ресторан
          </button>
        </div>
      </div>

      {/* Period selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex gap-1.5">
            {[
              { key: 'today', label: 'Сегодня' },
              { key: 'week', label: '7 дней' },
              { key: 'month', label: '30 дней' },
              { key: 'quarter', label: '90 дней' },
            ].map(p => (
              <button key={p.key} onClick={() => applyPreset(p.key)}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-gray-100 hover:bg-blue-50 hover:text-blue-600 text-gray-600 transition-colors">
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
            <span className="text-gray-400 text-sm">—</span>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : !data ? (
        <div className="text-center py-20 text-gray-400">
          <FileText size={48} className="mx-auto mb-3 opacity-50" />
          <p>Не удалось загрузить данные</p>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <SummaryCard title="Доход" value={formatUZS(data.total_income)} icon={TrendingUp} color="green" />
            <SummaryCard title="Расход" value={formatUZS(data.total_expense)} icon={TrendingDown} color="red" />
            <SummaryCard title="Чистый доход" value={formatUZS(data.net)} icon={ArrowUpDown}
              color={data.net >= 0 ? 'blue' : 'red'} />
            <SummaryCard title="Отчётов" value={String(data.report_count)} icon={FileText} color="purple" />
          </div>

          {/* Row 1: Income pie + Expense bar */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* Income by category */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Доход по категориям</h2>
              {data.income_by_category?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={data.income_by_category}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    >
                      {data.income_by_category.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatUZS(v)} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">Нет данных о доходах</p>
              )}
            </div>

            {/* Expense by category */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Расходы по категориям</h2>
              {data.expense_by_category?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={data.expense_by_category} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={formatShort} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={120} />
                    <Tooltip formatter={(v) => formatUZS(v)} />
                    <Bar dataKey="value" fill="#ef4444" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">Нет данных о расходах</p>
              )}
            </div>
          </div>

          {/* Row 2: Payment methods + Properties */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* Payment methods */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Способы оплаты</h2>
              {data.by_payment_method?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={data.by_payment_method}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={90}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {data.by_payment_method.map((_, i) => (
                        <Cell key={i} fill={COLORS[(i + 2) % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatUZS(v)} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">Нет данных</p>
              )}
            </div>

            {/* By property */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Доход по объектам</h2>
              {data.by_property?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={data.by_property}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-25} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={formatShort} />
                    <Tooltip formatter={(v) => formatUZS(v)} />
                    <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">Нет данных о проживании</p>
              )}
            </div>
          </div>

          {/* Row 3: Daily trend (only show for multi-day range) */}
          {isMultiDay && data.daily_totals?.length > 1 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Тренд по дням</h2>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={data.daily_totals}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }}
                    tickFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={formatShort} />
                  <Tooltip formatter={(v) => formatUZS(v)}
                    labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU')} />
                  <Legend />
                  <Area type="monotone" dataKey="income" name="Доход" stroke="#10b981" fill="#10b98133" strokeWidth={2} />
                  <Area type="monotone" dataKey="expense" name="Расход" stroke="#ef4444" fill="#ef444433" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Row 4: Services breakdown (if any) */}
          {data.by_service?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Доход по услугам</h2>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={data.by_service} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={formatShort} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={120} />
                  <Tooltip formatter={(v) => formatUZS(v)} />
                  <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SummaryCard({ title, value, icon: Icon, color }) {
  const colorMap = {
    green: 'bg-green-50 text-green-600',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-blue-50 text-blue-600',
    purple: 'bg-purple-50 text-purple-600',
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
          <Icon size={20} />
        </div>
      </div>
      <p className="text-xl font-bold text-gray-800">{value}</p>
    </div>
  );
}
