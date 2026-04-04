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

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split('T')[0];
}

function today() {
  return new Date().toISOString().split('T')[0];
}

const PRESETS = [
  { key: 'today', label: 'Сегодня', from: () => today(), to: () => today() },
  { key: '7d', label: '7 дней', from: () => daysAgo(7), to: () => today() },
  { key: '30d', label: '30 дней', from: () => daysAgo(30), to: () => today() },
  { key: '90d', label: '90 дней', from: () => daysAgo(90), to: () => today() },
];

export default function Dashboard() {
  const [section, setSection] = useState('RESORT');
  const [activePreset, setActivePreset] = useState('7d');
  const [dateFrom, setDateFrom] = useState(daysAgo(7));
  const [dateTo, setDateTo] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Separate trend data for the always-visible charts
  const [trend7, setTrend7] = useState([]);
  const [trend30, setTrend30] = useState([]);

  useEffect(() => {
    loadData();
  }, [section, dateFrom, dateTo]);

  // Load 7-day and 30-day trends on section change
  useEffect(() => {
    loadTrends();
  }, [section]);

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

  async function loadTrends() {
    try {
      const [d7, d30] = await Promise.all([
        api.getStructuredDashboard(section, daysAgo(7), today()),
        api.getStructuredDashboard(section, daysAgo(30), today()),
      ]);
      setTrend7(d7.daily_totals || []);
      setTrend30(d30.daily_totals || []);
    } catch (err) {
      console.error('Failed to load trends:', err);
    }
  }

  function applyPreset(key) {
    const preset = PRESETS.find(p => p.key === key);
    if (preset) {
      setActivePreset(key);
      setDateFrom(preset.from());
      setDateTo(preset.to());
    }
  }

  function handleCustomDate(from, to) {
    setActivePreset('custom');
    setDateFrom(from);
    setDateTo(to);
  }

  const periodLabel = activePreset === 'today' ? 'Сегодня'
    : activePreset === '7d' ? 'Последние 7 дней'
    : activePreset === '30d' ? 'Последние 30 дней'
    : activePreset === '90d' ? 'Последние 90 дней'
    : `${dateFrom} — ${dateTo}`;

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">{periodLabel}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setSection('RESORT')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              section === 'RESORT'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            Курорт
          </button>
          <button
            onClick={() => setSection('RESTAURANT')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              section === 'RESTAURANT'
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
            {PRESETS.map(p => (
              <button key={p.key} onClick={() => applyPreset(p.key)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activePreset === p.key
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 hover:bg-blue-50 hover:text-blue-600 text-gray-600'
                }`}>
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <input type="date" value={dateFrom}
              onChange={e => handleCustomDate(e.target.value, dateTo)}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
            <span className="text-gray-400 text-sm">—</span>
            <input type="date" value={dateTo}
              onChange={e => handleCustomDate(dateFrom, e.target.value)}
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
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Доход по категориям</h2>
              {data.income_by_category?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={data.income_by_category} dataKey="value" nameKey="name"
                      cx="50%" cy="50%" outerRadius={90}
                      label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}>
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
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Способы оплаты</h2>
              {data.by_payment_method?.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={data.by_payment_method} dataKey="value" nameKey="name"
                      cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
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

          {/* Services breakdown */}
          {data.by_service?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
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

      {/* Always-visible trend charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <TrendChart title="Тренд за 7 дней" data={trend7} />
        <TrendChart title="Тренд за 30 дней" data={trend30} />
      </div>
    </div>
  );
}

function TrendChart({ title, data }) {
  const hasData = data && data.length > 0;
  const hasValues = hasData && data.some(d => d.income > 0 || d.expense > 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">{title}</h2>
      {hasValues ? (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }}
              tickFormatter={d => {
                const dt = new Date(d + 'T00:00:00');
                return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
              }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={formatShort} />
            <Tooltip formatter={(v) => formatUZS(v)}
              labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU')} />
            <Legend />
            <Line type="monotone" dataKey="income" name="Доход" stroke="#10b981"
              strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            <Line type="monotone" dataKey="expense" name="Расход" stroke="#ef4444"
              strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-gray-400 text-center py-16">Нет данных за этот период</p>
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
