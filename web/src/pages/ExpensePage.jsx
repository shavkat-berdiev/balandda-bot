import { useState, useEffect } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { Search, Download } from 'lucide-react';
import { api } from '../api';
import { formatCurrency, getDateRange, formatDateShort } from '../utils/format';

const mockExpenseData = [
  { id: 1, date: '2026-03-31', category: 'Зарплата', staff: 'Иван Петров', amount: 500000 },
  { id: 2, date: '2026-03-31', category: 'Коммунальные услуги', staff: 'Система', amount: 350000 },
  { id: 3, date: '2026-03-30', category: 'Продукты', staff: 'Шеф-повар', amount: 280000 },
  { id: 4, date: '2026-03-30', category: 'Техническое обслуживание', staff: 'Сервис', amount: 150000 },
  { id: 5, date: '2026-03-29', category: 'Зарплата', staff: 'Мария Сидорова', amount: 450000 },
  { id: 6, date: '2026-03-29', category: 'Интернет и телефония', staff: 'Система', amount: 85000 },
  { id: 7, date: '2026-03-28', category: 'Маркетинг', staff: 'Отдел маркетинга', amount: 200000 },
  { id: 8, date: '2026-03-28', category: 'Страховка', staff: 'Система', amount: 320000 },
  { id: 9, date: '2026-03-27', category: 'Производство', staff: 'Хозяйство', amount: 180000 },
];

const categories = ['Все категории', 'Зарплата', 'Коммунальные услуги', 'Продукты', 'Техническое обслуживание', 'Маркетинг', 'Интернет и телефония', 'Страховка', 'Производство'];

const COLORS = ['#2d8c5a', '#1a5676', '#f59e0b', '#dc2626', '#6b7280', '#ec4899', '#8b5cf6', '#06b6d4', '#f59e0b'];

export default function ExpensePage({ dateRange = 'month' }) {
  const [expenseData, setExpenseData] = useState(mockExpenseData);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState('Все категории');
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        // Try to fetch real data
        const { from, to } = getDateRange(dateRange);
        try {
          const reports = await api.getDailyReports(from, to);
          if (reports && reports.expenses) {
            setExpenseData(reports.expenses);
          }
        } catch (apiError) {
          console.log('Using mock data');
        }
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [dateRange]);

  const filteredData = expenseData.filter((item) => {
    const matchCategory = filterCategory === 'Все категории' || item.category === filterCategory;
    const matchSearch =
      searchText === '' ||
      item.category.toLowerCase().includes(searchText.toLowerCase()) ||
      item.staff.toLowerCase().includes(searchText.toLowerCase()) ||
      item.date.includes(searchText);
    return matchCategory && matchSearch;
  });

  // Group by category for pie chart
  const categoryTotals = filteredData.reduce((acc, item) => {
    const existing = acc.find((c) => c.name === item.category);
    if (existing) {
      existing.value += item.amount;
    } else {
      acc.push({ name: item.category, value: item.amount });
    }
    return acc;
  }, []);

  const totalExpense = filteredData.reduce((sum, item) => sum + item.amount, 0);
  const itemCount = filteredData.length;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Фильтры</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Категория</label>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Поиск</label>
            <div className="relative">
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Поиск по категории или сотруднику..."
                className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
              />
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pie Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Распределение расходов
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={categoryTotals}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {categoryTotals.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(value)} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Summary Stats */}
        <div className="lg:col-span-2 bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Статистика расходов
          </h3>
          <div className="space-y-4">
            {categoryTotals.slice(0, 6).map((category, index) => {
              const percentage = (category.value / totalExpense) * 100;
              return (
                <div key={category.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-700">
                      {category.name}
                    </span>
                    <span className="text-sm font-semibold text-gray-900">
                      {formatCurrency(category.value)}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-red-500 h-2 rounded-full"
                      style={{ width: `${percentage}%` }}
                    ></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Details Table */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">Детали расходов</h3>
          <button className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-700 hover:bg-red-100 rounded-lg font-medium transition-colors">
            <Download size={18} />
            Экспорт
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Дата
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Категория
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Ответственный
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Сумма
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredData.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {formatDateShort(item.date)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {item.category}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {item.staff}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-right text-red-600">
                    -{formatCurrency(item.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary Footer */}
      <div className="bg-white rounded-lg shadow p-6 border-t-4 border-red-500">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">Всего операций: {itemCount}</p>
            <p className="text-sm text-gray-600 mt-1">Всего расходы:</p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-red-600">
              -{formatCurrency(totalExpense)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
