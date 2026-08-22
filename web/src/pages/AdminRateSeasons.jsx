import { Fragment, useState, useEffect, useMemo } from 'react';
import { Check, Trash2, Plus, Upload, Wand2, CalendarDays, PartyPopper } from 'lucide-react';
import { api } from '../api';

/**
 * Seasonal rates — the one place nightly prices are set.
 *
 * The base price on «Объекты» is the high-season rate. A season overrides it
 * for the dates it covers, and one season can hold several date ranges (autumn
 * + spring priced once). Holidays flip a night to the Saturday rate. Everything
 * saved here reaches the site, both bots, the operator calendar and every OTA
 * (Booking.com / Ostrovok / Airbnb / Google) through Beds24.
 */

const money = (v) => (Number(v) || 0).toLocaleString('ru-RU');
const fmtDate = (s) => (s ? new Date(s + 'T12:00:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }) : '');
const todayStr = () => new Date().toISOString().slice(0, 10);

export default function AdminRateSeasons() {
  const [seasons, setSeasons] = useState([]);
  const [properties, setProperties] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [selectedId, setSelectedId] = useState(null);
  const [grid, setGrid] = useState({});         // property_id -> {weekday, weekend}
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);

  const [newSeason, setNewSeason] = useState({ name: '', date_from: '', date_to: '', priority: 0 });
  const [newPeriod, setNewPeriod] = useState({ date_from: '', date_to: '', label: '' });
  const [newHoliday, setNewHoliday] = useState({ date: '', name: '' });

  const [preview, setPreview] = useState(null);
  const [previewUnit, setPreviewUnit] = useState('');
  const [previewMonth, setPreviewMonth] = useState(todayStr().slice(0, 7));

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [s, props, hol] = await Promise.all([
        api.getRateSeasons(), api.getAdminProperties(), api.getHolidays(),
      ]);
      setSeasons(s);
      setProperties(props.filter((p) => p.is_active && p.business_unit === 'RESORT'));
      setHolidays(hol);
      const keep = s.find((x) => x.id === selectedId) || s[0];
      if (keep) selectSeason(keep);
      else setSelectedId(null);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  function selectSeason(s) {
    setSelectedId(s.id);
    const g = {};
    s.prices.forEach((p) => { g[p.property_id] = { weekday: p.price_weekday, weekend: p.price_weekend }; });
    setGrid(g);
  }

  const season = useMemo(() => seasons.find((s) => s.id === selectedId) || null, [seasons, selectedId]);

  // Units grouped by type so the grid reads like the price list.
  const grouped = useMemo(() => {
    const by = {};
    properties.forEach((p) => { (by[p.property_type] ||= []).push(p); });
    return Object.entries(by);
  }, [properties]);

  const dirty = useMemo(() => {
    if (!season) return false;
    const orig = {};
    season.prices.forEach((p) => { orig[p.property_id] = `${p.price_weekday}/${p.price_weekend}`; });
    const now = {};
    Object.entries(grid).forEach(([k, v]) => { now[k] = `${Number(v.weekday) || 0}/${Number(v.weekend) || 0}`; });
    return JSON.stringify(orig) !== JSON.stringify(now);
  }, [season, grid]);

  function setCell(pid, band, value) {
    setGrid((g) => ({ ...g, [pid]: { ...(g[pid] || { weekday: 0, weekend: 0 }), [band]: value } }));
  }

  /** Prefill every unit from its base rate. delta is added (pass a negative). */
  function prefill(delta, applyWeekend) {
    const g = {};
    properties.forEach((p) => {
      const wd = Math.max(0, Math.round(Number(p.price_weekday || 0) + delta));
      const we = applyWeekend
        ? Math.max(0, Math.round(Number(p.price_weekend || 0) + delta))
        : Math.round(Number(p.price_weekend || 0));
      g[p.id] = { weekday: wd, weekend: we };
    });
    setGrid(g);
  }

  function copyBase() {
    const g = {};
    properties.forEach((p) => {
      g[p.id] = { weekday: Math.round(Number(p.price_weekday || 0)), weekend: Math.round(Number(p.price_weekend || 0)) };
    });
    setGrid(g);
  }

  /** Apply the first filled unit of a type to every other unit of that type. */
  function fillTypeDown(type) {
    const units = properties.filter((p) => p.property_type === type);
    const src = units.map((u) => grid[u.id]).find((v) => v && (Number(v.weekday) || Number(v.weekend)));
    if (!src) return;
    setGrid((g) => {
      const next = { ...g };
      units.forEach((u) => { next[u.id] = { weekday: src.weekday, weekend: src.weekend }; });
      return next;
    });
  }

  async function saveGrid() {
    if (!season) return;
    setSaving(true);
    setError('');
    try {
      const rows = Object.entries(grid)
        .filter(([, v]) => Number(v.weekday) > 0 || Number(v.weekend) > 0)
        .map(([pid, v]) => ({
          property_id: Number(pid),
          price_weekday: Number(v.weekday) || 0,
          price_weekend: Number(v.weekend) || 0,
        }));
      await api.setSeasonPrices(season.id, rows);
      setNotice('Цены сохранены. Нажмите «Опубликовать», чтобы разослать их сразу.');
      await load();
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  async function addSeason() {
    if (!newSeason.name.trim()) { setError('Укажите название сезона'); return; }
    setError('');
    try {
      const periods = newSeason.date_from
        ? [{ date_from: newSeason.date_from, date_to: newSeason.date_to || newSeason.date_from, label: null }]
        : [];
      const created = await api.createRateSeason({
        name: newSeason.name.trim(),
        priority: Number(newSeason.priority) || 0,
        is_active: true,
        periods,
        prefill_mode: 'delta',
        prefill_amount: 0,          // start from the base rate; edit the grid after
        prefill_apply_weekend: false,
      });
      setNewSeason({ name: '', date_from: '', date_to: '', priority: 0 });
      setSelectedId(created.id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleSeason(s) {
    try { await api.updateRateSeason(s.id, { is_active: !s.is_active }); await load(); }
    catch (err) { setError(err.message); }
  }

  async function removeSeason(s) {
    if (!window.confirm(`Удалить сезон «${s.name}»? Даты вернутся к базовым ценам.`)) return;
    try { await api.deleteRateSeason(s.id); setSelectedId(null); await load(); }
    catch (err) { setError(err.message); }
  }

  async function addPeriod() {
    if (!season || !newPeriod.date_from) { setError('Укажите дату начала'); return; }
    setError('');
    try {
      await api.addSeasonPeriod(season.id, {
        date_from: newPeriod.date_from,
        date_to: newPeriod.date_to || newPeriod.date_from,
        label: newPeriod.label || null,
      });
      setNewPeriod({ date_from: '', date_to: '', label: '' });
      await load();
    } catch (err) { setError(err.message); }
  }

  async function removePeriod(pid) {
    try { await api.deleteSeasonPeriod(pid); await load(); }
    catch (err) { setError(err.message); }
  }

  async function addHoliday() {
    if (!newHoliday.date) { setError('Укажите дату'); return; }
    setError('');
    try {
      await api.createHoliday({ date: newHoliday.date, name: newHoliday.name || null, is_active: true });
      setNewHoliday({ date: '', name: '' });
      await load();
    } catch (err) { setError(err.message); }
  }

  async function loadPreset(year) {
    try { const r = await api.presetHolidays(year); setNotice(`Добавлено праздников: ${r.added}`); await load(); }
    catch (err) { setError(err.message); }
  }

  async function publish() {
    setPublishing(true);
    setError('');
    try {
      const r = await api.publishRates();
      setNotice(`Отправлено: OTA ${r.beds24 ? '✓' : '—'}, кэш сайта ${r.site_cache_purged ? '✓' : '—'}. Боты подхватят в течение 5 минут.`);
    } catch (err) { setError(err.message); }
    setPublishing(false);
  }

  async function freeze() {
    if (!window.confirm('Зафиксировать текущую сумму у будущих броней без суммы? Это защитит их от пересчёта по новым ценам.')) return;
    try { const r = await api.freezeTotals(); setNotice(`Зафиксировано броней: ${r.updated}`); }
    catch (err) { setError(err.message); }
  }

  async function runPreview() {
    setError('');
    try {
      const from = `${previewMonth}-01`;
      const d = new Date(`${previewMonth}-01T12:00:00`);
      const to = new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
      const params = { date_from: from, date_to: to };
      if (previewUnit) params.property_id = previewUnit;
      const r = await api.getRatePreview(params);
      setPreview(r);
    } catch (err) { setError(err.message); }
  }

  if (loading) {
    return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Цены и сезоны</h1>
        <p className="text-gray-500 text-sm mt-1">
          Цена на вкладке «Объекты» — базовая (высокий сезон). Сезон переопределяет её на свои даты.
          Один сезон может иметь несколько периодов — осень и весна редактируются один раз.
          Суббота <b>и праздники</b> считаются по колонке «Суббота». Всё сохранённое здесь уходит на сайт,
          в Telegram и Instagram, в календарь и на Booking.com / Ostrovok / Airbnb / Google.
        </p>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}
      {notice && <div className="bg-green-50 text-green-700 rounded-lg px-4 py-3 text-sm mb-4">{notice}</div>}

      <div className="space-y-6">
        {/* ── Seasons ─────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-4 flex items-center gap-2"><CalendarDays size={17} /> Сезоны</h2>

          <div className="space-y-2 mb-5">
            {seasons.length === 0 && <div className="text-sm text-gray-400">Сезонов пока нет — действуют базовые цены.</div>}
            {seasons.map((s) => (
              <div key={s.id}
                className={`rounded-lg border px-4 py-3 cursor-pointer ${s.id === selectedId ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`}
                onClick={() => selectSeason(s)}>
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-gray-800">{s.name}</span>
                    {!s.is_active && <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded">выключен</span>}
                    {s.priority > 0 && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">приоритет {s.priority}</span>}
                    {s.periods.map((p) => (
                      <span key={p.id} className="text-xs bg-white border border-gray-200 text-gray-600 px-2 py-0.5 rounded">
                        {p.label ? `${p.label} · ` : ''}{fmtDate(p.date_from)} – {fmtDate(p.date_to)} · {p.nights} н.
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={(e) => { e.stopPropagation(); toggleSeason(s); }}
                      className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50">
                      {s.is_active ? 'Выключить' : 'Включить'}
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); removeSeason(s); }}
                      className="text-gray-400 hover:text-red-600"><Trash2 size={15} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-gray-100 pt-4">
            <div className="text-sm text-gray-600 mb-2">
              Новый сезон — например «Новый год»: укажите даты, приоритет выше 0, и задайте цены в таблице ниже.
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Название</label>
                <input value={newSeason.name} placeholder="Новый год"
                  onChange={(e) => setNewSeason({ ...newSeason, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">С даты (первая ночь)</label>
                <input type="date" value={newSeason.date_from}
                  onChange={(e) => setNewSeason({ ...newSeason, date_from: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">По дату (последняя ночь)</label>
                <input type="date" value={newSeason.date_to} min={newSeason.date_from}
                  onChange={(e) => setNewSeason({ ...newSeason, date_to: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Приоритет</label>
                <input type="number" value={newSeason.priority}
                  onChange={(e) => setNewSeason({ ...newSeason, priority: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div className="flex items-end">
                <button onClick={addSeason}
                  className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">
                  <Plus size={15} /> Добавить сезон
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              При пересечении побеждает сезон с большим приоритетом — поэтому «Новый год» с приоритетом 100
              перекроет низкий сезон на своих датах.
            </p>
          </div>
        </div>

        {/* ── Price grid ──────────────────────────────────────── */}
        {season && (
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
              <div>
                <h2 className="font-semibold text-gray-800">Цены сезона «{season.name}»</h2>
                <p className="text-sm text-gray-500 mt-1">
                  Пустая строка = объект не участвует в сезоне и продаётся по базовой цене.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button onClick={() => prefill(-500000, false)}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-xs border border-gray-200 text-gray-700 hover:bg-gray-50">
                  <Wand2 size={14} /> Будни −500 000
                </button>
                <button onClick={copyBase}
                  className="px-3 py-2 rounded-lg text-xs border border-gray-200 text-gray-700 hover:bg-gray-50">
                  = базовым
                </button>
                <button onClick={() => setGrid({})}
                  className="px-3 py-2 rounded-lg text-xs border border-gray-200 text-gray-700 hover:bg-gray-50">
                  Очистить
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="py-2 pr-3 font-medium">Объект</th>
                    <th className="py-2 px-3 font-medium text-right">Базовые будни</th>
                    <th className="py-2 px-3 font-medium">Будни (сезон)</th>
                    <th className="py-2 px-3 font-medium text-right">Δ</th>
                    <th className="py-2 px-3 font-medium text-right">Базовая Сб</th>
                    <th className="py-2 px-3 font-medium">Суббота и праздники</th>
                    <th className="py-2 px-3 font-medium text-right">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {grouped.map(([type, units]) => (
                    <Fragment key={type}>
                      <tr className="bg-gray-50">
                        <td colSpan={7} className="py-2 px-3 text-xs font-semibold text-gray-600">
                          {units[0]?.property_type_label || type}
                          <button onClick={() => fillTypeDown(type)}
                            className="ml-3 text-xs font-normal text-blue-600 hover:underline">
                            применить ко всем в типе
                          </button>
                        </td>
                      </tr>
                      {units.map((p) => {
                        const cur = grid[p.id] || { weekday: '', weekend: '' };
                        const dWd = Number(cur.weekday) ? Number(cur.weekday) - Number(p.price_weekday || 0) : null;
                        const dWe = Number(cur.weekend) ? Number(cur.weekend) - Number(p.price_weekend || 0) : null;
                        return (
                          <tr key={p.id} className="border-b border-gray-50">
                            <td className="py-2 pr-3 text-gray-800">{p.emoji} {p.name_ru}</td>
                            <td className="py-2 px-3 text-right text-gray-400">{money(p.price_weekday)}</td>
                            <td className="py-2 px-3">
                              <input type="number" step="50000" value={cur.weekday}
                                onChange={(e) => setCell(p.id, 'weekday', e.target.value)}
                                className="w-32 px-2 py-1 border border-gray-200 rounded text-sm text-right" />
                            </td>
                            <td className={`py-2 px-3 text-right text-xs ${dWd < 0 ? 'text-green-600' : dWd > 0 ? 'text-amber-600' : 'text-gray-300'}`}>
                              {dWd === null ? '—' : `${dWd > 0 ? '+' : ''}${money(dWd)}`}
                            </td>
                            <td className="py-2 px-3 text-right text-gray-400">{money(p.price_weekend)}</td>
                            <td className="py-2 px-3">
                              <input type="number" step="50000" value={cur.weekend}
                                onChange={(e) => setCell(p.id, 'weekend', e.target.value)}
                                className="w-32 px-2 py-1 border border-gray-200 rounded text-sm text-right" />
                            </td>
                            <td className={`py-2 px-3 text-right text-xs ${dWe < 0 ? 'text-green-600' : dWe > 0 ? 'text-amber-600' : 'text-gray-300'}`}>
                              {dWe === null ? '—' : `${dWe > 0 ? '+' : ''}${money(dWe)}`}
                            </td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center gap-3 mt-4 flex-wrap">
              <button onClick={saveGrid} disabled={saving || !dirty}
                className={`inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium ${dirty ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-gray-100 text-gray-400'}`}>
                <Check size={15} /> {saving ? '…' : 'Сохранить цены'}
              </button>
              <button onClick={publish} disabled={publishing}
                className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-gray-800 text-white hover:bg-gray-900">
                <Upload size={15} /> {publishing ? '…' : 'Опубликовать везде'}
              </button>
              <button onClick={freeze}
                className="px-4 py-2 rounded-lg text-sm border border-gray-200 text-gray-700 hover:bg-gray-50">
                Зафиксировать суммы будущих броней
              </button>
            </div>
          </div>
        )}

        {/* ── Extra periods for the selected season ───────────── */}
        {season && (
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-800 mb-1">Периоды сезона «{season.name}»</h2>
            <p className="text-sm text-gray-500 mb-4">
              Добавьте столько диапазонов, сколько нужно — цены у них общие.
            </p>
            <div className="space-y-2 mb-4">
              {season.periods.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 border border-gray-100 rounded-lg px-3 py-2">
                  <span className="text-sm text-gray-700">
                    {p.label ? <b>{p.label}</b> : null} {fmtDate(p.date_from)} – {fmtDate(p.date_to)}
                    <span className="text-gray-400"> · {p.nights} ночей</span>
                  </span>
                  <button onClick={() => removePeriod(p.id)} className="text-gray-400 hover:text-red-600"><Trash2 size={15} /></button>
                </div>
              ))}
              {season.periods.length === 0 && <div className="text-sm text-gray-400">Периодов нет — сезон ни на что не влияет.</div>}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">С даты</label>
                <input type="date" value={newPeriod.date_from}
                  onChange={(e) => setNewPeriod({ ...newPeriod, date_from: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">По дату</label>
                <input type="date" value={newPeriod.date_to} min={newPeriod.date_from}
                  onChange={(e) => setNewPeriod({ ...newPeriod, date_to: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Подпись</label>
                <input value={newPeriod.label} placeholder="Весна 2027"
                  onChange={(e) => setNewPeriod({ ...newPeriod, label: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
              </div>
              <div className="flex items-end">
                <button onClick={addPeriod}
                  className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">
                  <Plus size={15} /> Добавить период
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Holidays ────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-1 flex items-center gap-2"><PartyPopper size={17} /> Праздники</h2>
          <p className="text-sm text-gray-500 mb-4">
            В эти дни действует цена колонки «Суббота» — и в базовых ценах, и внутри сезона.
            Рамазон и Курбан хайит переносятся каждый год, их добавляйте вручную.
          </p>
          <div className="flex flex-wrap gap-2 mb-4">
            {holidays.map((h) => (
              <span key={h.id} className="inline-flex items-center gap-2 text-xs border border-gray-200 rounded-lg px-2 py-1">
                <b>{fmtDate(h.date)}</b>
                <span className="text-gray-500">{h.name}</span>
                <button onClick={() => api.deleteHoliday(h.id).then(load).catch((e) => setError(e.message))}
                  className="text-gray-400 hover:text-red-600"><Trash2 size={13} /></button>
              </span>
            ))}
            {holidays.length === 0 && <span className="text-sm text-gray-400">Праздников нет.</span>}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Дата</label>
              <input type="date" value={newHoliday.date}
                onChange={(e) => setNewHoliday({ ...newHoliday, date: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Название</label>
              <input value={newHoliday.name} placeholder="Курбан хайит"
                onChange={(e) => setNewHoliday({ ...newHoliday, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div className="flex items-end">
              <button onClick={addHoliday}
                className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">
                <Plus size={15} /> Добавить
              </button>
            </div>
            <div className="flex items-end gap-2">
              <button onClick={() => loadPreset(2026)} className="px-3 py-2 rounded-lg text-xs border border-gray-200 text-gray-700 hover:bg-gray-50">Праздники 2026</button>
              <button onClick={() => loadPreset(2027)} className="px-3 py-2 rounded-lg text-xs border border-gray-200 text-gray-700 hover:bg-gray-50">2027</button>
            </div>
          </div>
        </div>

        {/* ── Preview ─────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-1">Проверка</h2>
          <p className="text-sm text-gray-500 mb-4">
            Что именно заплатит гость за каждую ночь. Смотрите здесь перед публикацией.
          </p>
          <div className="flex items-end gap-3 flex-wrap mb-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Объект</label>
              <select value={previewUnit} onChange={(e) => setPreviewUnit(e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                <option value="">Все объекты</option>
                {properties.map((p) => <option key={p.id} value={p.id}>{p.emoji} {p.name_ru}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Месяц</label>
              <input type="month" value={previewMonth} onChange={(e) => setPreviewMonth(e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <button onClick={runPreview}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">Показать</button>
          </div>

          {preview && (
            <div className="space-y-4">
              {preview.units.map((u) => (
                <div key={u.property_id}>
                  <div className="text-sm font-medium text-gray-700 mb-2">{u.name}</div>
                  <div className="flex flex-wrap gap-1">
                    {u.nights.map((n) => (
                      <div key={n.date}
                        title={`${n.date}${n.season ? ' · ' + n.season : ''}${n.holiday ? ' · ' + n.holiday : ''}${n.blocked ? ' · закрыто' : ''}`}
                        className={`w-20 rounded px-1 py-1 text-center border ${
                          n.blocked ? 'bg-red-50 border-red-200 text-red-400 line-through'
                          : n.holiday ? 'bg-amber-50 border-amber-200 text-amber-800'
                          : n.season ? 'bg-blue-50 border-blue-200 text-blue-800'
                          : 'bg-gray-50 border-gray-200 text-gray-600'}`}>
                        <div className="text-[10px] opacity-70">{n.date.slice(8)} {['вс','пн','вт','ср','чт','пт','сб'][new Date(n.date + 'T12:00:00').getDay()]}</div>
                        <div className="text-[11px] font-medium">{money(n.price)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <div className="flex gap-4 text-xs text-gray-500 pt-2">
                <span><span className="inline-block w-3 h-3 rounded bg-gray-100 border border-gray-200 mr-1 align-middle" /> базовая</span>
                <span><span className="inline-block w-3 h-3 rounded bg-blue-100 border border-blue-200 mr-1 align-middle" /> сезон</span>
                <span><span className="inline-block w-3 h-3 rounded bg-amber-100 border border-amber-200 mr-1 align-middle" /> праздник</span>
                <span><span className="inline-block w-3 h-3 rounded bg-red-100 border border-red-200 mr-1 align-middle" /> закрыто</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
