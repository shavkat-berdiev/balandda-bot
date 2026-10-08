// Telegram Mini App: operator books a guest from a @balandda_chimgan chat without leaving
// Telegram. Opened from the «✍️ Оформить бронь» button on a /бронь card in «Брони»
// (t.me/balandda_bot/<app>?startapp=<draft token>). Sign-in is Telegram's own signed
// launch data, checked server-side against the calendar's staff (POST /api/v1/tgapp/auth).
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';

const DISCOUNTS = [0, 5, 10, 15, 20, 25, 30, 50];
const REASONS = [
  ['PROMOTION', 'Акция'], ['VIP_GUEST', 'VIP гость'], ['BIRTHDAY', 'День рождения'],
  ['FAVORITE_GUEST', 'Любимый гость'], ['OTHER', 'Другое'],
];

function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return ymd(d);
}
function nights(ci, co) {
  return Math.round((new Date(co + 'T00:00:00') - new Date(ci + 'T00:00:00')) / 864e5);
}
function money(n) {
  return n ? Math.round(n).toLocaleString('ru-RU') : '0';
}
function fmt(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}
function langFromPhone(phone) {
  const ph = (phone || '').replace(/\D/g, '');
  return !ph || ph.startsWith('998') || ph.length === 9 ? 'ru' : 'en';
}
function loadTelegram() {
  return new Promise((resolve) => {
    if (window.Telegram?.WebApp) return resolve(window.Telegram.WebApp);
    const s = document.createElement('script');
    s.src = 'https://telegram.org/js/telegram-web-app.js';
    s.onload = () => resolve(window.Telegram?.WebApp || null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-gray-500 mb-1">{label}</span>
      {children}
    </label>
  );
}

export default function TgApp() {
  const [wa, setWa] = useState(null);
  const [phase, setPhase] = useState('loading'); // loading | noTg | denied | form | saving | done
  const [error, setError] = useState('');
  const [operator, setOperator] = useState(null);
  const [draft, setDraft] = useState(null);
  const [units, setUnits] = useState([]);
  const [f, setF] = useState(null);
  const [avail, setAvail] = useState(null);   // { error, codes:Set }
  const [prices, setPrices] = useState({});   // property_id -> stay sum
  const [created, setCreated] = useState(null);
  const [lang, setLang] = useState('ru');
  const [sent, setSent] = useState('');
  const [sending, setSending] = useState(false);

  // 1. Telegram sign-in → session token → draft + units
  useEffect(() => {
    (async () => {
      const w = await loadTelegram();
      setWa(w);
      try { w?.ready(); w?.expand(); } catch { /* ignore */ }
      if (!w || !w.initData) { setPhase('noTg'); return; }
      try {
        const r = await fetch('/api/v1/tgapp/auth', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: w.initData }),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { setError(j.detail || 'Нет доступа'); setPhase('denied'); return; }
        localStorage.setItem('token', j.token);
        localStorage.setItem('user', JSON.stringify(j.user));
        setOperator(j.user);
        const token = j.start_param || new URLSearchParams(window.location.search).get('tgdraft');
        const [props, d] = await Promise.all([
          api.getAdminProperties(),
          token ? api.tgDraft(token).catch(() => null) : Promise.resolve(null),
        ]);
        const resort = (props || []).filter((p) => p.is_active && p.business_unit === 'RESORT')
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        setUnits(resort);
        setDraft(d ? { ...d, token } : null);
        const today = ymd(new Date());
        const ci = d?.check_in && d.check_in >= today ? d.check_in : today;
        const co = d?.check_out && d.check_out > ci ? d.check_out : addDays(ci, 1);
        setF({
          property_id: resort[0]?.id ?? '', check_in: ci, check_out: co,
          guest_name: d?.customer_name || '', guest_phone: d?.phone || '', guest_email: '',
          guest_count: d?.guests ? String(d.guests) : '', status: 'HOLD',
          discount: 0, discount_reason: '', note: '',
        });
        setLang(langFromPhone(d?.phone));
        setPhase('form');
      } catch (e) {
        setError(e.message || 'Ошибка загрузки');
        setPhase('denied');
      }
    })();
  }, []);

  // 2. Free units + prices for the chosen dates
  useEffect(() => {
    if (!f || !f.check_in || !f.check_out || f.check_out <= f.check_in) return;
    let cancelled = false;
    fetch(`/api/v1/public/availability?check_in=${f.check_in}&check_out=${f.check_out}&guests=1`)
      .then((r) => r.json())
      .then((j) => { if (!cancelled) setAvail({ error: j.error || null, codes: new Set((j.available_units || []).map((u) => u.code)) }); })
      .catch(() => { if (!cancelled) setAvail(null); });
    api.getRatePreview({ date_from: f.check_in, date_to: addDays(f.check_out, -1) })
      .then((r) => {
        if (cancelled) return;
        const m = {};
        (r.units || []).forEach((u) => { m[u.property_id] = (u.nights || []).reduce((s, n) => s + (Number(n.price) || 0), 0); });
        setPrices(m);
      })
      .catch(() => { if (!cancelled) setPrices({}); });
    return () => { cancelled = true; };
  }, [f?.check_in, f?.check_out]);

  const isFree = (u) => !avail || avail.error || avail.codes.has(u.code);
  const unit = useMemo(() => units.find((u) => u.id === Number(f?.property_id)), [units, f?.property_id]);
  const base = unit ? prices[unit.id] || 0 : 0;
  const total = Math.round(base * (1 - (Number(f?.discount) || 0) / 100));
  const n = f ? nights(f.check_in, f.check_out) : 0;

  function set(patch) {
    setF((x) => {
      const next = { ...x, ...patch };
      if ('check_in' in patch && next.check_out <= next.check_in) next.check_out = addDays(next.check_in, 1);
      return next;
    });
  }

  async function save() {
    if (!f.property_id) return alert('Выберите объект');
    if (f.check_out <= f.check_in) return alert('Дата выезда должна быть позже заезда');
    if (unit && !isFree(unit) && !confirm(`${unit.name_ru} занят на эти даты по данным сайта. Всё равно попробовать?`)) return;
    setPhase('saving');
    try {
      const res = await api.createReservation({
        property_id: Number(f.property_id), check_in: f.check_in, check_out: f.check_out,
        guest_name: f.guest_name || null, guest_phone: f.guest_phone || null,
        guest_email: (f.guest_email || '').trim() || null,
        guest_count: f.guest_count ? Number(f.guest_count) : null,
        telegram_username: draft?.username || null,
        status: f.status, source: 'TELEGRAM',
        total_amount: null, deposit_amount: null,
        discount_percent: Number(f.discount) || 0,
        discount_reason: f.discount ? (f.discount_reason || 'OTHER') : null,
        note: f.note || null,
        tg_draft: draft?.token || undefined,
      });
      setCreated(res);
      setPhase('done');
      try { wa?.HapticFeedback?.notificationOccurred('success'); } catch { /* ignore */ }
    } catch (e) {
      setPhase('form');
      alert(e.message || 'Не удалось создать бронь');
    }
  }

  async function sendPay() {
    setSending(true);
    try {
      const r = await api.tgSend(created.id, { kind: 'pay', lang });
      const where = r.via === 'business' ? 'в чат @balandda_chimgan' : r.via === 'bot' ? 'в @balandda_bot' : 'в Telegram';
      setSent(r.ok ? `✓ Счёт отправлен клиенту ${where}` : `⚠️ Не отправлено: ${r.error || 'ошибка'}`);
    } catch (e) {
      setSent(`⚠️ ${e.message || 'Не удалось отправить'}`);
    } finally {
      setSending(false);
    }
  }

  const input = 'w-full border border-gray-200 rounded-lg px-3 py-2.5 text-[15px] bg-white focus:outline-none focus:ring-2 focus:ring-sky-400';
  const shell = (body) => <div className="min-h-screen bg-gray-50 text-gray-900 px-4 py-4">{body}</div>;

  if (phase === 'loading') {
    return shell(<div className="flex justify-center pt-24"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-600" /></div>);
  }
  if (phase === 'noTg') {
    return shell(<div className="pt-16 text-center text-gray-600">Откройте эту страницу из Telegram — кнопкой «✍️ Оформить бронь» в группе операторов.</div>);
  }
  if (phase === 'denied') {
    return shell(<div className="pt-16 text-center"><div className="text-3xl mb-2">🔒</div><div className="text-gray-700">{error}</div></div>);
  }

  if (phase === 'done' && created) {
    return shell(
      <div className="space-y-4">
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <div className="text-green-600 font-semibold">✅ Бронь №{created.id} создана</div>
          <div className="mt-2 text-[15px] leading-6">
            <div><b>{unit?.name_ru}</b></div>
            <div>{fmt(created.check_in)} → {fmt(created.check_out)} · {nights(created.check_in, created.check_out)} ноч.</div>
            <div>{created.guest_name}{created.guest_phone ? ` · ${created.guest_phone}` : ''}</div>
            {created.total_amount ? <div>Стоимость: <b>{money(created.total_amount)} сум</b></div> : null}
            <div className="text-xs text-gray-500 mt-1">{created.status === 'HOLD' ? 'Ожидает оплаты — таймер брони запущен' : 'Подтверждена'}</div>
          </div>
        </div>

        {created.telegram_user_id ? (
          <div className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Язык сообщения клиенту</span>
              <span className="flex gap-1">
                {['ru', 'uz', 'en'].map((l) => (
                  <button key={l} onClick={() => setLang(l)}
                    className={`px-2.5 py-1 rounded-md text-xs font-semibold ${lang === l ? 'bg-sky-600 text-white' : 'bg-gray-100 text-gray-700'}`}>{l.toUpperCase()}</button>
                ))}
              </span>
            </div>
            <button onClick={sendPay} disabled={sending}
              className="w-full py-3 rounded-xl bg-sky-600 text-white font-semibold disabled:opacity-50">
              {sending ? 'Отправка…' : '💳 Отправить клиенту счёт на оплату'}
            </button>
            {sent && <div className="text-sm">{sent}</div>}
            <div className="text-xs text-gray-500">Клиент получит сумму, кнопки оплаты 20% / 100% −5% и ссылку на бота.</div>
          </div>
        ) : null}

        <button onClick={() => wa?.close()} className="w-full py-3 rounded-xl bg-gray-900 text-white font-semibold">Готово</button>
        <button onClick={() => wa?.openLink('https://calendar.balandda.uz/calendar')} className="w-full py-2 text-sm text-sky-700">Открыть календарь</button>
      </div>,
    );
  }

  return shell(
    <div className="space-y-4 pb-24">
      <div>
        <div className="text-lg font-bold">Новая бронь</div>
        <div className="text-sm text-gray-500">
          {draft ? <>💬 из чата @balandda_chimgan · <b>{[draft.customer_name, draft.username ? '@' + draft.username : null].filter(Boolean).join(' · ')}</b></> : 'без привязки к чату'}
        </div>
        {draft?.status === 'booked' && draft.reservation_id
          ? <div className="mt-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">По этому чату уже оформлена бронь №{draft.reservation_id}.</div> : null}
        {operator ? <div className="text-xs text-gray-400 mt-0.5">Оператор: {operator.full_name}</div> : null}
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Заезд"><input type="date" value={f.check_in} onChange={(e) => set({ check_in: e.target.value })} className={input} /></Field>
          <Field label="Выезд"><input type="date" value={f.check_out} min={addDays(f.check_in, 1)} onChange={(e) => set({ check_out: e.target.value })} className={input} /></Field>
        </div>
        <div className="text-xs text-gray-500">{n} ноч.{avail?.error ? ' · ⚠️ даты закрыты для онлайн-продажи — бронь всё равно можно создать' : ''}</div>
        <Field label="Объект">
          <select value={f.property_id} onChange={(e) => set({ property_id: e.target.value })} className={input}>
            {units.map((u) => (
              <option key={u.id} value={u.id} disabled={!isFree(u)}>
                {u.name_ru}{isFree(u) ? (prices[u.id] ? ` — ${money(prices[u.id])} сум` : '') : ' — занято'}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Скидка">
            <select value={f.discount} onChange={(e) => set({ discount: Number(e.target.value) })} className={input}>
              {DISCOUNTS.map((d) => <option key={d} value={d}>{d ? `${d}%` : 'Без скидки'}</option>)}
            </select>
          </Field>
          <Field label="Причина скидки">
            <select value={f.discount_reason} disabled={!f.discount} onChange={(e) => set({ discount_reason: e.target.value })} className={input}>
              <option value="">—</option>
              {REASONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="rounded-xl bg-sky-50 px-3 py-2.5 text-[15px]">
          Итого: <b>{total ? `${money(total)} сум` : '—'}</b>
          {total ? <span className="text-sm text-gray-600"> · предоплата 20%: {money(total * 0.2)} сум</span> : null}
        </div>
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
        <Field label="Имя гостя"><input value={f.guest_name} onChange={(e) => set({ guest_name: e.target.value })} className={input} /></Field>
        <Field label="Телефон"><input type="tel" value={f.guest_phone} onChange={(e) => set({ guest_phone: e.target.value })} className={input} placeholder="+998…" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Гостей"><input type="number" min="1" value={f.guest_count} onChange={(e) => set({ guest_count: e.target.value })} className={input} /></Field>
          <Field label="Статус">
            <select value={f.status} onChange={(e) => set({ status: e.target.value })} className={input}>
              <option value="HOLD">Ожидает оплаты</option>
              <option value="CONFIRMED">Подтверждена</option>
            </select>
          </Field>
        </div>
        <Field label="E-mail (для ваучера)"><input type="email" value={f.guest_email} onChange={(e) => set({ guest_email: e.target.value })} className={input} placeholder="необязательно" /></Field>
        <Field label="Заметка"><input value={f.note} onChange={(e) => set({ note: e.target.value })} className={input} /></Field>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-white/95 border-t border-gray-200 px-4 py-3">
        <button onClick={save} disabled={phase === 'saving'}
          className="w-full py-3 rounded-xl bg-sky-600 text-white font-semibold disabled:opacity-50">
          {phase === 'saving' ? 'Сохранение…' : `Создать бронь${total ? ` · ${money(total)} сум` : ''}`}
        </button>
      </div>
    </div>,
  );
}
