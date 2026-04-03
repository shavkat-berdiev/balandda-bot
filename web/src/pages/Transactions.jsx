import { useState, useEffect } from 'react';
import { Calendar, ArrowLeftRight } from 'lucide-react';
import { api } from '../api';

function formatUZS(amount) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(amount));
}

function getDefaultDates() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 30);
  return {
    from: from.toISOString().split('T')[0],
    to: today.toISOString().split('T')[0],
  };
}

export default function Transactions() {
  const defaults = getDefaultDates();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterUnit, setFilterUnit] = useState('');
  const [filterType, setFilterType] = useState('');
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);

  useEffect(() => { loadTransactions(); }, [filterUnit, filterType, dateFrom, dateTo]);

  async function loadTransactions() {
    setLoading(true);
    setError('');
    try {
      const data = await api.getStructuredTransactions({
        business_unit: filterUnit || undefined,
        entry_type: filterType || undefined,
        start_date: dateFrom,
        end_date: dateTo,
        limit: '200',
      });
      setTransactions(data);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  const totalIncome = transactions.filter(t => t.type === 'income').reduce((s, t) => s + t.amount, 0);
  const totalExpense = transactions.filter(t => t.type === 'expense').reduce((s, t) => s + t.amount, 0);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Транзакции</h1>
          <p className="text-gray-500 text-sm mt-1">Все записи доходов и расходов</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Раздел</label>
            <select value={filterUnit} onChange={e => setFilterUnit(e.target.value)}
              className="px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm">
              <option value="">Все</option>
              <option value="resort">Курорт</option>
              <option value="restaurant">Ресторан</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Тип</label>
            <select value={filterType} onChange={e => setFilterType(e.target.value)}
              className="px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm">
              <option value="">Все</option>
              <option value="income">Доход</option>
              <option value="expense">Расход</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">С</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">По</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
        </div>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <div className="bg-green-50 rounded-lg px-4 py-3 border border-green-100">
          <p className="text-xs text-green-600 font-medium">Доход</p>
          <p className="text-lg font-bold text-green-700">+{formatUZS(totalIncome)} UZS</p>
        </div>
        <div className="bg-red-50 rounded-lg px-4 py-3 border border-red-100">
          <p className="text-xs text-red-600 font-medium">Расход</p>
          <p className="text-lg font-bold text-red-700">-{formatUZS(totalExpense)} UZS</p>
        </div>
        <div className="bg-blue-50 rounded-lg px-4 py-3 border border-blue-100">
          <p className="text-xs text-blue-600 font-medium">Записей</p>
          <p className="text-lg font-bold text-blue-700">{transactions.length}</p>
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Дата</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Тип</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Раздел</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Категория</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Описание</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Оплата</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Сумма (UZS)</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td colSpan="8" className="px-4 py-12 text-center text-gray-400">Загрузка...</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan="8" className="px-4 py-12 text-center text-gray-400">
                  <ArrowLeftRight size={36} className="mx-auto mb-2 opacity-40" />
                  Нет записей за выбранный период
                </td></tr>
              ) : (
                transactions.map(tx => (
                  <tr key={tx.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {new Date(tx.date + 'T00:00:00').toLocaleDateString('ru-RU')}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        tx.type === 'income'
                          ? 'bg-green-50 text-green-700'
                          : 'bg-red-50 text-red-700'
                      }`}>
                        {tx.type === 'income' ? 'Доход' : 'Расход'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                        tx.business_unit === 'resort' ? 'bg-blue-50 text-blue-700' : 'bg-orange-50 text-orange-700'
                      }`}>
                        {tx.business_unit === 'resort' ? 'Курорт' : 'Ресторан'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{tx.category}</td>
                    <td className="px-4 py-3 text-sm text-gray-800 font-medium max-w-xs truncate">{tx.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{tx.payment_method || '—'}</td>
                    <td className={`px-4 py-3 text-sm font-semibold text-right ${
                      tx.type === 'income' ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {tx.type === 'income' ? '+' : '-'}{formatUZS(tx.amount)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs ${
                        tx.status === 'SUBMITTED' ? 'bg-blue-50 text-blue-600' :
                        tx.status === 'APPROVED' ? 'bg-green-50 text-green-600' :
                        'bg-yellow-50 text-yellow-600'
                      }`}>
                        {tx.status === 'SUBMITTED' ? 'Отправлен' :
                         tx.status === 'APPROVED' ? 'Утверждён' : 'Черновик'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
