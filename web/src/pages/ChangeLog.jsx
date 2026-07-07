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
function money(n) {
  if (n == null) return '';
  return Number(n).toLocaleString('ru-RU').replace(/,/g, ' ');
}
function currentUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}
const STATUS_RU = { CANCELLED: 'Отменено', EXPIRED: 'Истекло' };

export default function ChangeLog() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [action, setAction] = useState('');
  const [inactive, setInactive] = useState([]);
  const isOwner = (currentUser().role || '').toUpperCase() === 'OWNER';

  const reload = () => {
    setLoading(true);
    Promise.all([
      api.getAllReservationEvents(500).then((d) => setEvents(d || [])).catch((e) => setError(e.message || 'Ошибка загрузки')),
      api.getInactiveReservations(200).then((d) => setInactive(d || [])).catch(() => setInactive([])),
    ]).finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  async function doRestore(id) {
    if (!confirm('Восстановить эту бронь? Даты снова станут занятыми.')) return;
    try { await api.restoreReservation(id); reload(); }
    catch (e) { alert(e.message || 'Не удалось восстановить'); }
  }
  async function doDelete(id) {
    if (!confirm('Удалить эту бронь НАВСЕГДА? Это действие необратимо.')) return;
    if (!confirm('Вы уверены? Бронь будет удалена без возможности восстановления.')) return;
    try { await api.deleteReservation(id); reload(); }
    catch (e) { alert(e.message || 'Не удалось удалить'); }
  }

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

      {inactive.length > 0 && (
        <div className="mb-6 border border-gray-200 rounded-xl bg-white p-4">
          <div className="text-sm font-semibold text-gray-700 mb-1">Отменённые и истёкшие брони — можно восстановить ({inactive.length})</div>
          <p className="text-xs text-gray-400 mb-3">Даты сейчас свободны. Восстановление вернёт бронь как «Подтверждено», если даты ещё не заняты другой бронью.</p>
          <ul className="divide-y divide-gray-100 max-h-64 overflow-y-auto">
            {inactive.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="text-sm text-gray-500">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium mr-2 ${r.status === 'EXPIRED' ? 'bg-gray-100 text-gray-600' : 'bg-amber-100 text-amber-700'}`}>{STATUS_RU[r.status] || r.status}</span>
                  {r.property_name} · {r.guest_name || '—'}{r.telegram_username ? ` · @${r.telegram_username}` : ''} · {r.check_in}→{r.check_out}
                  {r.total_amount != null ? ` · ${money(r.total_amount)} сум` : ''}
                </span>
                <span className="flex gap-2">
                  <button onClick={() => doRestore(r.id)} className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium hover:bg-blue-100">Восстановить</button>
                  {isOwner && <button onClick={() => doDelete(r.id)} className="px-3 py-1.5 rounded-lg bg-red-50 text-red-600 text-xs font-medium hover:bg-red-100">Удалить навсегда</button>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="text-sm font-semibold text-gray-700 mb-2">История изменений (все действия)</div>
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
