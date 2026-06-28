import { useState, useEffect, useMemo, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Plus, X } from 'lucide-react';
import { api } from '../api';

const STATUS_STYLE = {
  HOLD: { cell: 'bg-amber-200 hover:bg-amber-300', label: 'Бронь (ожидает)' },
  CONFIRMED: { cell: 'bg-blue-300 hover:bg-blue-400', label: 'Подтверждено' },
  CHECKED_IN: { cell: 'bg-green-300 hover:bg-green-400', label: 'Заселён' },
  CHECKED_OUT: { cell: 'bg-slate-300 hover:bg-slate-400', label: 'Выселен' },
  BLOCKED: { cell: 'bg-gray-400 hover:bg-gray-500', label: 'Заблокировано' },
  NO_SHOW: { cell: 'bg-red-200', label: 'Не приехал' },
  CANCELLED: { cell: 'bg-white', label: 'Отменено' },
};
const STATUS_OPTIONS = ['CONFIRMED', 'HOLD', 'BLOCKED'];
const SOURCE_OPTIONS = ['MANUAL', 'PHONE', 'DIRECT', 'TELEGRAM', 'INSTAGRAM', 'BOOKING_COM', 'AIRBNB'];

function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function money(n) {
  if (n == null) return '';
  return Number(n).toLocaleString('ru-RU').replace(/,/g, ' ');
}

export default function Calendar() {
  const today = useMemo(() => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; }, []);
  const [start, setStart] = useState(today);
  const [span, setSpan] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth < 640 ? 7 : 21
  );
  const [units, setUnits] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState(null);     // new-reservation form
  const [detail, setDetail] = useState(null); // reservation detail

  const days = useMemo(
    () => Array.from({ length: span }, (_, i) => addDays(start, i)),
    [start, span]
  );
  const rangeFrom = ymd(start);
  const rangeTo = ymd(addDays(start, span));

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [u, r] = await Promise.all([
        api.getAdminProperties(),
        api.getReservations(rangeFrom, rangeTo),
      ]);
      setUnits((u || []).filter((x) => x.is_active && x.business_unit === 'RESORT'));
      setReservations(r || []);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [rangeFrom, rangeTo]);

  useEffect(() => { load(); }, [load]);

  // index: `${property_id}|${ymd}` -> reservation covering that night
  const byCell = useMemo(() => {
    const m = new Map();
    for (const r of reservations) {
      if (r.status === 'CANCELLED' || r.status === 'NO_SHOW') continue;
      let d = new Date(r.check_in + 'T00:00:00');
      const end = new Date(r.check_out + 'T00:00:00');
      while (d < end) {
        m.set(`${r.property_id}|${ymd(d)}`, r);
        d = addDays(d, 1);
      }
    }
    return m;
  }, [reservations]);

  function openNew(unit, date) {
    setForm({
      property_id: unit ? unit.id : (units[0]?.id ?? ''),
      check_in: date ? ymd(date) : rangeFrom,
      check_out: date ? ymd(addDays(date, 1)) : ymd(addDays(start, 1)),
      guest_name: '', guest_phone: '', guest_count: '',
      status: 'CONFIRMED', source: 'MANUAL',
      total_amount: '', deposit_amount: '', note: '',
    });
  }

  async function submitNew(e) {
    e.preventDefault();
    try {
      const body = {
        property_id: Number(form.property_id),
        check_in: form.check_in,
        check_out: form.check_out,
        guest_name: form.guest_name || null,
        guest_phone: form.guest_phone || null,
        guest_count: form.guest_count ? Number(form.guest_count) : null,
        status: form.status,
        source: form.source,
        total_amount: form.total_amount ? Number(form.total_amount) : null,
        deposit_amount: form.deposit_amount ? Number(form.deposit_amount) : null,
        note: form.note || null,
      };
      await api.createReservation(body);
      setForm(null);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось создать');
    }
  }

  async function doCancel(id) {
    if (!confirm('Отменить эту бронь?')) return;
    try {
      await api.cancelReservation(id);
      setDetail(null);
      await load();
    } catch (e) {
      alert(e.message || 'Ошибка');
    }
  }

  const dow = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <h1 className="text-2xl font-bold text-gray-800">Календарь броней</h1>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setStart(addDays(start, -span))} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ChevronLeft size={18} /></button>
          <input type="date" value={ymd(start)} onChange={(e) => setStart(new Date(e.target.value + 'T00:00:00'))} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          <button onClick={() => setStart(addDays(start, span))} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ChevronRight size={18} /></button>
          <select value={span} onChange={(e) => setSpan(Number(e.target.value))} className="border border-gray-200 rounded-lg px-2 py-2 text-sm">
            <option value={7}>7 дней</option>
            <option value={14}>14 дней</option>
            <option value={21}>21 день</option>
            <option value={30}>30 дней</option>
          </select>
          <button onClick={() => openNew(null, null)} className="flex items-center gap-1.5 bg-blue-600 text-white rounded-lg px-3 py-2 text-sm font-medium hover:bg-blue-700"><Plus size={16} /> Бронь</button>
        </div>
      </div>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-3 text-xs text-gray-600">
        {STATUS_OPTIONS.concat(['CHECKED_IN']).map((s) => (
          <span key={s} className="flex items-center gap-1.5"><span className={`inline-block w-3 h-3 rounded ${STATUS_STYLE[s].cell.split(' ')[0]}`} />{STATUS_STYLE[s].label}</span>
        ))}
      </div>

      {loading ? (
        <div className="py-16 text-center text-gray-400">Загрузка…</div>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded-xl bg-white" style={{ WebkitOverflowScrolling: 'touch' }}>
          <table className="border-collapse text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 border-b border-r border-gray-200 px-3 py-2 text-left font-semibold text-gray-700 min-w-[150px]">Объект</th>
                {days.map((d) => {
                  const isSat = d.getDay() === 6;
                  return (
                    <th key={ymd(d)} className={`border-b border-gray-200 px-1 py-2 text-center font-medium min-w-[34px] ${isSat ? 'bg-rose-50 text-rose-600' : 'text-gray-500'}`}>
                      <div className="text-[10px] leading-none">{dow[d.getDay()]}</div>
                      <div>{d.getDate()}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.id}>
                  <td className="sticky left-0 z-10 bg-white border-b border-r border-gray-200 px-3 py-1.5 font-medium text-gray-800 whitespace-nowrap">
                    {u.name_ru} <span className="text-gray-400 text-xs">· {u.capacity}👤</span>
                  </td>
                  {days.map((d) => {
                    const r = byCell.get(`${u.id}|${ymd(d)}`);
                    const isSat = d.getDay() === 6;
                    if (r) {
                      const st = STATUS_STYLE[r.status] || STATUS_STYLE.CONFIRMED;
                      return (
                        <td key={ymd(d)} className="border-b border-gray-100 p-0">
                          <button onClick={() => setDetail(r)} title={`${r.guest_name || r.source_label}: ${r.check_in}→${r.check_out}`}
                            className={`w-full h-8 ${st.cell} transition-colors`} />
                        </td>
                      );
                    }
                    return (
                      <td key={ymd(d)} className={`border-b border-gray-100 p-0 ${isSat ? 'bg-rose-50/40' : ''}`}>
                        <button onClick={() => openNew(u, d)} className="w-full h-8 hover:bg-blue-100 transition-colors" />
                      </td>
                    );
                  })}
                </tr>
              ))}
              {units.length === 0 && (
                <tr><td colSpan={days.length + 1} className="px-3 py-8 text-center text-gray-400">Нет объектов</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* New reservation modal */}
      {form && (
        <Modal onClose={() => setForm(null)} title="Новая бронь / блок">
          <form onSubmit={submitNew} className="space-y-3">
            <Field label="Объект">
              <select required value={form.property_id} onChange={(e) => setForm({ ...form, property_id: e.target.value })} className="input">
                {units.map((u) => <option key={u.id} value={u.id}>{u.name_ru}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Заезд"><input type="date" required value={form.check_in} onChange={(e) => setForm({ ...form, check_in: e.target.value })} className="input" /></Field>
              <Field label="Выезд"><input type="date" required value={form.check_out} onChange={(e) => setForm({ ...form, check_out: e.target.value })} className="input" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Статус">
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="input">
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_STYLE[s].label}</option>)}
                </select>
              </Field>
              <Field label="Источник">
                <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} className="input">
                  {SOURCE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Имя гостя"><input value={form.guest_name} onChange={(e) => setForm({ ...form, guest_name: e.target.value })} className="input" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Телефон"><input value={form.guest_phone} onChange={(e) => setForm({ ...form, guest_phone: e.target.value })} className="input" /></Field>
              <Field label="Гостей"><input type="number" min="1" value={form.guest_count} onChange={(e) => setForm({ ...form, guest_count: e.target.value })} className="input" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Сумма (сум)"><input type="number" value={form.total_amount} onChange={(e) => setForm({ ...form, total_amount: e.target.value })} className="input" /></Field>
              <Field label="Предоплата (сум)"><input type="number" value={form.deposit_amount} onChange={(e) => setForm({ ...form, deposit_amount: e.target.value })} className="input" /></Field>
            </div>
            <Field label="Заметка"><input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className="input" /></Field>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setForm(null)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm">Отмена</button>
              <button type="submit" className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">Создать</button>
            </div>
          </form>
        </Modal>
      )}

      {/* Detail modal */}
      {detail && (
        <Modal onClose={() => setDetail(null)} title={detail.guest_name || detail.source_label}>
          <div className="space-y-1.5 text-sm text-gray-700">
            <Row k="Объект" v={detail.property_name} />
            <Row k="Даты" v={`${detail.check_in} → ${detail.check_out}`} />
            <Row k="Статус" v={detail.status_label} />
            <Row k="Источник" v={detail.source_label} />
            {detail.guest_phone && <Row k="Телефон" v={detail.guest_phone} />}
            {detail.guest_count != null && <Row k="Гостей" v={detail.guest_count} />}
            {detail.total_amount != null && <Row k="Сумма" v={money(detail.total_amount) + ' сум'} />}
            {detail.deposit_amount != null && <Row k="Предоплата" v={money(detail.deposit_amount) + ' сум'} />}
            {detail.note && <Row k="Заметка" v={detail.note} />}
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button onClick={() => doCancel(detail.id)} className="px-4 py-2 rounded-lg bg-red-50 text-red-600 text-sm font-medium hover:bg-red-100">Отменить бронь</button>
            <button onClick={() => setDetail(null)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm">Закрыть</button>
          </div>
        </Modal>
      )}

      <style>{`.input{width:100%;border:1px solid #e5e7eb;border-radius:0.5rem;padding:0.5rem 0.625rem;font-size:0.875rem}`}</style>
    </div>
  );
}

function Field({ label, children }) {
  return <label className="block"><span className="block text-xs font-medium text-gray-500 mb-1">{label}</span>{children}</label>;
}
function Row({ k, v }) {
  return <div className="flex justify-between gap-4"><span className="text-gray-400">{k}</span><span className="text-gray-800 text-right">{v}</span></div>;
}
function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
