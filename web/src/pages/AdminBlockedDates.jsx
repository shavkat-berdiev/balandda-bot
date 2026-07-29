import { useState, useEffect } from 'react';
import { Check, Trash2, Plus, CalendarOff } from 'lucide-react';
import { api } from '../api';

// Sales window (rolling N months) + blocked (closed) dates.
// Everything set here applies to the site, Telegram/Instagram bots AND
// Booking.com/Airbnb via Beds24 (availability is zeroed automatically).
export default function AdminBlockedDates() {
  const [rules, setRules] = useState(null);
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [months, setMonths] = useState(9);
  const [savingWindow, setSavingWindow] = useState(false);
  const [savedWindow, setSavedWindow] = useState(false);

  const [form, setForm] = useState({ date_from: '', date_to: '', property_id: '', reason: '' });
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [r, props] = await Promise.all([api.getBookingRules(), api.getAdminProperties()]);
      setRules(r);
      setMonths(r.window_months);
      setProperties(props.filter((p) => p.is_active && p.business_unit === 'RESORT'));
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  async function saveWindow() {
    setSavingWindow(true);
    setError('');
    try {
      await api.setBookingWindow(Number(months));
      setSavedWindow(true);
      setTimeout(() => setSavedWindow(false), 1800);
      await load();
    } catch (err) {
      setError(err.message);
    }
    setSavingWindow(false);
  }

  async function addBlock() {
    if (!form.date_from) { setError('Укажите дату начала'); return; }
    setAdding(true);
    setError('');
    try {
      await api.createBlockedDate({
        date_from: form.date_from,
        date_to: form.date_to || form.date_from,
        property_id: form.property_id ? Number(form.property_id) : null,
        reason: form.reason || null,
      });
      setForm({ date_from: '', date_to: '', property_id: '', reason: '' });
      await load();
    } catch (err) {
      setError(err.message);
    }
    setAdding(false);
  }

  async function remove(id) {
    setDeletingId(id);
    setError('');
    try {
      await api.deleteBlockedDate(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
    setDeletingId(null);
  }

  const fmt = (d) => d && new Date(d + 'T00:00:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
  const isPast = (b) => rules && b.date_to < rules.today;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Закрытые даты и окно продаж</h1>
        <p className="text-gray-500 text-sm mt-1">
          Действует везде сразу: сайт, Telegram/Instagram-боты и Booking.com/Airbnb (через Beds24).
          Существующие брони не затрагиваются — закрывается только продажа новых дат.
        </p>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : (
        <div className="space-y-6">
          {/* Sales window */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-800 mb-1">Окно продаж</h2>
            <p className="text-sm text-gray-500 mb-4">
              Брони открыты на <b>{rules?.window_months} мес.</b> вперёд — сейчас до <b>{fmt(rules?.max_date)}</b>.
              Окно скользящее: каждый день открывается ещё один день.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <input type="number" min="1" max="24" value={months}
                onChange={(e) => setMonths(e.target.value)}
                className="w-24 px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              <span className="text-sm text-gray-500">месяцев вперёд (1–24)</span>
              <button onClick={saveWindow} disabled={savingWindow}
                className={`inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium ${savedWindow ? 'bg-green-100 text-green-700' : 'bg-blue-600 text-white hover:bg-blue-700'}`}>
                <Check size={15} /> {savedWindow ? 'Сохранено' : (savingWindow ? '…' : 'Сохранить')}
              </button>
            </div>
          </div>

          {/* Add block */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-800 mb-4">Закрыть даты</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <label className="block text-xs text-gray-500 mb-1">С даты (первая закрытая ночь)</label>
                <input type="date" value={form.date_from}
                  onChange={(e) => setForm({ ...form, date_from: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">По дату (последняя закрытая ночь)</label>
                <input type="date" value={form.date_to} min={form.date_from}
                  onChange={(e) => setForm({ ...form, date_to: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Что закрываем</label>
                <select value={form.property_id}
                  onChange={(e) => setForm({ ...form, property_id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                  <option value="">🏔 Весь курорт</option>
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>{p.emoji} {p.name_ru}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Причина (видна только вам)</label>
                <input value={form.reason} placeholder="Новый год / ремонт…"
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div className="flex items-end">
                <button onClick={addBlock} disabled={adding}
                  className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                  <Plus size={15} /> {adding ? '…' : 'Закрыть'}
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Выезд в первый день следующего «открытого» дня разрешён: закрываются ночи, а не даты выезда.
            </p>
          </div>

          {/* Blocks list */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left">Даты (ночи)</th>
                    <th className="px-4 py-3 text-left">Область</th>
                    <th className="px-4 py-3 text-left">Причина</th>
                    <th className="px-4 py-3 text-center">Действие</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(rules?.blocked || []).length === 0 && (
                    <tr><td colSpan="4" className="px-4 py-8 text-center text-gray-400">
                      <CalendarOff size={22} className="inline mb-1" /><br />Закрытых дат нет
                    </td></tr>
                  )}
                  {(rules?.blocked || []).map((b) => (
                    <tr key={b.id} className={`hover:bg-gray-50 ${isPast(b) ? 'opacity-50' : ''}`}>
                      <td className="px-4 py-3 font-medium text-gray-800">
                        {fmt(b.date_from)}{b.date_to !== b.date_from ? ` — ${fmt(b.date_to)}` : ''}
                        {isPast(b) && <span className="ml-2 text-xs text-gray-400">(прошло)</span>}
                      </td>
                      <td className="px-4 py-3">
                        {b.property_id
                          ? <span className="text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md text-xs font-medium">{b.unit_name}</span>
                          : <span className="text-red-700 bg-red-50 px-2 py-0.5 rounded-md text-xs font-medium">Весь курорт</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-500">{b.reason || '—'}</td>
                      <td className="px-4 py-3 text-center">
                        <button onClick={() => remove(b.id)} disabled={deletingId === b.id}
                          className="text-gray-400 hover:text-red-500" title="Открыть даты снова">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
