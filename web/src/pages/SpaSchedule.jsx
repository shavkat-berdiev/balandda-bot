import { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, X, Check, Trash2, Search } from 'lucide-react';
import { api } from '../api';

const START_MIN = 9 * 60;      // 09:00
const END_MIN = 22 * 60;       // 22:00
const STEP = 30;               // minutes per row
const ROW_H = 44;              // px per row
const SLOTS = (END_MIN - START_MIN) / STEP;  // 26
const TZ = '+05:00';           // Asia/Tashkent (fixed)

const STATUS_LABEL = { planned: 'Запланирована', done: 'Выполнена', cancelled: 'Отменена', no_show: 'Не пришёл' };
const STATUS_COLOR = {
  planned: 'bg-blue-100 border-blue-300 text-blue-900',
  done: 'bg-green-100 border-green-300 text-green-900',
  cancelled: 'bg-gray-100 border-gray-300 text-gray-400 line-through',
  no_show: 'bg-amber-100 border-amber-300 text-amber-900',
};

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function pad(n) { return String(n).padStart(2, '0'); }
function minToHHMM(m) { return `${pad(Math.floor(m / 60))}:${pad(m % 60)}`; }
function fmtPrice(n) { return Number(n || 0).toLocaleString('ru-RU'); }

export default function SpaSchedule() {
  const [date, setDate] = useState(todayISO());
  const [appts, setAppts] = useState([]);
  const [masters, setMasters] = useState([]);
  const [services, setServices] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null); // {mode:'create'|'edit', ...}

  useEffect(() => {
    api.getSpaMasters().then(m => setMasters(m.filter(x => x.is_active))).catch(() => {});
    api.getAdminServices().then(s => setServices(s.filter(x => x.is_active))).catch(() => {});
    api.getSpaLocations().then(l => setLocations(l.filter(x => x.is_active))).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try { setAppts(await api.getSpaAppointments(date)); setError(''); }
    catch (err) { setError(err.message); }
    setLoading(false);
  }, [date]);

  useEffect(() => { load(); }, [load]);

  function dayStartInstant() { return new Date(`${date}T09:00:00${TZ}`).getTime(); }
  function apptTopMin(a) { return (new Date(a.start_at).getTime() - dayStartInstant()) / 60000; }

  function shiftDate(days) {
    const d = new Date(`${date}T12:00:00${TZ}`);
    d.setDate(d.getDate() + days);
    setDate(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
  }

  function openCreate(masterId, slotIndex) {
    const startMin = START_MIN + slotIndex * STEP;
    setModal({ mode: 'create', master_id: masterId, timeMin: startMin });
  }
  function openEdit(a) { setModal({ mode: 'edit', appt: a }); }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Расписание SPA</h1>
          <p className="text-gray-500 text-sm mt-1">По мастерам · нажмите на свободное время, чтобы записать</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => shiftDate(-1)} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ChevronLeft size={18} /></button>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          <button onClick={() => shiftDate(1)} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ChevronRight size={18} /></button>
          <button onClick={() => setDate(todayISO())} className="px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">Сегодня</button>
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {masters.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
          Нет активных мастеров. Добавьте их в разделе «SPA мастера».
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          {/* header */}
          <div className="flex border-b border-gray-200 min-w-max sticky top-0 bg-white z-10">
            <div className="w-14 shrink-0 border-r border-gray-100" />
            {masters.map(m => (
              <div key={m.id} className="flex-1 min-w-[150px] px-3 py-2 text-center text-sm font-semibold text-gray-700 border-r border-gray-100">
                {m.name}
              </div>
            ))}
          </div>
          {/* body */}
          <div className="flex min-w-max relative" style={{ height: SLOTS * ROW_H }}>
            {/* time gutter */}
            <div className="w-14 shrink-0 border-r border-gray-100 relative">
              {Array.from({ length: SLOTS }).map((_, i) => (
                <div key={i} className="absolute left-0 right-0 text-[10px] text-gray-400 pr-1 text-right"
                  style={{ top: i * ROW_H - 6 }}>{i % 2 === 0 ? minToHHMM(START_MIN + i * STEP) : ''}</div>
              ))}
            </div>
            {/* master columns */}
            {masters.map(m => (
              <div key={m.id} className="flex-1 min-w-[150px] border-r border-gray-100 relative"
                onClick={(e) => {
                  if (e.target.closest('[data-appt]')) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const idx = Math.floor((e.clientY - rect.top) / ROW_H);
                  if (idx >= 0 && idx < SLOTS) openCreate(m.id, idx);
                }}>
                {Array.from({ length: SLOTS }).map((_, i) => (
                  <div key={i} className="absolute left-0 right-0 border-b border-gray-50 hover:bg-blue-50/40 cursor-pointer"
                    style={{ top: i * ROW_H, height: ROW_H }} />
                ))}
                {appts.filter(a => a.master_id === m.id).map(a => {
                  const top = (apptTopMin(a) / STEP) * ROW_H;
                  const h = Math.max((a.duration_minutes / STEP) * ROW_H, 22);
                  if (top < -ROW_H || top > SLOTS * ROW_H) return null;
                  return (
                    <div key={a.id} data-appt onClick={() => openEdit(a)}
                      className={`absolute left-1 right-1 rounded-md border px-2 py-1 overflow-hidden cursor-pointer text-[11px] leading-tight ${STATUS_COLOR[a.status] || STATUS_COLOR.planned}`}
                      style={{ top: top + 1, height: h - 2 }}>
                      <div className="font-semibold truncate">{a.service_name}</div>
                      <div className="truncate">{a.customer_name || 'Гость'}{a.location_name ? ` · ${a.location_name}` : ''}</div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
      {loading && <p className="text-xs text-gray-400 mt-2">Загрузка…</p>}

      {modal && (
        <ApptModal
          modal={modal} date={date} masters={masters} services={services} locations={locations}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }}
        />
      )}
    </div>
  );
}

function ApptModal({ modal, date, masters, services, locations, onClose, onSaved }) {
  const isEdit = modal.mode === 'edit';
  const a = modal.appt;
  const [masterId, setMasterId] = useState(isEdit ? a.master_id : modal.master_id);
  const [serviceId, setServiceId] = useState(isEdit ? a.service_id : '');
  const [locationId, setLocationId] = useState(isEdit ? (a.location_id || '') : '');
  const [timeMin, setTimeMin] = useState(isEdit ? null : modal.timeMin);
  const [timeStr, setTimeStr] = useState(isEdit ? new Date(a.start_at).toTimeString().slice(0, 5) : minToHHMM(modal.timeMin));
  const [linkMode, setLinkMode] = useState(isEdit && a.reservation_id ? 'booking' : 'walkin');
  const [name, setName] = useState(isEdit ? (a.customer_name || '') : '');
  const [phone, setPhone] = useState(isEdit ? (a.customer_phone || '') : '');
  const [reservationId, setReservationId] = useState(isEdit ? (a.reservation_id || null) : null);
  const [price, setPrice] = useState(isEdit ? a.price : '');
  const [note, setNote] = useState(isEdit ? (a.note || '') : '');
  const [status, setStatus] = useState(isEdit ? a.status : 'planned');
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [err, setErr] = useState('');
  const [saving, setSaving] = useState(false);

  const svc = services.find(s => s.id === Number(serviceId));
  // Services this master can perform (fallback: all if none assigned to anyone)
  const masterServices = services.filter(s => !s.master_ids?.length || s.master_ids.includes(Number(masterId)));
  const needsRoom = svc && svc.location_mode !== 'cottage_only';
  const roomOptions = svc && svc.location_ids?.length
    ? locations.filter(l => svc.location_ids.includes(l.id))
    : locations;

  useEffect(() => { if (svc && price === '') setPrice(svc.price); }, [serviceId]); // eslint-disable-line

  // Build the time-slot dropdown
  const slotOptions = [];
  for (let m = START_MIN; m < END_MIN; m += STEP) slotOptions.push(minToHHMM(m));

  async function doSearch(q) {
    setSearch(q);
    if (q.trim().length < 2) { setResults([]); return; }
    try { setResults(await api.searchReservations(q)); } catch { setResults([]); }
  }
  function pickReservation(r) {
    setReservationId(r.id);
    setName(r.guest_name || '');
    setPhone(r.guest_phone || '');
    setResults([]); setSearch(`${r.guest_name || '—'}${r.guest_phone ? ' · ' + r.guest_phone : ''}`);
  }

  async function save() {
    setErr('');
    if (!serviceId) { setErr('Выберите услугу'); return; }
    setSaving(true);
    const start_at = `${date}T${timeStr}:00${TZ}`;
    const payload = {
      service_id: Number(serviceId),
      master_id: Number(masterId),
      location_id: needsRoom && locationId ? Number(locationId) : null,
      reservation_id: linkMode === 'booking' ? reservationId : null,
      customer_name: name || null,
      customer_phone: phone || null,
      start_at,
      price: price === '' ? null : parseFloat(price),
      note: note || null,
      status,
    };
    try {
      if (isEdit) await api.updateSpaAppointment(a.id, payload);
      else await api.createSpaAppointment(payload);
      onSaved();
    } catch (e) { setErr(e.message); setSaving(false); }
  }

  async function cancelAppt() {
    setErr(''); setSaving(true);
    try { await api.updateSpaAppointment(a.id, { status: 'cancelled' }); onSaved(); }
    catch (e) { setErr(e.message); setSaving(false); }
  }

  const field = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm';
  const lbl = 'block text-xs font-medium text-gray-600 mb-1';

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">{isEdit ? 'Запись' : 'Новая запись'}</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100"><X size={18} /></button>
        </div>

        {err && <div className="bg-red-50 text-red-600 rounded-lg px-3 py-2 text-sm mb-3">{err}</div>}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={lbl}>Мастер</label>
            <select value={masterId} onChange={e => setMasterId(e.target.value)} className={field}>
              {masters.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div>
            <label className={lbl}>Время</label>
            <select value={timeStr} onChange={e => setTimeStr(e.target.value)} className={field}>
              {slotOptions.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div className="mt-3">
          <label className={lbl}>Услуга</label>
          <select value={serviceId} onChange={e => { setServiceId(e.target.value); setLocationId(''); setPrice(''); }} className={field}>
            <option value="">— Выберите услугу —</option>
            {masterServices.map(s => <option key={s.id} value={s.id}>{s.name_ru} · {s.duration_minutes} мин · {fmtPrice(s.price)}</option>)}
          </select>
        </div>

        {needsRoom && (
          <div className="mt-3">
            <label className={lbl}>Кабинет {svc.location_mode === 'room_or_cottage' ? '(или коттедж — оставьте пустым)' : ''}</label>
            <select value={locationId} onChange={e => setLocationId(e.target.value)} className={field}>
              <option value="">{svc.location_mode === 'room_only' ? '— Выберите кабинет —' : '— В коттедже —'}</option>
              {roomOptions.map(l => <option key={l.id} value={l.id}>{l.name_ru}</option>)}
            </select>
          </div>
        )}

        <div className="mt-4">
          <div className="flex gap-4 mb-2 text-sm">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={linkMode === 'walkin'} onChange={() => { setLinkMode('walkin'); setReservationId(null); }} /> Гость / walk-in
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={linkMode === 'booking'} onChange={() => setLinkMode('booking')} /> Из брони
            </label>
          </div>
          {linkMode === 'booking' && (
            <div className="mb-2 relative">
              <div className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg">
                <Search size={15} className="text-gray-400" />
                <input value={search} onChange={e => doSearch(e.target.value)} placeholder="Имя или телефон гостя…" className="flex-1 text-sm outline-none" />
              </div>
              {results.length > 0 && (
                <div className="absolute z-10 left-0 right-0 bg-white border border-gray-200 rounded-lg mt-1 shadow-lg max-h-48 overflow-y-auto">
                  {results.map(r => (
                    <button key={r.id} onClick={() => pickReservation(r)} className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-50">
                      <span className="font-medium">{r.guest_name || '—'}</span>
                      <span className="text-gray-500"> · {r.property_name || ''} · {r.check_in}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={lbl}>Имя</label>
              <input value={name} onChange={e => setName(e.target.value)} className={field} />
            </div>
            <div>
              <label className={lbl}>Телефон</label>
              <input value={phone} onChange={e => setPhone(e.target.value)} className={field} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mt-3">
          <div>
            <label className={lbl}>Цена</label>
            <input type="number" value={price} onChange={e => setPrice(e.target.value)} className={field} />
          </div>
          {isEdit && (
            <div>
              <label className={lbl}>Статус</label>
              <select value={status} onChange={e => setStatus(e.target.value)} className={field}>
                {Object.keys(STATUS_LABEL).map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </select>
            </div>
          )}
        </div>

        <div className="mt-3">
          <label className={lbl}>Заметка</label>
          <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} className={field} />
        </div>

        <div className="flex items-center gap-3 mt-5">
          <button onClick={save} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            <Check size={16} /> {isEdit ? 'Сохранить' : 'Записать'}
          </button>
          {isEdit && a.status !== 'cancelled' && (
            <button onClick={cancelAppt} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg text-sm font-medium hover:bg-red-100">
              <Trash2 size={16} /> Отменить запись
            </button>
          )}
          <button onClick={onClose} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 ml-auto">Закрыть</button>
        </div>
      </div>
    </div>
  );
}
