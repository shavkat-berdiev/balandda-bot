import { useState, useEffect, useMemo, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Plus, X } from 'lucide-react';
import { api } from '../api';

const STATUS_STYLE = {
  HOLD: { cell: 'bg-red-300 hover:bg-red-400', label: 'Бронь (не оплачено)' },
  CONFIRMED: { cell: 'bg-blue-300 hover:bg-blue-400', label: 'Подтверждено' },
  CHECKED_IN: { cell: 'bg-green-300 hover:bg-green-400', label: 'Заселён' },
  CHECKED_OUT: { cell: 'bg-slate-300 hover:bg-slate-400', label: 'Выселен' },
  BLOCKED: { cell: 'bg-gray-400 hover:bg-gray-500', label: 'Заблокировано' },
  NO_SHOW: { cell: 'bg-gray-200', label: 'Не приехал' },
  CANCELLED: { cell: 'bg-white', label: 'Отменено' },
  EXPIRED: { cell: 'bg-gray-100', label: 'Истекло (не оплачено)' },
};
const STATUS_OPTIONS = ['CONFIRMED', 'HOLD', 'BLOCKED'];
const SOURCE_OPTIONS = ['MANUAL', 'PHONE', 'DIRECT', 'TELEGRAM', 'INSTAGRAM', 'BOOKING_COM', 'AIRBNB'];
const PAYMENT_METHODS = [
  { v: 'CASH', l: 'Наличные' },
  { v: 'CARD_TRANSFER', l: 'Перевод на карту' },
  { v: 'WIRE_TRANSFER', l: 'Перечисление' },
  { v: 'TERMINAL_VISA', l: 'Терминал Visa' },
  { v: 'TERMINAL_UZCARD', l: 'Терминал UzCard' },
  { v: 'PAYME', l: 'PayMe' },
];

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

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
// Keep calendar bars compact: show ~9 chars, full text on the card.
function cap(s, n = 9) {
  s = (s ?? '').toString();
  return s.length > n ? s.slice(0, n) + '…' : s;
}
const ACTION_LABELS = { created: 'создано', updated: 'изменено', cancelled: 'отменено', restored: 'восстановлено', deleted: 'удалено', payment: 'оплата', auto: 'авто' };
function currentUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}
function fmtDateTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}
// Bar colour: no-show grey, fully paid green, past+unpaid orange (debt), else status colour.
function barClass(r, todayStr) {
  if (r.status === 'NO_SHOW') return 'bg-gray-200 hover:bg-gray-300 line-through text-gray-500';
  if (r.status === 'HOLD') return 'bg-red-300 hover:bg-red-400'; // unpaid hold — awaiting prepayment
  const total = r.total_amount, paid = r.paid_amount || 0;
  const fullyPaid = total != null && total > 0 && paid + 1 >= total;
  if (fullyPaid) return 'bg-green-300 hover:bg-green-400';
  if (r.check_out <= todayStr) return 'bg-orange-300 hover:bg-orange-400'; // stay ended, not fully paid
  return (STATUS_STYLE[r.status] && STATUS_STYLE[r.status].cell) || STATUS_STYLE.CONFIRMED.cell;
}
function stayTotal(unit, ciStr, coStr) {
  if (!unit || !ciStr || !coStr) return 0;
  let d = new Date(ciStr + 'T00:00:00');
  const end = new Date(coStr + 'T00:00:00');
  let total = 0;
  while (d < end) {
    total += Number(d.getDay() === 6 ? unit.price_weekend : unit.price_weekday) || 0; // Sat = weekend
    d = addDays(d, 1);
  }
  return Math.round(total);
}

export default function Calendar({ businessUnit = 'RESORT', autoPrice = true, title = 'Календарь броней', showImport = true, expires = true } = {}) {
  const today = useMemo(() => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; }, []);
  const [start, setStart] = useState(() => addDays(today, -1)); // opens on yesterday
  const [span, setSpan] = useState(31); // yesterday + 30 days; "load more" extends it
  const [importing, setImporting] = useState(false);
  const [units, setUnits] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState(null);     // new-reservation form
  const [detail, setDetail] = useState(null); // selected reservation
  const [detailForm, setDetailForm] = useState(null); // editable copy of the selected reservation
  const [events, setEvents] = useState([]);   // change log for the selected reservation
  const [savingDetail, setSavingDetail] = useState(false);
  const [payForm, setPayForm] = useState(null);
  const [savingPay, setSavingPay] = useState(false);
  const [payments, setPayments] = useState([]);   // payment ledger for the selected booking
  const [editPay, setEditPay] = useState(null);    // {id, amount, method} inline edit
  const [prepays, setPrepays] = useState([]);      // prepayments (with proof) for the selected booking
  const [preFile, setPreFile] = useState(null);
  const [savingPre, setSavingPre] = useState(false);
  const [shotUrls, setShotUrls] = useState({});    // prepaymentId -> object URL (auth-fetched image)
  const [connectUrl, setConnectUrl] = useState(''); // generated client Telegram deep-link
  const [linkCopied, setLinkCopied] = useState(false);
  const [bookMsgs, setBookMsgs] = useState(null);   // editable invitation text {ru,uz,en,zh} from balandda.uz
  const [msgLang, setMsgLang] = useState('ru');

  useEffect(() => {
    fetch('https://www.balandda.uz/bookingmsg.php').then((r) => (r.ok ? r.json() : null)).then((m) => { if (m) setBookMsgs(m); }).catch(() => {});
  }, []);

  const isOwner = useMemo(() => (currentUser().role || '').toUpperCase() === 'OWNER', []);

  const days = useMemo(
    () => Array.from({ length: span }, (_, i) => addDays(start, i)),
    [start, span]
  );
  const rangeLabel = useMemo(() => {
    const a = days[0], b = days[days.length - 1];
    const ma = a.getMonth(), mb = b.getMonth(), ya = a.getFullYear(), yb = b.getFullYear();
    if (ma === mb && ya === yb) return `${MONTHS[ma]} ${ya}`;
    if (ya === yb) return `${MONTHS[ma]} – ${MONTHS[mb]} ${yb}`;
    return `${MONTHS[ma]} ${ya} – ${MONTHS[mb]} ${yb}`;
  }, [days]);
  const rangeFrom = ymd(start);
  const rangeTo = ymd(addDays(start, span));

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [u, r] = await Promise.all([
        api.getAdminProperties(),
        api.getReservations(rangeFrom, rangeTo),
      ]);
      setUnits((u || []).filter((x) => x.is_active && x.business_unit === businessUnit));
      setReservations(r || []);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, [rangeFrom, rangeTo, businessUnit]);

  useEffect(() => { load(); }, [load]);

  // When a booking is selected: load an editable copy + its change log + payment ledger.
  useEffect(() => {
    if (!detail) { setDetailForm(null); setEvents([]); setPayForm(null); setPayments([]); setEditPay(null); setPrepays([]); setPreFile(null); setShotUrls({}); return; }
    setPayForm(null); setEditPay(null); setPreFile(null); setShotUrls({}); setConnectUrl(''); setLinkCopied(false);
    setDetailForm({
      property_id: detail.property_id,
      status: detail.status,
      check_in: detail.check_in, check_out: detail.check_out,
      guest_name: detail.guest_name || '', guest_phone: detail.guest_phone || '',
      telegram_username: detail.telegram_username || '',
      guest_count: detail.guest_count ?? '', total_amount: detail.total_amount ?? '',
      deposit_amount: detail.deposit_amount ?? '', note: detail.note || '',
    });
    api.getReservationEvents(detail.id).then(setEvents).catch(() => setEvents([]));
    api.getReservationPayments(detail.id).then(setPayments).catch(() => setPayments([]));
    api.prepaymentsByReservation(detail.id).then(setPrepays).catch(() => setPrepays([]));
  }, [detail]);

  async function reloadPayments(id) {
    try { setPayments(await api.getReservationPayments(id)); } catch { /* ignore */ }
  }

  async function addPrepay() {
    if (!detail || !preFile) return;
    setSavingPre(true);
    try {
      const fd = new FormData();
      fd.append('reservation_id', detail.id);
      fd.append('screenshot', preFile);
      await api.addPrepaymentFromReservation(fd);
      setPreFile(null);
      setPrepays(await api.prepaymentsByReservation(detail.id));
    } catch (e) { setError(e.message); }
    setSavingPre(false);
  }

  async function viewShot(id) {
    try {
      const u = shotUrls[id] || await api.prepaymentScreenshotUrl(id);
      if (!shotUrls[id]) setShotUrls((s) => ({ ...s, [id]: u }));
      window.open(u, '_blank');
    } catch { setError('Не удалось загрузить скриншот'); }
  }

  // index: `${property_id}|${ymd}` -> reservation covering that night
  const byCell = useMemo(() => {
    const m = new Map();
    for (const r of reservations) {
      if (r.status === 'CANCELLED' || r.status === 'EXPIRED') continue; // freed dates; no-show stays visible
      let d = new Date(r.check_in + 'T00:00:00');
      const end = new Date(r.check_out + 'T00:00:00');
      while (d < end) {
        const key = `${r.property_id}|${ymd(d)}`;
        const ex = m.get(key);
        // don't let a no-show hide an active booking on the same night
        if (!(ex && r.status === 'NO_SHOW' && ex.status !== 'NO_SHOW')) m.set(key, r);
        d = addDays(d, 1);
      }
    }
    return m;
  }, [reservations]);

  // Suggested amounts from the unit's catalog rate (editable). Deposit defaults to 30%.
  function calcAmounts(propertyId, ci, co) {
    if (!autoPrice) return { total_amount: '', deposit_amount: '' }; // pool: amounts empty/manual
    const u = units.find((x) => x.id === Number(propertyId));
    const total = stayTotal(u, ci, co);
    return {
      total_amount: total ? String(total) : '',
      deposit_amount: total ? String(Math.round(total * 0.2)) : '',
    };
  }

  function openNew(unit, date) {
    const property_id = unit ? unit.id : (units[0]?.id ?? '');
    const check_in = date ? ymd(date) : rangeFrom;
    const check_out = date ? ymd(addDays(date, 1)) : ymd(addDays(start, 1));
    setForm({
      step: 1, createdRes: null,
      property_id, check_in, check_out,
      guest_name: '', guest_phone: '', guest_count: '', telegram_username: '',
      status: expires ? 'HOLD' : 'CONFIRMED', source: 'MANUAL',
      ...calcAmounts(property_id, check_in, check_out),
      note: '',
      payMethod: 'CASH', payAmount: '',
    });
  }

  // Merge a change; recompute suggested amounts when the unit or dates change.
  function updateForm(patch) {
    setForm((f) => {
      const next = { ...f, ...patch };
      // Keep check-out strictly after check-in: if the arrival moved to/past it, bump it.
      if ('check_in' in patch && next.check_in && next.check_out <= next.check_in) {
        next.check_out = ymd(addDays(new Date(next.check_in + 'T00:00:00'), 1));
      }
      if ('property_id' in patch || 'check_in' in patch || 'check_out' in patch) {
        Object.assign(next, calcAmounts(next.property_id, next.check_in, next.check_out));
      }
      return next;
    });
  }

  async function importPreps() {
    setImporting(true);
    try {
      const r = await api.importPrepayments();
      await load();
      alert(`Брони из предоплат: +${r.created} (пропущено ${r.skipped}); привязано прошлых оплат: ${r.linked_income ?? 0}`);
    } catch (e) {
      alert(e.message || 'Ошибка импорта');
    } finally {
      setImporting(false);
    }
  }

  // Step 1: create the booking (HOLD → red until a prepayment is added).
  async function submitNew(e) {
    e.preventDefault();
    if (!form.check_out || form.check_out <= form.check_in) {
      alert('Дата выезда должна быть позже даты заезда.');
      return;
    }
    try {
      const body = {
        property_id: Number(form.property_id),
        check_in: form.check_in,
        check_out: form.check_out,
        guest_name: form.guest_name || null,
        guest_phone: form.guest_phone || null,
        guest_count: form.guest_count ? Number(form.guest_count) : null,
        telegram_username: form.telegram_username || null,
        status: form.status,
        source: form.source,
        total_amount: form.total_amount ? Number(form.total_amount) : null,
        // The 20% figure is only a suggestion used to prefill the prepayment step —
        // it is NOT a paid deposit, so we don't persist it (avoids double-counting "paid").
        deposit_amount: null,
        note: form.note || null,
      };
      const res = await api.createReservation(body);
      await load();
      if (form.status === 'BLOCKED') { setForm(null); return; }
      // Step 2: prepayment (prefill the 20% deposit, editable up).
      setForm((f) => ({ ...f, step: 2, createdRes: res, payAmount: f.deposit_amount || '', payMethod: 'CASH' }));
    } catch (e) {
      alert(e.message || 'Не удалось создать');
    }
  }

  // Step 2: register the prepayment against the just-created booking (flips it out of red).
  async function submitPrepay() {
    if (!form?.createdRes) { setForm(null); return; }
    const amt = Number(form.payAmount);
    if (!amt || amt <= 0) { alert('Введите сумму предоплаты'); return; }
    try {
      await api.acceptPayment(form.createdRes.id, { amount: amt, payment_method: form.payMethod });
      setForm(null);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось провести предоплату');
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

  async function doExtendHold() {
    try {
      const u = await api.extendHold(detail.id);
      setDetail(u);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось продлить');
    }
  }

  async function doWaivePrepay() {
    if (!confirm('Отметить бронь как «без предоплаты»? Она станет подтверждённой и перестанет истекать.')) return;
    try {
      const u = await api.waivePrepayment(detail.id);
      setDetail(u);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось');
    }
  }

  function connectText(url = connectUrl) {
    const msg = bookMsgs && bookMsgs[msgLang];
    return (msg ? msg + '\n\n' : '') + url;
  }

  async function doConnectLink() {
    try {
      const r = await api.connectLink(detail.id);
      setConnectUrl(r.url); setLinkCopied(false);
      try { await navigator.clipboard.writeText(connectText(r.url)); setLinkCopied(true); } catch { /* clipboard may be blocked */ }
    } catch (e) {
      alert(e.message || 'Не удалось получить ссылку');
    }
  }

  async function copyConnectUrl() {
    try {
      await navigator.clipboard.writeText(connectText());
      setLinkCopied(true); setTimeout(() => setLinkCopied(false), 1800);
    } catch { /* clipboard blocked — user can select the field manually */ }
  }

  // Cancelled + expired bookings in range — kept (struck-through) so they can be
  // restored; their dates read as free for new bookings.
  const freed = useMemo(
    () => reservations.filter((r) => r.status === 'CANCELLED' || r.status === 'EXPIRED'),
    [reservations]
  );

  async function doRestore(id) {
    if (!confirm('Восстановить эту бронь? Даты снова станут занятыми.')) return;
    try {
      await api.restoreReservation(id);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось восстановить');
    }
  }

  async function doDelete(id) {
    if (!confirm('Удалить эту бронь НАВСЕГДА? Это действие необратимо.')) return;
    if (!confirm('Вы уверены? Бронь будет удалена без возможности восстановления.')) return;
    try {
      await api.deleteReservation(id);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось удалить');
    }
  }

  async function saveDetail() {
    setSavingDetail(true);
    try {
      await api.updateReservation(detail.id, {
        status: detailForm.status,
        check_in: detailForm.check_in,
        check_out: detailForm.check_out,
        guest_name: detailForm.guest_name || null,
        guest_phone: detailForm.guest_phone || null,
        guest_count: detailForm.guest_count ? Number(detailForm.guest_count) : null,
        telegram_username: detailForm.telegram_username || null,
        total_amount: detailForm.total_amount ? Number(detailForm.total_amount) : null,
        note: detailForm.note || null,
        property_id: detailForm.property_id ? Number(detailForm.property_id) : undefined,
      });
      setDetail(null);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось сохранить');
    } finally {
      setSavingDetail(false);
    }
  }

  async function acceptPay() {
    if (!payForm || !payForm.amount || Number(payForm.amount) <= 0) { alert('Введите сумму'); return; }
    setSavingPay(true);
    try {
      const updated = await api.acceptPayment(detail.id, { amount: Number(payForm.amount), payment_method: payForm.method });
      setPayForm(null);
      setDetail(updated);   // refreshes paid/balance/status + reloads ledger via effect
      await load();         // refresh calendar colours (red → confirmed / green)
    } catch (e) {
      alert(e.message || 'Не удалось принять оплату');
    } finally {
      setSavingPay(false);
    }
  }

  async function saveEditPay() {
    if (!editPay || !editPay.amount || Number(editPay.amount) <= 0) { alert('Введите сумму'); return; }
    try {
      const updated = await api.editReservationPayment(detail.id, editPay.id, { amount: Number(editPay.amount), payment_method: editPay.method });
      setEditPay(null);
      setDetail(updated);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось изменить оплату');
    }
  }

  async function deletePay(incomeId) {
    if (!confirm('Удалить эту оплату? Сумма будет вычтена из дохода и кошелька.')) return;
    try {
      const updated = await api.deleteReservationPayment(detail.id, incomeId);
      setDetail(updated);
      await load();
    } catch (e) {
      alert(e.message || 'Не удалось удалить оплату');
    }
  }

  const dow = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <h1 className="text-xl font-bold text-gray-800 mr-auto">{title}</h1>
        <button onClick={() => setStart(addDays(start, -(span - 1)))} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Раньше"><ChevronLeft size={18} /></button>
        <input type="date" value={ymd(start)} onChange={(e) => { setStart(new Date(e.target.value + 'T00:00:00')); setSpan(31); }} className="border border-gray-200 rounded-lg px-2 py-2 text-sm" />
        <button onClick={() => setStart(addDays(start, span - 1))} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50" title="Позже"><ChevronRight size={18} /></button>
        <button onClick={() => openNew(null, null)} className="flex items-center gap-1.5 bg-blue-600 text-white rounded-lg px-3 py-2 text-sm font-medium hover:bg-blue-700"><Plus size={16} /> Бронь</button>
      </div>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>}

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-3 text-xs text-gray-600">
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-red-300" />Не оплачено</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-blue-300" />Подтверждено</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-green-300" />Оплачено</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-orange-300" />Долг</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-gray-400" />Блок</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded bg-gray-100 border border-gray-200" />Истекло</span>
      </div>

      {loading ? (
        <div className="py-16 text-center text-gray-400">Загрузка…</div>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded-xl bg-white" style={{ WebkitOverflowScrolling: 'touch' }}>
          <table className="border-collapse text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 border-b border-r border-gray-200 px-2 py-2 text-left font-semibold text-gray-700 min-w-[92px] w-[92px]">Объект</th>
                {days.map((d) => {
                  const isSat = d.getDay() === 6;
                  const isToday = ymd(d) === ymd(today);
                  const mon = MONTHS_SHORT[d.getMonth()];
                  return (
                    <th key={ymd(d)} className={`border-b border-gray-200 px-1 py-2 text-center font-medium min-w-[72px] ${isToday ? 'bg-blue-50 text-blue-700' : isSat ? 'bg-rose-50 text-rose-600' : 'text-gray-500'}`}>
                      <div className="text-[10px] leading-none">{isToday ? 'сегодня' : dow[d.getDay()]}</div>
                      <div>{String(d.getDate()).padStart(2, '0')}<span className="text-[10px] font-normal">, {mon.charAt(0).toUpperCase() + mon.slice(1)}</span></div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <UnitRow key={u.id} unit={u} days={days} byCell={byCell} onOpen={openNew} onDetail={setDetail} todayStr={ymd(today)} />
              ))}
              {units.length === 0 && (
                <tr><td colSpan={days.length + 1} className="px-3 py-8 text-center text-gray-400">Нет объектов</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && units.length > 0 && (
        <div className="mt-3 text-center">
          <button onClick={() => setSpan((s) => s + 30)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Показать ещё 30 дней →</button>
        </div>
      )}

      {/* Cancelled + expired bookings in range — restore or permanently delete */}
      {freed.length > 0 && (
        <div className="mt-5 border border-gray-200 rounded-xl bg-white p-4">
          <div className="text-sm font-semibold text-gray-600 mb-1">Отменённые и истёкшие брони в этом периоде</div>
          <p className="text-xs text-gray-400 mb-3">Даты свободны для новых броней. Можно восстановить бронь{isOwner ? ' или удалить её навсегда' : ''}.</p>
          <ul className="space-y-2">
            {freed.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-2 first:border-t-0 first:pt-0">
                <span className="text-sm text-gray-400 line-through">
                  <span className="not-italic no-underline text-gray-300 mr-1">{r.status === 'EXPIRED' ? '⌛' : '✕'}</span>
                  {r.property_name} · {r.guest_name || r.source_label} · {r.check_in}→{r.check_out}
                  {r.total_amount != null ? ` · ${money(r.total_amount)} сум` : ''}
                </span>
                <span className="flex gap-2">
                  <button onClick={() => doRestore(r.id)} className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium hover:bg-blue-100">Восстановить</button>
                  {isOwner && (
                    <button onClick={() => doDelete(r.id)} className="px-3 py-1.5 rounded-lg bg-red-50 text-red-600 text-xs font-medium hover:bg-red-100">Удалить навсегда</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* New booking — step 1 (details) → step 2 (prepayment) */}
      {form && (
        <Modal onClose={() => setForm(null)} title={form.step === 2 ? 'Предоплата · шаг 2 из 2' : 'Новая бронь · шаг 1 из 2'}>
          {form.step === 1 ? (
            <form onSubmit={submitNew} className="space-y-3">
              <Field label="Объект">
                <select required value={form.property_id} onChange={(e) => updateForm({ property_id: e.target.value })} className="input">
                  {units.map((u) => <option key={u.id} value={u.id}>{u.name_ru}</option>)}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Заезд"><input type="date" required value={form.check_in} onChange={(e) => updateForm({ check_in: e.target.value })} className="input" /></Field>
                <Field label="Выезд"><input type="date" required value={form.check_out} onChange={(e) => updateForm({ check_out: e.target.value })} className="input" /></Field>
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
                <Field label="Телефон"><input value={form.guest_phone} onChange={(e) => setForm({ ...form, guest_phone: e.target.value })} className="input" placeholder="+998…" /></Field>
                <Field label="Telegram (ник)"><input value={form.telegram_username} onChange={(e) => setForm({ ...form, telegram_username: e.target.value })} className="input" placeholder="@username" /></Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Гостей"><input type="number" min="1" value={form.guest_count} onChange={(e) => setForm({ ...form, guest_count: e.target.value })} className="input" /></Field>
                <Field label="Сумма (сум)"><input type="number" value={form.total_amount} onChange={(e) => setForm({ ...form, total_amount: e.target.value })} className="input" /></Field>
              </div>
              <Field label="Заметка"><input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className="input" /></Field>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setForm(null)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm">Отмена</button>
                <button type="submit" className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">
                  {form.status === 'BLOCKED' ? 'Создать блок' : 'Далее → предоплата'}
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-3">
              {expires ? (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                  Бронь создана и <b>ждёт предоплаты</b> (красная). Без предоплаты в течение рабочего часа она освободит дату автоматически.
                </div>
              ) : (
                <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
                  Бронь создана. Предоплата <b>необязательна</b> — можно принять её сейчас или позже.
                </div>
              )}
              <div className="text-sm text-gray-600">
                {form.createdRes?.property_name} · {form.check_in}→{form.check_out}
                {form.total_amount ? <> · сумма {money(form.total_amount)} сум</> : null}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Сумма предоплаты (сум)"><input type="number" value={form.payAmount} onChange={(e) => setForm({ ...form, payAmount: e.target.value })} className="input" /></Field>
                <Field label="Способ оплаты">
                  <select value={form.payMethod} onChange={(e) => setForm({ ...form, payMethod: e.target.value })} className="input">
                    {PAYMENT_METHODS.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
                  </select>
                </Field>
              </div>
              <p className="text-xs text-gray-400">Предзаполнено 20% — измените, если клиент платит больше.</p>
              <div className="flex justify-between gap-2 pt-2">
                <button type="button" onClick={() => setForm(null)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm">Позже (оставить красной)</button>
                <button type="button" onClick={submitPrepay} className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700">Провести предоплату</button>
              </div>
            </div>
          )}
        </Modal>
      )}

      {/* Detail / edit modal */}
      {detail && detailForm && (
        <Modal onClose={() => setDetail(null)} title={`${detail.property_name || 'Бронь'}${detail.source_label ? ' · ' + detail.source_label : ''}`}>
          <div className="mb-3 p-2.5 rounded-lg bg-gray-50 text-sm flex items-center justify-between">
            <span className="text-gray-500">Оплачено</span>
            <span className="font-semibold text-gray-800">
              {money(detail.paid_amount || 0)}{detail.total_amount != null ? ` / ${money(detail.total_amount)}` : ''} сум
              {detail.balance != null && detail.balance > 0 ? ` · остаток ${money(detail.balance)}` : ''}
              {detail.balance != null && detail.balance <= 0 ? ' ✓' : ''}
            </span>
          </div>

          {/* Telegram: connect link to message the customer via @balandda_bot */}
          <button onClick={doConnectLink} className="w-full mb-2 px-3 py-2 rounded-lg bg-sky-50 text-sky-700 text-sm font-medium hover:bg-sky-100">
            {detail.telegram_user_id ? '🔗 Telegram привязан · ещё раз ссылку' : '🔗 Ссылка для клиента (Telegram)'}
          </button>
          {connectUrl && (
            <div className="mb-3 bg-sky-50 rounded-lg p-2 space-y-2">
              {bookMsgs && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-sky-700">Язык:</span>
                  {[['ru', 'RU'], ['uz', 'UZ'], ['en', 'EN'], ['zh', '中文']].map(([code, lbl]) => (
                    <button key={code} onClick={() => setMsgLang(code)} className={`px-2 py-0.5 rounded text-xs font-medium ${msgLang === code ? 'bg-sky-600 text-white' : 'bg-white text-sky-700 border border-sky-200'}`}>{lbl}</button>
                  ))}
                </div>
              )}
              <textarea readOnly value={connectText()} onFocus={(e) => e.target.select()} className="w-full bg-white/70 rounded-md text-xs text-sky-900 p-2 outline-none resize-none" rows={bookMsgs ? 4 : 2} />
              <button onClick={copyConnectUrl} className="w-full px-2.5 py-1.5 rounded-md bg-sky-600 text-white text-xs font-medium hover:bg-sky-700">
                {linkCopied ? 'Скопировано ✓' : '📋 Копировать сообщение + ссылку'}
              </button>
            </div>
          )}

          {/* Unpaid hold → agent can grant more time or waive prepayment */}
          {detail.status === 'HOLD' && (
            <div className="mb-3 grid grid-cols-2 gap-2">
              <button onClick={doExtendHold} className="px-3 py-2 rounded-lg bg-amber-50 text-amber-700 text-sm font-medium hover:bg-amber-100">⏳ Продлить до 24 ч</button>
              <button onClick={doWaivePrepay} className="px-3 py-2 rounded-lg bg-blue-50 text-blue-700 text-sm font-medium hover:bg-blue-100">Без предоплаты</button>
            </div>
          )}

          {/* Payment ledger — partial payments (each editable / removable) */}
          {payments.length > 0 && (
            <div className="mb-3 rounded-lg border border-gray-200 divide-y divide-gray-100">
              {payments.map((p) => (
                <div key={p.id} className="px-3 py-2 text-sm">
                  {editPay && editPay.id === p.id ? (
                    <div className="flex items-center gap-2">
                      <input type="number" value={editPay.amount} onChange={(e) => setEditPay({ ...editPay, amount: e.target.value })} className="input flex-1" />
                      <select value={editPay.method} onChange={(e) => setEditPay({ ...editPay, method: e.target.value })} className="input flex-1">
                        {PAYMENT_METHODS.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
                      </select>
                      <button onClick={saveEditPay} className="text-blue-600 text-xs font-semibold">OK</button>
                      <button onClick={() => setEditPay(null)} className="text-gray-400 text-sm">×</button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-gray-700"><b>{money(p.amount)}</b> сум · {p.payment_method_label}</span>
                      <span className="flex items-center gap-2.5 text-xs">
                        <span className="text-gray-400">{p.report_date}</span>
                        <button onClick={() => setEditPay({ id: p.id, amount: String(Math.round(p.amount)), method: p.payment_method })} className="text-blue-600 hover:underline">изм.</button>
                        <button onClick={() => deletePay(p.id)} className="text-red-500 hover:underline">удал.</button>
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!payForm ? (
            <button
              onClick={() => setPayForm({ amount: String(Math.max(0, Math.round(detail.balance ?? 0)) || ''), method: 'CASH' })}
              className="w-full mb-3 px-3 py-2 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700"
            >➕ Добавить оплату / предоплату</button>
          ) : (
            <div className="mb-3 p-3 rounded-lg border border-green-200 bg-green-50 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <input type="number" placeholder="Сумма" value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} className="input" />
                <select value={payForm.method} onChange={(e) => setPayForm({ ...payForm, method: e.target.value })} className="input">
                  {PAYMENT_METHODS.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
                </select>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => setPayForm(null)} className="px-3 py-1.5 rounded-lg border border-gray-200 text-sm">Отмена</button>
                <button onClick={acceptPay} disabled={savingPay} className="px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50">{savingPay ? '…' : 'Провести оплату'}</button>
              </div>
            </div>
          )}
          {/* Prepayment with proof screenshot — saved to the SAME prepayments table as the bot */}
          <div className="mb-4 pt-3 border-t border-gray-100">
            <div className="text-xs font-semibold text-gray-500 mb-2">Предоплаты (скриншот-подтверждение)</div>
            {prepays.length > 0 && (
              <ul className="space-y-1.5 mb-2">
                {prepays.map((p) => (
                  <li key={p.id} className="flex items-center justify-between text-sm bg-gray-50 rounded-lg px-3 py-1.5">
                    <span>{Number(p.amount).toLocaleString('ru-RU')} сум · <span className="text-gray-500">{p.status_label}</span></span>
                    {p.has_screenshot
                      ? <button onClick={() => viewShot(p.id)} className="text-blue-600 hover:underline text-xs">📸 Скриншот</button>
                      : <span className="text-gray-400 text-xs">без фото</span>}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex items-center gap-2 flex-wrap">
              <label className="px-3 py-1.5 rounded-lg border border-gray-200 text-sm cursor-pointer hover:bg-gray-50">
                {preFile ? '✅ Фото выбрано' : '📎 Выбрать скриншот'}
                <input type="file" accept="image/*" hidden onChange={(e) => setPreFile(e.target.files[0] || null)} />
              </label>
              <button onClick={addPrepay} disabled={savingPre || !preFile} className="px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm font-medium hover:bg-green-700 disabled:opacity-50">{savingPre ? '…' : 'Добавить скриншот'}</button>
            </div>
            <p className="text-xs text-gray-400 mt-1">Скриншот-подтверждение оплаты. Сохраняется в общую базу предоплат (как из бота @berdiev_shavkat_bot).</p>
          </div>
          <div className="space-y-3">
            <Field label="Объект">
              <select value={detailForm.property_id} onChange={(e) => setDetailForm({ ...detailForm, property_id: e.target.value })} className="input">
                {units.map((u) => <option key={u.id} value={u.id}>{u.name_ru}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Заезд"><input type="date" value={detailForm.check_in} onChange={(e) => setDetailForm({ ...detailForm, check_in: e.target.value })} className="input" /></Field>
              <Field label="Выезд"><input type="date" value={detailForm.check_out} onChange={(e) => setDetailForm({ ...detailForm, check_out: e.target.value })} className="input" /></Field>
            </div>
            <Field label="Статус">
              <select value={detailForm.status} onChange={(e) => setDetailForm({ ...detailForm, status: e.target.value })} className="input">
                {Object.keys(STATUS_STYLE).filter((s) => s !== 'CANCELLED' && s !== 'EXPIRED').map((s) => <option key={s} value={s}>{STATUS_STYLE[s].label}</option>)}
              </select>
            </Field>
            <Field label="Имя гостя"><input value={detailForm.guest_name} onChange={(e) => setDetailForm({ ...detailForm, guest_name: e.target.value })} className="input" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Телефон"><input value={detailForm.guest_phone} onChange={(e) => setDetailForm({ ...detailForm, guest_phone: e.target.value })} className="input" /></Field>
              <Field label="Telegram (ник)"><input value={detailForm.telegram_username} onChange={(e) => setDetailForm({ ...detailForm, telegram_username: e.target.value })} className="input" placeholder="@username" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Гостей"><input type="number" min="1" value={detailForm.guest_count} onChange={(e) => setDetailForm({ ...detailForm, guest_count: e.target.value })} className="input" /></Field>
              <Field label="Сумма (сум)"><input type="number" value={detailForm.total_amount} onChange={(e) => setDetailForm({ ...detailForm, total_amount: e.target.value })} className="input" /></Field>
            </div>
            <Field label="Заметка"><input value={detailForm.note} onChange={(e) => setDetailForm({ ...detailForm, note: e.target.value })} className="input" /></Field>
          </div>
          <div className="flex justify-between items-center gap-2 pt-4">
            <button onClick={() => doCancel(detail.id)} className="px-3 py-2 rounded-lg bg-red-50 text-red-600 text-sm font-medium hover:bg-red-100">Отменить</button>
            <div className="flex gap-2">
              <button onClick={() => setDetail(null)} className="px-4 py-2 rounded-lg border border-gray-200 text-sm">Закрыть</button>
              <button onClick={saveDetail} disabled={savingDetail} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">{savingDetail ? 'Сохранение…' : 'Сохранить'}</button>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-gray-100">
            <div className="text-xs font-semibold text-gray-500 mb-2">История изменений</div>
            {events.length === 0 ? (
              <p className="text-xs text-gray-400">Нет записей</p>
            ) : (
              <ul className="space-y-1.5 max-h-40 overflow-y-auto">
                {events.map((ev) => (
                  <li key={ev.id} className="text-xs text-gray-600 leading-snug">
                    <span className="text-gray-400">{fmtDateTime(ev.created_at)}</span>{' · '}
                    <span className="font-medium text-gray-700">{ev.actor_name || 'Система'}</span>{' · '}
                    {ACTION_LABELS[ev.action] || ev.action}{ev.detail ? `: ${ev.detail}` : ''}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Modal>
      )}

      <style>{`.input{width:100%;border:1px solid #e5e7eb;border-radius:0.5rem;padding:0.5rem 0.625rem;font-size:0.875rem}`}</style>
    </div>
  );
}

// One unit's row as a tape chart: bookings render as bars (colSpan over their nights)
// showing guest name + phone; empty days are clickable to create a booking.
// Compact display names for the narrow unit column (agents know the units well).
function shortName(n) {
  return String(n || '')
    .replace(/Белое\s*Шале/gi, 'Белое')
    .replace(/Апартаменты?/gi, 'Апарт.')
    .replace(/SPA\s*Сьют|Спа\s*(номер|сьют)?/gi, 'SPA')
    .replace(/Вилла\s*Infinity|Infinity\s*Villa/gi, 'Вилла')
    .replace(/\s+/g, ' ')
    .trim();
}

function UnitRow({ unit, days, byCell, onOpen, onDetail, todayStr }) {
  const cells = [];
  let i = 0;
  while (i < days.length) {
    const d = days[i];
    const r = byCell.get(`${unit.id}|${ymd(d)}`);
    if (r) {
      let len = 1;
      while (i + len < days.length) {
        const rr = byCell.get(`${unit.id}|${ymd(days[i + len])}`);
        if (rr && rr.id === r.id) len++; else break;
      }
      const total = r.total_amount;
      const paid = r.paid_amount || 0;
      const fullyPaid = total != null && total > 0 && paid + 1 >= total;
      const line2 = r.guest_phone || (total != null ? money(total) + ' сум' : '');
      cells.push(
        <td key={ymd(d)} colSpan={len} className="border-b border-gray-100 p-0.5 align-top">
          <button onClick={() => onDetail(r)} title={`${r.guest_name || r.source_label} · ${r.guest_phone || ''} · ${r.check_in}→${r.check_out}`}
            className={`w-full h-12 rounded ${barClass(r, todayStr)} px-1.5 text-left leading-tight overflow-hidden transition-colors`}>
            <div className="text-[11px] font-semibold truncate">{fullyPaid ? '✓ ' : ''}{cap(r.guest_name || r.source_label)}</div>
            <div className="text-[11px] truncate opacity-80">{cap(line2)}</div>
          </button>
        </td>
      );
      i += len;
    } else {
      const isSat = d.getDay() === 6;
      cells.push(
        <td key={ymd(d)} className={`border-b border-gray-100 p-0 ${isSat ? 'bg-rose-50/40' : ''}`}>
          <button onClick={() => onOpen(unit, d)} className="w-full h-12 hover:bg-blue-100 transition-colors" />
        </td>
      );
      i += 1;
    }
  }
  return (
    <tr>
      <td className="sticky left-0 z-10 bg-white border-b border-r border-gray-200 px-2 py-1.5 font-medium text-gray-800 text-xs leading-tight min-w-[92px] w-[92px]">
        {shortName(unit.name_ru)}
      </td>
      {cells}
    </tr>
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
