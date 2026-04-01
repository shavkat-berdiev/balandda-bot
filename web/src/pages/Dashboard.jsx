import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, DollarSign, ArrowUpDown } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { api } from '../api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];

function formatUZS(amount) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(amount)) + ' UZS';
}

export default function Dashboard() {
  const [section, setSection] = useState('resort');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadReport();
  }, [section]);

  async function loadReport() {
    setLoading(true);
    try {
      const data = await api.getDailyReport(section);
      setReport(data);
    } catch (err) {
      console.error('Failed to load report:', err);
    }
    setLoading(false);
  }

  const inCategories = report?.categories?.filter(c => c.type === 'cash_in') || [];
  const outCategories = report?.categories?.filter(c => c.type === 'cash_out') || [];

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Today's overview</p>
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
            Resort
          </button>
          <button
            onClick={() => setSection('restaurant')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              section === 'restaurant'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            Restaurant
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <SummaryCard
              title="Cash In"
              value={formatUZS(report?.total_in || 0)}
              icon={TrendingUp}
              color="green"
            />
            <SummaryCard
              title="Cash Out"
              value={formatUZS(report?.total_out || 0)}
              icon={TrendingDown}
              color="red"
            />
            <SummaryCard
              title="Net"
              value={formatUZS(report?.net || 0)}
              icon={ArrowUpDown}
              color={(report?.net || 0) >= 0 ? 'blue' : 'red'}
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Income by category */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Income by Category</h2>
              {inCategories.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={inCategories}
                      dataKey="total"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    >
                      {inCategories.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatUZS(v)} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">No income data today</p>
              )}
            </div>

            {/* Expense by category */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Expenses by Category</h2>
              {outCategories.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={outCategories}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                    <Tooltip formatter={(v) => formatUZS(v)} />
                    <Bar dataKey="total" fill="#ef4444" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-gray-400 text-center py-16">No expense data today</p>
              )}
            </div>
          </div>
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
