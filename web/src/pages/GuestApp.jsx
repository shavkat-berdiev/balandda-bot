// Guest booking Mini App (@balandda_bot). Opened from the bot's «🗓 Забронировать» button,
// the chat menu button, or an operator's «📨 анкета» link (startapp=g_<draft token>).
// Every server call carries Telegram's signed initData, verified on the server.
import { useEffect, useMemo, useState } from 'react';

const IMG = 'https://www.balandda.uz/assets/img/';
const PHOTO = {
  CHALET_WITH_SAUNA: 'chalet_03.jpg', CHALET_WITHOUT_SAUNA: 'chalet_05.jpg', WHITE_CHALET: 'banner_img_01.jpg',
  APARTMENT: 'apart_1.jpg', PENTHOUSE: 'pent_1.jpg', VILLA: 'villa_1.jpg', SPA_SUITE: 'spa_03.jpg',
};

const T = {
  ru: {
    title: 'Бронирование', sub: 'Balandda Chimgan · горы, 1,5 ч от Ташкента',
    dates: 'Даты', pick_in: 'Выберите дату заезда', pick_out: 'Теперь — дату выезда',
    nights: (n) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'ночь' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'ночи' : 'ночей'}`,
    stay: 'Размещение', guests: 'Гостей', upto: (n) => `до ${n} гостей`, none: 'нет мест на эти даты',
    for_stay: 'за проживание', choose_dates_first: 'Выберите даты, чтобы увидеть цены и свободные дома',
    contact: 'Контакты', name: 'Имя и фамилия', phone: 'Телефон', share: '📱 Поделиться номером из Telegram',
    email: 'E-mail (необязательно — пришлём ваучер)', book: 'Забронировать', total: 'Итого',
    agree: 'Нажимая «Забронировать», вы принимаете условия публичной оферты balandda.uz/offer.html',
    created: 'Бронь создана', hold: 'Мы держим бронь за вами 60 минут. Оплатите онлайн — бронь подтвердится автоматически.',
    pay_dep: (v) => `💳 Предоплата 20% — ${v} сум`, pay_full: (v) => `✅ 100% со скидкой 5% — ${v} сум`,
    later: 'Оплачу позже', paid_note: 'После оплаты ваучер придёт в этот чат.',
    closed: 'закрыто', err_dates: 'Выберите даты заезда и выезда', err_type: 'Выберите размещение',
    err_name: 'Укажите имя', err_phone: 'Укажите телефон', taken: 'Этот вариант только что заняли — выберите другой',
    fail: 'Не удалось создать бронь. Напишите нам: t.me/balandda_chimgan', open_tg: 'Откройте бронирование из Telegram.',
    dates_blocked: 'Эти даты закрыты для бронирования', dates_window: 'Продажи на эти даты ещё не открыты', dates_past: 'Дата заезда уже прошла', too_many: 'У вас уже есть неоплаченные брони — оплатите их или напишите нам', write: 'Разрешите боту присылать сообщения — так придут счёт и ваучер',
    uzs: 'сум', from: 'от', reception: 'Вопросы — ресепшн +998 99 018 70 77',
  },
  uz: {
    title: 'Bron qilish', sub: "Balandda Chimgan · tog'lar, Toshkentdan 1,5 soat",
    dates: 'Sanalar', pick_in: 'Kelish sanasini tanlang', pick_out: 'Endi — ketish sanasini',
    nights: (n) => `${n} kecha`,
    stay: 'Joylashuv', guests: 'Mehmonlar', upto: (n) => `${n} mehmongacha`, none: "bu sanalarga joy yo'q",
    for_stay: 'yashash uchun', choose_dates_first: "Narxlar va bo'sh uylarni ko'rish uchun sanalarni tanlang",
    contact: "Aloqa", name: 'Ism va familiya', phone: 'Telefon', share: "📱 Telegramdagi raqamni ulashish",
    email: "E-mail (ixtiyoriy — vaucher yuboramiz)", book: 'Bron qilish', total: 'Jami',
    agree: "«Bron qilish» tugmasini bosib, siz balandda.uz/offer.html ommaviy oferta shartlarini qabul qilasiz",
    created: 'Bron yaratildi', hold: "Bronni 60 daqiqa saqlaymiz. Onlayn to'lang — bron avtomatik tasdiqlanadi.",
    pay_dep: (v) => `💳 20% oldindan to'lov — ${v} so'm`, pay_full: (v) => `✅ 100%, 5% chegirma — ${v} so'm`,
    later: "Keyinroq to'layman", paid_note: "To'lovdan so'ng vaucher shu chatga keladi.",
    closed: 'yopiq', err_dates: 'Kelish va ketish sanalarini tanlang', err_type: 'Joylashuvni tanlang',
    err_name: 'Ismingizni kiriting', err_phone: 'Telefon raqamini kiriting', taken: "Bu variant hozirgina band qilindi — boshqasini tanlang",
    fail: "Bron yaratib bo'lmadi. Bizga yozing: t.me/balandda_chimgan", open_tg: 'Bronni Telegramdan oching.',
    dates_blocked: 'Bu sanalar bron uchun yopiq', dates_window: 'Bu sanalarga sotuv hali ochilmagan', dates_past: "Kelish sanasi o'tib ketgan", too_many: "Sizda to'lanmagan bronlar bor — ularni to'lang yoki bizga yozing", write: "Botga xabar yuborishga ruxsat bering — hisob va vaucher shu yerga keladi",
    uzs: "so'm", from: '', reception: "Savollar — resepshn +998 99 018 70 77",
  },
  en: {
    title: 'Booking', sub: 'Balandda Chimgan · mountains, 1.5 h from Tashkent',
    dates: 'Dates', pick_in: 'Choose your check-in date', pick_out: 'Now choose check-out',
    nights: (n) => `${n} night${n === 1 ? '' : 's'}`,
    stay: 'Accommodation', guests: 'Guests', upto: (n) => `up to ${n} guests`, none: 'not available for these dates',
    for_stay: 'for the stay', choose_dates_first: 'Choose dates to see prices and free houses',
    contact: 'Contact', name: 'Full name', phone: 'Phone', share: '📱 Share my Telegram number',
    email: 'E-mail (optional — we send the voucher)', book: 'Book now', total: 'Total',
    agree: 'By tapping «Book now» you accept the public offer at balandda.uz/offer.html',
    created: 'Booking created', hold: 'We hold the booking for 60 minutes. Pay online and it is confirmed automatically.',
    pay_dep: (v) => `💳 20% deposit — ${v} UZS`, pay_full: (v) => `✅ 100% with 5% off — ${v} UZS`,
    later: "I'll pay later", paid_note: 'After payment the voucher arrives in this chat.',
    closed: 'closed', err_dates: 'Choose check-in and check-out dates', err_type: 'Choose accommodation',
    err_name: 'Enter your name', err_phone: 'Enter your phone', taken: 'This option was just taken — please choose another',
    fail: 'Could not create the booking. Message us: t.me/balandda_chimgan', open_tg: 'Open the booking from Telegram.',
    dates_blocked: 'These dates are closed for booking', dates_window: 'Sales for these dates are not open yet', dates_past: 'The check-in date has passed', too_many: 'You already have unpaid bookings — pay them or message us', write: 'Allow the bot to message you — the invoice and voucher arrive there',
    uzs: 'UZS', from: 'from', reception: 'Questions — reception +998 99 018 70 77',
  },
};
const MONTHS = {
  ru: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
  uz: ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
};
const DOW = { ru: ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'], uz: ['du', 'se', 'ch', 'pa', 'ju', 'sh', 'ya'], en: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'] };

function ymd(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function addDays(iso, n) { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return ymd(d); }
function nightsOf(ci, co) { return Math.round((new Date(co + 'T00:00:00') - new Date(ci + 'T00:00:00')) / 864e5); }
function money(n) { return n ? Math.round(n).toLocaleString('ru-RU') : '0'; }
function fmt(iso, lang) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return `${d.getDate()} ${MONTHS[lang][d.getMonth()].slice(0, 3).toLowerCase()}`;
}

async function post(path, body) {
  const r = await fetch('/api/v1/tgapp' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.detail || 'error'), { status: r.status, data: j });
  return j;
}

function RangeCalendar({ lang, rules, ci, co, onChange }) {
  const today = rules?.today || ymd(new Date());
  const max = rules?.max_date || addDays(today, 270);
  const [ym, setYm] = useState(() => (ci || today).slice(0, 7));
  const blocked = (iso) => (rules?.blocked || []).some((b) => b.from <= iso && iso <= (b.to || b.from));
  const rangeBlocked = (a, b) => (rules?.blocked || []).some((x) => a <= (x.to || x.from) && b > x.from);
  const [y, m] = ym.split('-').map(Number);
  const first = new Date(y, m - 1, 1);
  const lead = (first.getDay() + 6) % 7;
  const dim = new Date(y, m, 0).getDate();
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= dim; d++) cells.push(`${ym}-${String(d).padStart(2, '0')}`);
  const shift = (k) => { const d = new Date(y, m - 1 + k, 1); setYm(ymd(d).slice(0, 7)); };
  const canPrev = ym > today.slice(0, 7);
  const canNext = ym < max.slice(0, 7);

  function tap(iso) {
    if (!ci || (ci && co)) { onChange(iso, null); return; }
    if (iso <= ci) { onChange(iso, null); return; }
    if (nightsOf(ci, iso) > 30 || rangeBlocked(ci, iso)) { onChange(iso, null); return; }
    onChange(ci, iso);
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <button onClick={() => canPrev && shift(-1)} className={`w-9 h-9 rounded-full ${canPrev ? 'bg-gray-100' : 'opacity-0'}`}>‹</button>
        <div className="font-semibold">{MONTHS[lang][m - 1]} {y}</div>
        <button onClick={() => canNext && shift(1)} className={`w-9 h-9 rounded-full ${canNext ? 'bg-gray-100' : 'opacity-0'}`}>›</button>
      </div>
      <div className="grid grid-cols-7 text-center text-[11px] text-gray-400 mb-1">{DOW[lang].map((d) => <div key={d}>{d}</div>)}</div>
      <div className="grid grid-cols-7 gap-y-1 text-center">
        {cells.map((iso, i) => {
          if (!iso) return <div key={i} />;
          const off = iso < today || iso > max;
          const blk = !off && blocked(iso);
          const isIn = iso === ci, isOut = iso === co;
          const inside = ci && co && iso > ci && iso < co;
          let cls = 'h-10 flex items-center justify-center text-[15px] ';
          if (off) cls += 'text-gray-300';
          else if (blk) cls += 'text-gray-300 line-through';
          else if (isIn || isOut) cls += 'bg-sky-600 text-white font-semibold rounded-full';
          else if (inside) cls += 'bg-sky-100 text-sky-900';
          else cls += 'text-gray-900';
          return (
            <button key={iso} disabled={off || (blk && !(ci && !co))} onClick={() => tap(iso)} className={cls}>
              {Number(iso.slice(8))}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function GuestApp({ wa, startParam }) {
  const tgUser = wa?.initDataUnsafe?.user || {};
  const initLang = (() => {
    const q = new URLSearchParams(window.location.search).get('lang');
    const l = (q || tgUser.language_code || 'ru').slice(0, 2);
    return l === 'uz' ? 'uz' : l === 'en' ? 'en' : 'ru';
  })();
  const [lang, setLang] = useState(initLang);
  const t = T[lang];
  const [phase, setPhase] = useState('loading');   // loading | form | saving | done | noTg | error
  const [err, setErr] = useState('');
  const [catalog, setCatalog] = useState(null);
  const [rules, setRules] = useState(null);
  const [session, setSession] = useState(null);    // {draft, ref}
  const [ci, setCi] = useState(null);
  const [co, setCo] = useState(null);
  const [avail, setAvail] = useState(null);
  const [type, setType] = useState(() => new URLSearchParams(window.location.search).get('type'));
  const [availTick, setAvailTick] = useState(0);
  const [guests, setGuests] = useState(2);
  const [name, setName] = useState([tgUser.first_name, tgUser.last_name].filter(Boolean).join(' '));
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    (async () => {
      if (!wa?.initData) { setPhase('noTg'); return; }
      try { wa.setHeaderColor('#23333f'); wa.setBackgroundColor('#f4f7f8'); } catch { /* old clients */ }
      try {
        const [s, cat, rl] = await Promise.all([
          post('/guest/session', { init_data: wa.initData }),
          fetch('/api/v1/public/catalog').then((r) => r.json()),
          fetch('/api/v1/public/booking-rules').then((r) => r.json()),
        ]);
        setSession(s); setCatalog(cat); setRules(rl);
        const d = s.draft;
        if (d) {
          if (d.check_in && d.check_in >= rl.today) { setCi(d.check_in); if (d.check_out && d.check_out > d.check_in) setCo(d.check_out); }
          if (d.customer_name) setName(d.customer_name);
          if (d.phone) setPhone(d.phone);
          if (d.guests) setGuests(Math.min(10, Math.max(1, d.guests)));
        }
        setPhase('form');
      } catch (e) {
        setErr(e.message); setPhase('error');
      }
    })();
  }, [wa]);

  useEffect(() => {
    if (!ci || !co) { setAvail(null); return; }
    let cancelled = false;
    fetch(`/api/v1/public/availability?check_in=${ci}&check_out=${co}&guests=${guests}`)
      .then((r) => r.json()).then((j) => { if (!cancelled) setAvail(j); }).catch(() => {});
    return () => { cancelled = true; };
  }, [ci, co, guests, availTick]);

  const types = useMemo(() => {
    const list = (catalog?.types || []).filter((x) => x.units > 0);
    const byType = {};
    (avail?.available_types || []).forEach((a) => { byType[a.type] = a; });
    return list.map((x) => ({ ...x, avail: avail ? byType[x.type] || null : undefined }));
  }, [catalog, avail]);
  const chosen = types.find((x) => x.type === type);
  const total = chosen?.avail?.price_from_total || 0;
  const n = ci && co ? nightsOf(ci, co) : 0;

  async function sharePhone() {
    try { await post('/guest/expect-contact', { init_data: wa.initData }); } catch { /* ignore */ }
    wa.requestContact((ok, res) => {
      const p = res?.responseUnsafe?.contact?.phone_number;
      if (ok && p) setPhone(p.startsWith('+') ? p : '+' + p);
    });
  }

  async function book() {
    if (!ci || !co) return wa.showAlert(t.err_dates);
    if (!chosen || !chosen.avail) return wa.showAlert(t.err_type);
    if (name.trim().length < 2) return wa.showAlert(t.err_name);
    if (phone.replace(/\D/g, '').length < 9) return wa.showAlert(t.err_phone);
    // The invoice and voucher come from @balandda_bot — make sure it may write to this guest
    // (someone who opened the form from a @balandda_chimgan link may never have started it).
    if (wa.initDataUnsafe?.user && !wa.initDataUnsafe.user.allows_write_to_pm && wa.requestWriteAccess) {
      await new Promise((resolve) => { try { wa.requestWriteAccess(() => resolve()); } catch { resolve(); } });
    }
    setPhase('saving');
    try {
      const r = await post('/guest/book', {
        init_data: wa.initData, type: chosen.type, check_in: ci, check_out: co, guests,
        name: name.trim(), phone: phone.trim(), email: email.trim() || null, lang,
      });
      setResult(r); setPhase('done');
      try { wa.HapticFeedback?.notificationOccurred('success'); } catch { /* ignore */ }
    } catch (e) {
      setPhase('form');
      const d = e.data?.detail;
      const msg = d === 'unavailable' ? t.taken : d === 'name' ? t.err_name : d === 'phone' ? t.err_phone : (t[d] || t.fail);
      wa.showAlert(msg);
      if (d === 'unavailable') { setType(null); setAvailTick((k) => k + 1); }
    }
  }

  const shell = (body) => <div className="min-h-screen bg-[#f4f7f8] text-[#171d29] pb-28">{body}</div>;
  const card = 'bg-white rounded-2xl p-4 mx-3 mt-3 shadow-[0_1px_2px_rgba(0,0,0,.04)]';
  const input = 'w-full border border-gray-200 rounded-xl px-3 py-3 text-[16px] bg-white focus:outline-none focus:ring-2 focus:ring-sky-400';

  if (phase === 'loading') return shell(<div className="flex justify-center pt-28"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-600" /></div>);
  if (phase === 'noTg') return shell(<div className="pt-24 px-6 text-center text-gray-600">{t.open_tg}</div>);
  if (phase === 'error') return shell(<div className="pt-24 px-6 text-center text-gray-600">{t.fail}</div>);

  const header = (
    <div className="bg-[#23333f] text-white px-4 pt-4 pb-5">
      <div className="flex items-center justify-between">
        <img src="https://www.balandda.uz/assets/logo/balandda_logo_white.png" alt="Balandda" className="h-6" />
        <div className="flex gap-1">
          {['ru', 'uz', 'en'].map((l) => (
            <button key={l} onClick={() => setLang(l)} className={`px-2 py-0.5 rounded text-xs font-semibold ${lang === l ? 'bg-[#cadb44] text-[#122733]' : 'bg-white/10 text-white'}`}>{l.toUpperCase()}</button>
          ))}
        </div>
      </div>
      <div className="mt-4 text-xl font-bold">{phase === 'done' ? t.created : t.title}</div>
      <div className="text-sm text-white/70">{t.sub}</div>
    </div>
  );

  if (phase === 'done' && result) {
    return shell(
      <>
        {header}
        <div className={card}>
          <div className="text-green-600 font-semibold">✅ #{result.booking_id} · {result.unit_name}</div>
          <div className="mt-1 text-[15px]">{fmt(result.check_in, lang)} → {fmt(result.check_out, lang)} · {t.nights(result.nights)}</div>
          {result.total_amount ? <div className="mt-1 text-[15px]">{t.total}: <b>{money(result.total_amount)} {t.uzs}</b></div> : null}
          <div className="mt-3 text-sm text-gray-600">{t.hold}</div>
        </div>
        <div className="mx-3 mt-3 space-y-2">
          {result.pay_deposit_url && (
            <button onClick={() => wa.openLink(result.pay_deposit_url)} className="w-full py-3.5 rounded-xl bg-sky-600 text-white font-semibold">{t.pay_dep(money(result.deposit_amount))}</button>
          )}
          {result.pay_full_url && (
            <button onClick={() => wa.openLink(result.pay_full_url)} className="w-full py-3.5 rounded-xl bg-[#23333f] text-white font-semibold">{t.pay_full(money(result.full_amount))}</button>
          )}
          <button onClick={() => wa.close()} className="w-full py-3 rounded-xl text-sky-700 font-medium">{t.later}</button>
          <div className="text-center text-xs text-gray-500">{t.paid_note}<br />{t.reception}</div>
        </div>
      </>,
    );
  }

  return shell(
    <>
      {header}
      <div className={card}>
        <div className="flex items-baseline justify-between mb-3">
          <div className="font-semibold">{t.dates}</div>
          <div className="text-sm text-sky-700 font-medium">
            {ci && co ? `${fmt(ci, lang)} → ${fmt(co, lang)} · ${t.nights(n)}` : (ci ? t.pick_out : t.pick_in)}
          </div>
        </div>
        <RangeCalendar lang={lang} rules={rules} ci={ci} co={co} onChange={(a, b) => { setCi(a); setCo(b); }} />
      </div>

      <div className={card}>
        <div className="flex items-center justify-between">
          <div className="font-semibold">{t.guests}</div>
          <div className="flex items-center gap-3">
            <button onClick={() => setGuests((g) => Math.max(1, g - 1))} className="w-9 h-9 rounded-full bg-gray-100 text-lg">−</button>
            <div className="w-6 text-center font-semibold">{guests}</div>
            <button onClick={() => setGuests((g) => Math.min(12, g + 1))} className="w-9 h-9 rounded-full bg-gray-100 text-lg">+</button>
          </div>
        </div>
      </div>

      <div className="mx-3 mt-4 mb-1 font-semibold px-1">{t.stay}</div>
      {!ci || !co ? <div className="mx-4 text-sm text-gray-500">{t.choose_dates_first}</div> : null}
      {avail?.error ? <div className="mx-4 text-sm text-red-600">{t[avail.error] || t.err_dates}</div> : null}
      <div className="px-3 space-y-3 mt-2">
        {types.map((x) => {
          const off = x.avail === null;
          const sel = type === x.type;
          return (
            <button key={x.type} disabled={off || !ci || !co} onClick={() => setType(x.type)}
              className={`w-full text-left bg-white rounded-2xl overflow-hidden border-2 ${sel ? 'border-sky-500' : 'border-transparent'} ${off ? 'opacity-50' : ''}`}>
              <div className="flex">
                <img src={IMG + (PHOTO[x.type] || 'villa_1.jpg')} alt="" className="w-28 h-28 object-cover flex-none" loading="lazy" />
                <div className="p-3 flex-1 min-w-0">
                  <div className="font-semibold leading-tight">{(x.labels && x.labels[lang]) || x.label}</div>
                  <div className="text-xs text-gray-500 mt-1">{t.upto(x.capacity_max)}</div>
                  <div className="mt-2 text-[15px]">
                    {x.avail ? <><b>{money(x.avail.price_from_total)} {t.uzs}</b> <span className="text-xs text-gray-500">{t.for_stay}</span></>
                      : x.avail === null ? <span className="text-sm text-gray-500">{t.none}</span>
                        : <span className="text-sm text-gray-500">{t.from} {money(x.price_from?.weekday)} {t.uzs}</span>}
                  </div>
                </div>
                {sel ? <div className="pr-3 pt-3 text-sky-600 text-xl">✓</div> : null}
              </div>
            </button>
          );
        })}
      </div>

      <div className={card + ' space-y-3'}>
        <div className="font-semibold">{t.contact}</div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t.name} className={input} />
        <div className="flex gap-2">
          <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t.phone + ' +998…'} className={input} />
        </div>
        {wa?.requestContact ? <button onClick={sharePhone} className="w-full py-2.5 rounded-xl bg-sky-50 text-sky-700 font-medium text-sm">{t.share}</button> : null}
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t.email} className={input} />
        <div className="text-[11px] text-gray-400">{t.agree}</div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-white/95 border-t border-gray-200 px-4 py-3">
        <button onClick={book} disabled={phase === 'saving'} className="w-full py-3.5 rounded-xl bg-sky-600 text-white font-semibold text-[16px] disabled:opacity-50">
          {phase === 'saving' ? '…' : `${t.book}${total ? ` · ${money(total)} ${t.uzs}` : ''}`}
        </button>
      </div>
    </>,
  );
}
