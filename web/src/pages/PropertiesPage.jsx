import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Home, Calendar } from 'lucide-react';
import { api } from '../api';
import { formatCurrency, getDateRange } from '../utils/format';

const mockProperties = [
  {
    id: 1,
    name: 'Люкс Suite',
    type: 'Люкс',
    status: 'occupied',
    monthRevenue: 7500000,
    occupancyRate: 95,
  },
  {
    id: 2,
    name: 'Deluxe Room 101',
    type: 'Делюкс',
    status: 'occupied',
    monthRevenue: 4200000,
    occupancyRate: 87,
  },
  {
    id: 3,
    name: 'Deluxe Room 102',
    type: 'Делюкс',
    status: 'free',
    monthRevenue: 3800000,
    occupancyRate: 78,
  },
  {
    id: 4,
    name: 'Standard Room 201',
    type: 'Стандарт',
    status: 'occupied',
    monthRevenue: 2100000,
    occupancyRate: 65,
  },
  {
    id: 5,
    name: 'Standard Room 202',
    type: 'Стандарт',
    status: 'occupied',
    monthRevenue: 1950000,
    occupancyRate: 61,
  },
  {
    id: 6,
    name: 'Вилла Alpha',
    type: 'Вилла',
    status: 'free',
    monthRevenue: 12000000,
    occupancyRate: 88,
  },
];

const mockOccupancyData = [
  { date: '2026-03-25', occupied: 5, free: 1 },
  { date: '2026-03-26', occupied: 5, free: 1 },
  { date: '2026-03-27', occupied: 4, free: 2 },
  { date: '2026-03-28', occupied: 6, free: 0 },
  { date: '2026-03-29', occupied: 5, free: 1 },
  { date: '2026-03-30', occupied: 6, free: 0 },
  { date: '2026-03-31', occupied: 5, free: 1 },
];

const mockRevenueData = [
  { property: 'Люкс Suite', revenue: 7500000 },
  { property: 'Вилла Alpha', revenue: 12000000 },
  { property: 'Deluxe Room 101', revenue: 4200000 },
  { property: 'Deluxe Room 102', revenue: 3800000 },
  { property: 'Standard 201', revenue: 2100000 },
  { property: 'Standard 202', revenue: 1950000 },
];

export default function PropertiesPage({ dateRange = 'month' }) {
  const [properties, setProperties] = useState(mockProperties);
  const [occupancyData, setOccupancyData] = useState(mockOccupancyData);
  const [revenueData, setRevenueData] = useState(mockRevenueData);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const { from, to } = getDateRange(dateRange);

        // Try to fetch real data
        try {
          const props = await api.getProperties();
          if (props) {
            setProperties(props);
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

  const totalOccupancyRate =
    Math.round(
      (occupancyData.reduce((sum, d) => sum + d.occupied, 0) /
        occupancyData.reduce((sum, d) => sum + d.occupied + d.free, 0)) *
        100
    ) || 0;

  const totalRevenue = properties.reduce((sum, p) => sum + p.monthRevenue, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-blue-500">
          <p className="text-sm text-gray-600 mb-1">Всего объектов</p>
          <p className="text-3xl font-bold text-gray-800">{properties.length}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-green-500">
          <p className="text-sm text-gray-600 mb-1">Среднее заполнение</p>
          <p className="text-3xl font-bold text-gray-800">{totalOccupancyRate}%</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6 border-l-4 border-amber-500">
          <p className="text-sm text-gray-600 mb-1">Доход в месяц</p>
          <p className="text-3xl font-bold text-gray-800">{formatCurrency(totalRevenue)}</p>
        </div>
      </div>

      {/* Properties Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {properties.map((property) => (
          <div
            key={property.id}
            className="bg-white rounded-lg shadow hover:shadow-lg transition-shadow overflow-hidden"
          >
            <div
              className={`h-24 ${
                property.status === 'occupied'
                  ? 'bg-green-50 border-b border-green-200'
                  : 'bg-gray-50 border-b border-gray-200'
              } flex items-center justify-center`}
            >
              <Home size={40} className={property.status === 'occupied' ? 'text-green-600' : 'text-gray-400'} />
            </div>
            <div className="p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-1">{property.name}</h3>
              <p className="text-sm text-gray-600 mb-4">{property.type}</p>

              <div className="space-y-3 mb-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Статус:</span>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      property.status === 'occupied'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {property.status === 'occupied' ? 'Занято' : 'Свободно'}
                  </span>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-600">Заполняемость:</span>
                    <span className="text-sm font-semibold text-gray-800">
                      {property.occupancyRate}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-green-500 h-2 rounded-full"
                      style={{ width: `${property.occupancyRate}%` }}
                    ></div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                  <span className="text-sm text-gray-600">Доход месяца:</span>
                  <span className="text-sm font-bold text-green-600">
                    {formatCurrency(property.monthRevenue)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Доход по объектам
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={revenueData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" stroke="#6b7280" />
              <YAxis dataKey="property" type="category" width={120} stroke="#6b7280" />
              <Tooltip
                formatter={(value) => formatCurrency(value)}
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '0.5rem',
                }}
              />
              <Bar dataKey="revenue" fill="#2d8c5a" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Occupancy Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Тренд заполняемости
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={occupancyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '0.5rem',
                }}
              />
              <Bar dataKey="occupied" fill="#2d8c5a" name="Занято" />
              <Bar dataKey="free" fill="#e5e7eb" name="Свободно" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detailed Table */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">
          Подробная информация
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Объект
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Тип
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Статус
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Заполняемость
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Доход месяца
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {properties.map((property) => (
                <tr key={property.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {property.name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {property.type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        property.status === 'occupied'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {property.status === 'occupied' ? 'Занято' : 'Свободно'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {property.occupancyRate}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-right text-green-600">
                    {formatCurrency(property.monthRevenue)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
