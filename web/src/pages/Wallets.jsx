import { useState, useEffect } from 'react';
import { api } from '../api';

const TX_TYPE_COLORS = {
  CASH_IN: { bg: 'bg-green-100', text: 'text-green-800' },
  TRANSFER_TO_EMPLOYEE: { bg: 'bg-blue-100', text: 'text-blue-800' },
  TRANSFER_TO_SHAVKAT: { bg: 'bg-purple-100', text: 'text-purple-800' },
  CASH_TO_BANK: { bg: 'bg-gray-100', text: 'text-gray-800' },
};

function formatAmount(n) {
  return Number(n).toLocaleString('ru-RU').replace(/,/g, ' ');
}

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function Wallets() {
  const [wallets, setWallets] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [txLoading, setTxLoading] = useState(false);
  const [filterUser, setFilterUser] = useState('');
  const [filterType, setFilterType] = useState('');

  useEffect(() => {
    loadWallets();
    loadTransactions();
  }, []);

  useEffect(() => {
    loadTransactions();
  }, [filterUser, filterType]);

  async function loadWallets() {
    try {
      const data = await api.getWalletsList();
      setWallets(data.wallets || []);
    } catch (err) {
      console.error('Failed to load wallets:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadTransactions() {
    setTxLoading(true);
    try {
      const params = {};
      if (filterUser) params.telegram_id = filterUser;
      if (filterType) params.transaction_type = filterType;
      const data = await api.getWalletsTransactions(params);
      setTransactions(data.transactions || []);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    } finally {
      setTxLoading(false);
    }
  }

  const totalCash = wallets.reduce((sum, w) => sum + w.balance, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Кошельки</h1>
      </div>

      {/* Summary card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="text-sm text-gray-500 mb-1">Общая касса (наличные на руках)</div>
        <div className="text-3xl font-bold text-gray-900">{formatAmount(totalCash)} UZS</div>
      </div>

      {/* Wallet balances grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {wallets.map((w) => (
          <div
            key={w.telegram_id}
            className={`bg-white rounded-xl shadow-sm border p-5 cursor-pointer transition hover:shadow-md ${
              filterUser === String(w.telegram_id) ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'
            }`}
            onClick={() => setFilterUser(
              filterUser === String(w.telegram_id) ? '' : String(w.telegram_id)
            )}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
                {w.full_name?.charAt(0) || '?'}
              </div>
              <div>
                <div className="font-medium text-gray-900">{w.full_name}</div>
                <div className="text-xs text-gray-500">{w.role}</div>
              </div>
            </div>
            <div className={`text-xl font-bold ${w.balance >= 0 ? 'text-green-700' : 'text-red-600'}`}>
              {formatAmount(w.balance)} UZS
            </div>
          </div>
        ))}
      </div>

      {/* Transaction history */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between flex-wrap gap-3">
          <h2 className="text-lg font-semibold text-gray-900">История операций</h2>
          <div className="flex gap-2">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="text-sm border border-gray-300 rounded-lg px-3 py-1.5"
            >
              <option value="">Все типы</option>
              <option value="CASH_IN">Приход наличных</option>
              <option value="TRANSFER_TO_EMPLOYEE">Передача сотруднику</option>
              <option value="TRANSFER_TO_SHAVKAT">Передано Шавкату</option>
              <option value="CASH_TO_BANK">Сдано в банк</option>
            </select>
            {filterUser && (
              <button
                onClick={() => setFilterUser('')}
                className="text-sm text-blue-600 hover:text-blue-800 px-2"
              >
                Сбросить фильтр
              </button>
            )}
          </div>
        </div>

        {txLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : transactions.length === 0 ? (
          <div className="text-center text-gray-400 py-12">Нет операций</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="px-6 py-3 font-medium">Дата</th>
                  <th className="px-6 py-3 font-medium">Тип</th>
                  <th className="px-6 py-3 font-medium">Отправитель</th>
                  <th className="px-6 py-3 font-medium">Получатель</th>
                  <th className="px-6 py-3 font-medium text-right">Сумма</th>
                  <th className="px-6 py-3 font-medium">Комментарий</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {transactions.map((tx) => {
                  const colors = TX_TYPE_COLORS[tx.transaction_type] || TX_TYPE_COLORS.CASH_IN;
                  return (
                    <tr key={tx.id} className="hover:bg-gray-50">
                      <td className="px-6 py-3 text-gray-600 whitespace-nowrap">
                        {formatDateTime(tx.created_at)}
                      </td>
                      <td className="px-6 py-3">
                        <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
                          {tx.transaction_type_label}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-900">{tx.sender_name}</td>
                      <td className="px-6 py-3 text-gray-600">{tx.receiver_name}</td>
                      <td className="px-6 py-3 text-right font-medium text-gray-900 whitespace-nowrap">
                        {formatAmount(tx.amount)} UZS
                      </td>
                      <td className="px-6 py-3 text-gray-500 max-w-[200px] truncate">
                        {tx.note || ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
