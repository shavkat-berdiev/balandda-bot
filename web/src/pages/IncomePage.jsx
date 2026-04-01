import { useState, useEffect } from 'react';
import { Search, Download } from 'lucide-react';
import { api } from '../api';
import { formatCurrency, getDateRange, formatDateShort } from '../utils/format';

const mockIncomeData = [
  { id: 1, date: '2026-03-31', property: 'Люкс Suite', type: 'room', method: 'Карта', amount: 2500000 },
  { id: 2, date: '2026-03-31', property: 'Deluxe Room', type: 'room', method: 'Наличные', amount: 1800000 },
  { id: 3, date: '2026-03-30', property: 'Вилла', type: 'villa', method: 'Банковский перевод', amount: 3500000 },
  { id: 4, date: '2026-03-30', property: 'Standard Room', type: 'room', method: 'Онлайн', amount: 1200000 },
  { id: 5, date: '2026-03-29', property: 'Люкс Suite', type: 'room', method: 'Карта', amount: 2500000 },
  { id: 6, date: '2026-03-29', property: 'Ресторан', type: 'restaurant', method: 'Наличные', amount: 850000 },
  { id: 7, date: '2026-03-28', property: 'Deluxe Room', type: 'room', method: 'Банковский перевод', amount: 1800000 },
  { id: 8, date: '2026-03-28', property: 'СПА', type: 'spa', method: 'Карта', amount: 620000 },
];

const propertyTypes = {
  room: 'Номер',
  villa: 'Вилла',
  restaurant: 'Ресторан',
  spa: 'СПА',
};

const paymentMethods = ['Все методы', 'Наличные', 'Карта', 'Банковский перевод', 'Онлайн'];
const properties = ['Все объекты', 'Люкс Suite', 'Deluxe Room', 'Standard Room', 'Вилла', 'Ресторан', 'СПА'];

export default function IncomePage({ dateRange = 'month' }) {
  const [incomeData, setIncomeData] = useState(mockIncomeData);
  const [loading, setLoading] = useState(true);
  const [filterProperty, setFilterProperty] = useState('Все объекты');
  const [filterMethod, setFilterMethod] = useState('Все методы');
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        // Try to fetch real data
        const { from, to } = getDateRange(dateRange);
        try {
          const reports = await api.getDailyReports(from, to);
          if (reports && reports.data) {
            // Transform API response if needed
            setIncomeData(reports.data);
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

  const filteredData = incomeData.filter((item) => {
    const matchProperty = filterProperty === 'Все объекты' || item.property === filterProperty;
    const matchMethod = filterMethod === 'Все методы' || item.method === filterMethod;
    const matchSearch =
      searchText === '' ||
      item.property.toLowerCase().includes(searchText.toLowerCase()) ||
      item.date.includes(searchText);
    return matchProperty && matchMethod && matchSearch;
  });

  const totalIncome = filteredData.reduce((sum, item) => sum + item.amount, 0);
  const itemCount = filteredData.length;

  const groupedByProperty = filteredData.reduce((acc, item) => {
    const existing = acc.find((g) => g.property === item.property);
    if (existing) {
      existing.amount += item.amount;
      existing.count += 1;
    } else {
      acc.push({ property: item.property, amount: item.amount, count: 1 });
    }
    return acc;
  }, []);

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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Объект</label>
            <select
              value={filterProperty}
              onChange={(e) => setFilterProperty(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              {properties.map((prop) => (
                <option key={prop} value={prop}>
                  {prop}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Способ оплаты
            </label>
            <select
              value={filterMethod}
              onChange={(e) => setFilterMethod(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              {paymentMethods.map((method) => (
                <option key={method} value={method}>
                  {method}
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
                placeholder="Поиск..."
                className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
              />
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
            </div>
          </div>
        </div>
      </div>

      {/* Summary by Property */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Сводка по объектам</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Объект
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Операции
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Сумма
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {groupedByProperty.map((group) => (
                <tr key={group.property} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {group.property}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {group.count}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-right text-green-600">
                    {formatCurrency(group.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Details Table */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">Детали доходов</h3>
          <button className="flex items-center gap-2 px-4 py-2 bg-green-50 text-green-700 hover:bg-green-100 rounded-lg font-medium transition-colors">
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
                  Объект
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Тип
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Способ оплаты
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
                    {item.property}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {propertyTypes[item.type] || item.type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {item.method}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-right text-green-600">
                    {formatCurrency(item.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary Footer */}
      <div className="bg-white rounded-lg shadow p-6 border-t-4 border-green-500">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">Всего операций: {itemCount}</p>
            <p className="text-sm text-gray-600 mt-1">Всего доход:</p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-green-600">
              {formatCurrency(totalIncome)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
