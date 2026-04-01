import { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp, Download, CheckCircle, Clock } from 'lucide-react';
import { api } from '../api';
import { formatCurrency, getDateRange, formatDate } from '../utils/format';

const mockReports = [
  {
    id: 1,
    date: '2026-03-31',
    status: 'completed',
    type: 'text-imported',
    totalIncome: 7800000,
    totalExpense: 1500000,
    itemsCount: 24,
    expanded: false,
    details: {
      properties: ['Люкс Suite', 'Deluxe Room', 'Standard Room', 'Вилла'],
      paymentMethods: ['Наличные', 'Карта', 'Банковский перевод'],
      categories: ['Зарплата', 'Коммунальные услуги', 'Продукты'],
    },
  },
  {
    id: 2,
    date: '2026-03-30',
    status: 'completed',
    type: 'structured',
    totalIncome: 8100000,
    totalExpense: 1800000,
    itemsCount: 28,
    expanded: false,
    details: {
      properties: ['Люкс Suite', 'Deluxe Room', 'Вилла'],
      paymentMethods: ['Карта', 'Банковский перевод'],
      categories: ['Зарплата', 'Техническое обслуживание'],
    },
  },
  {
    id: 3,
    date: '2026-03-29',
    status: 'completed',
    type: 'text-imported',
    totalIncome: 6500000,
    totalExpense: 1300000,
    itemsCount: 20,
    expanded: false,
    details: {
      properties: ['Люкс Suite', 'Deluxe Room', 'Standard Room'],
      paymentMethods: ['Наличные', 'Карта'],
      categories: ['Зарплата', 'Продукты', 'Маркетинг'],
    },
  },
  {
    id: 4,
    date: '2026-03-28',
    status: 'completed',
    type: 'structured',
    totalIncome: 7200000,
    totalExpense: 1600000,
    itemsCount: 26,
    expanded: false,
    details: {
      properties: ['Люкс Suite', 'Вилла', 'Ресторан'],
      paymentMethods: ['Карта', 'Онлайн'],
      categories: ['Зарплата', 'Коммунальные услуги', 'Страховка'],
    },
  },
  {
    id: 5,
    date: '2026-03-27',
    status: 'completed',
    type: 'text-imported',
    totalIncome: 4800000,
    totalExpense: 1100000,
    itemsCount: 16,
    expanded: false,
    details: {
      properties: ['Deluxe Room', 'Standard Room'],
      paymentMethods: ['Наличные'],
      categories: ['Производство', 'Интернет и телефония'],
    },
  },
  {
    id: 6,
    date: '2026-03-26',
    status: 'completed',
    type: 'structured',
    totalIncome: 6100000,
    totalExpense: 1400000,
    itemsCount: 22,
    expanded: false,
    details: {
      properties: ['Люкс Suite', 'Deluxe Room', 'СПА'],
      paymentMethods: ['Карта', 'Банковский перевод', 'Онлайн'],
      categories: ['Зарплата', 'Продукты'],
    },
  },
];

export default function ReportsPage({ dateRange = 'month' }) {
  const [reports, setReports] = useState(mockReports);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const { from, to } = getDateRange(dateRange);

        // Try to fetch real data
        try {
          const data = await api.getDailyReports(from, to);
          if (data && data.data) {
            setReports(data.data);
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

  const toggleExpanded = (id) => {
    setReports(
      reports.map((r) =>
        r.id === id ? { ...r, expanded: !r.expanded } : r
      )
    );
  };

  const getTypeLabel = (type) => {
    return type === 'structured' ? 'Структурированный' : 'Текст-импорт';
  };

  const getTypeColor = (type) => {
    return type === 'structured'
      ? 'bg-blue-50 text-blue-700 border-blue-200'
      : 'bg-amber-50 text-amber-700 border-amber-200';
  };

  const netProfit = (income, expense) => income - expense;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">
          Сводка отчётов
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-600">Всего отчётов</p>
            <p className="text-2xl font-bold text-gray-800">{reports.length}</p>
          </div>
          <div className="text-center p-4 bg-green-50 rounded-lg">
            <p className="text-sm text-gray-600">Всего доход</p>
            <p className="text-2xl font-bold text-green-700">
              {formatCurrency(reports.reduce((sum, r) => sum + r.totalIncome, 0))}
            </p>
          </div>
          <div className="text-center p-4 bg-red-50 rounded-lg">
            <p className="text-sm text-gray-600">Всего расходы</p>
            <p className="text-2xl font-bold text-red-700">
              -{formatCurrency(reports.reduce((sum, r) => sum + r.totalExpense, 0))}
            </p>
          </div>
          <div className="text-center p-4 bg-blue-50 rounded-lg">
            <p className="text-sm text-gray-600">Чистая прибыль</p>
            <p className="text-2xl font-bold text-blue-700">
              {formatCurrency(
                reports.reduce((sum, r) => sum + (r.totalIncome - r.totalExpense), 0)
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Reports List */}
      <div className="space-y-4">
        {reports.map((report) => (
          <div
            key={report.id}
            className="bg-white rounded-lg shadow overflow-hidden hover:shadow-lg transition-shadow"
          >
            {/* Report Header */}
            <button
              onClick={() => toggleExpanded(report.id)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
            >
              <div className="flex-1 text-left">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-semibold text-gray-800">
                    Отчёт за {formatDate(report.date)}
                  </h3>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium border ${getTypeColor(
                      report.type
                    )}`}
                  >
                    {getTypeLabel(report.type)}
                  </span>
                  <div className="flex items-center gap-1 text-green-700">
                    <CheckCircle size={16} />
                    <span className="text-sm font-medium">Завершено</span>
                  </div>
                </div>
                <p className="text-sm text-gray-600">
                  {report.itemsCount} записей
                </p>
              </div>

              <div className="flex items-center gap-8">
                <div className="text-right">
                  <p className="text-sm text-gray-600">Доход</p>
                  <p className="text-lg font-bold text-green-600">
                    {formatCurrency(report.totalIncome)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600">Расходы</p>
                  <p className="text-lg font-bold text-red-600">
                    -{formatCurrency(report.totalExpense)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600">Прибыль</p>
                  <p className="text-lg font-bold text-blue-600">
                    {formatCurrency(netProfit(report.totalIncome, report.totalExpense))}
                  </p>
                </div>

                <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                  {report.expanded ? (
                    <ChevronUp size={20} />
                  ) : (
                    <ChevronDown size={20} />
                  )}
                </button>
              </div>
            </button>

            {/* Expanded Details */}
            {report.expanded && (
              <div className="border-t border-gray-200 px-6 py-4 bg-gray-50">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-3">Объекты</h4>
                    <div className="space-y-2">
                      {report.details.properties.map((prop) => (
                        <div
                          key={prop}
                          className="text-sm text-gray-700 px-3 py-2 bg-white rounded border border-gray-200"
                        >
                          {prop}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-3">
                      Способы оплаты
                    </h4>
                    <div className="space-y-2">
                      {report.details.paymentMethods.map((method) => (
                        <div
                          key={method}
                          className="text-sm text-gray-700 px-3 py-2 bg-white rounded border border-gray-200"
                        >
                          {method}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="font-semibold text-gray-800 mb-3">Категории</h4>
                    <div className="space-y-2">
                      {report.details.categories.map((cat) => (
                        <div
                          key={cat}
                          className="text-sm text-gray-700 px-3 py-2 bg-white rounded border border-gray-200"
                        >
                          {cat}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex gap-3">
                  <button className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 font-medium transition-colors">
                    <Download size={18} />
                    Скачать отчёт
                  </button>
                  <button className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 font-medium transition-colors">
                    Подробнее
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
