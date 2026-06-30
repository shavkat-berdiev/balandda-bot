import { useState, useEffect, useMemo } from 'react';
import { api } from '../api';

const ACTION_LABELS = {
  created: 'Создано', updated: 'Изменено', cancelled: 'Отменено',
  restored: 'Восстановлено', deleted: 'Удалено навсегда', payment: 'Оплата', auto: 'Авто',
};
const ACTION_STYLE = {
  created: 'bg-green-100 text-green-700',
  updated: 'bg-blue-100 text-blue-700',
  cancelled: 'bg-amber-100 text-amber-700',
  restored: 'bg-blue-100 text-blue-700',
  deleted: 'bg-red-100 text-red-700',
  payment: 'bg-emerald-100 text-emerald-700',
  auto: 'bg-gray-100 text-gray-600',
};

function fmtDateTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function ChangeLog() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [action, setAction] = useState('');

  useEffect(() => {
    setLoading(true);
    api.getAllReservationEvents(500)
      .then((d) => setEvents(d || []))
      .catch((e) => setError(e.message || 'Ошибка загрузки'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => events.filter((e) => {
    if (action && e.action !== action) return false;
    if (!q) return true;
    const s = `${e.property_name || ''} ${e.guest_name || ''} ${e.detail || ''} ${e.actor_name || ''} ${ACTION_LABELS[e.action] || e.action}`.toLowerCase();
    return s.includes(q.toLowerCase());
  }), [events, q, action]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h1 className="text-2xl font-bold text-gray-800">Журнал изменений броней</h1>
        <div className="flex flex-wrap items-center gap-2">
          <select value={action} onChange={(e) => setAction(e.target.value)} className="border border-gray-200 rounded-lg px-3 py-2 text-sm">
            <option value="">Все действия</option>
            {Object.keys(ACTION_LABELS).map((a) => <option key={a} value={a}>{ACTION_LABELS[a]}</option>)}
          </select>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск: гость, объект, кто…" className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-60 max-w-full" />
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-4">Все действия с бронями: создание, изменение, оплата, отмена, восстановление и удаление. Удалённые брони сохраняются здесь со снимком данных.</p>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="py-16 text-center text-gray-400">Загрузка…</div>
      ) : (
        <div className="border border-gray-200 rounded-xl bg-white overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500">
                <th className="px-4 py-2.5 font-semibold whitespace-nowrap">Когда</th>
                <th className="px-4 py-2.5 font-semibold">Действие</th>
                <th className="px-4 py-2.5 font-semibold">Бронь</th>
                <th className="px-4 py-2.5 font-semibold">Кто</th>
                <th className="px-4 py-2.5 font-semibold">Детали</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.id} className="border-t border-gray-100 align-top">
                  <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{fmtDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${ACTION_STYLE[e.action] || 'bg-gray-100 text-gray-600'}`}>
                      {ACTION_LABELS[e.action] || e.action}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-700">
                    {e.property_name || (e.reservation_id ? `#${e.reservation_id}` : '—')}
                    {e.guest_name ? ` · ${e.guest_name}` : ''}
                    {e.check_in ? <div className="text-xs text-gray-400">{e.check_in} → {e.check_out}</div> : null}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">{e.actor_name || 'Система'}</td>
                  <td className="px-4 py-2.5 text-gray-600">{e.detail || ''}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">Нет записей</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
