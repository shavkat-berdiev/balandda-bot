import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { api } from '../api';

const TYPE_LABELS = { internal: 'Внутренний', external: 'Внешний' };

function iso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function fmt(n) { return Number(n || 0).toLocaleString('ru-RU'); }

const PRESETS = [
  { key: 'today', label: 'Сегодня', days: 0 },
  { key: 'week', label: '7 дней', days: 6 },
  { key: 'month', label: '30 дней', days: 29 },
];

export default function SpaCommissions() {
  const today = new Date();
  const [from, setFrom] = useState(iso(new Date(today.getTime() - 29 * 864e5)));
  const [to, setTo] = useState(iso(today));
  const [preset, setPreset] = useState('month');
  const [data, setData] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [details, setDetails] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api.getSpaCommissionsSummary(from, to)); setError(''); }
    catch (err) { setError(err.message); }
    setLoading(false);
  }, [from, to]);

  useEffect(() => { load(); setOpenId(null); setDetails({}); }, [load]);

  function applyPreset(p) {
    setPreset(p.key);
    const now = new Date();
    setFrom(iso(new Date(now.getTime() - p.days * 864e5)));
    setTo(iso(now));
  }

  async function toggleDetails(masterId) {
    if (openId === masterId) { setOpenId(null); return; }
    setOpenId(masterId);
    if (!details[masterId]) {
      try {
        const d = await api.getSpaCommissionsDetails(masterId, from, to);
        setDetails(prev => ({ ...prev, [masterId]: d }));
      } catch (err) { setError(err.message); }
    }
  }

  const totals = data?.totals;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Комиссии SPA</h1>
          <p className="text-gray-500 text-sm mt-1">Заработок мастеров · выплаты делаются в @balandda_spa_bot</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.map(p => (
            <button key={p.key} onClick={() => applyPreset(p)}
              className={`px-3 py-2 rounded-lg text-sm border ${preset === p.key ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'}`}>
              {p.label}
            </button>
          ))}
          <input type="date" value={from} onChange={e => { setFrom(e.target.value); setPreset(''); }}
            className="px-2 py-2 border border-gray-200 rounded-lg text-sm" />
          <span className="text-gray-400 text-sm">—</span>
          <input type="date" value={to} onChange={e => { setTo(e.target.value); setPreset(''); }}
            className="px-2 py-2 border border-gray-200 rounded-lg text-sm" />
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {totals && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
          <StatCard label="Услуг выполнено" value={totals.services_done} />
          <StatCard label="Выручка SPA (по записям)" value={`${fmt(totals.revenue)} UZS`} />
          <StatCard label="Начислено комиссий" value={`${fmt(totals.earned)} UZS`} />
          <StatCard label={`Бонус админа (${data.admin_bonus?.percent ?? 0}%)`} value={`${fmt(data.admin_bonus?.bonus)} UZS`} />
          <StatCard label="К выплате (всего)" value={`${fmt(totals.balance)} UZS`} highlight />
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : data && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Мастер</th>
                  <th className="px-4 py-3 text-left">Тип</th>
                  <th className="px-4 py-3 text-center">Услуг</th>
                  <th className="px-4 py-3 text-right">Выручка</th>
                  <th className="px-4 py-3 text-right">Начислено</th>
                  <th className="px-4 py-3 text-right">Выплачено (период)</th>
                  <th className="px-4 py-3 text-right">К выплате (всего)</th>
                  <th className="px-4 py-3 text-center"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.masters.map(m => (
                  <>
                    <tr key={m.master_id} onClick={() => toggleDetails(m.master_id)}
                      className={`cursor-pointer hover:bg-gray-50 ${!m.is_active ? 'opacity-50' : ''}`}>
                      <td className="px-4 py-3 font-medium text-gray-800">{m.name}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${m.master_type === 'external' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'}`}>
                          {TYPE_LABELS[m.master_type] || m.master_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center text-gray-600">{m.services_done}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-600">{fmt(m.revenue)}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-800">{fmt(m.earned)}</td>
                      <td className="px-4 py-3 text-right font-mono text-gray-600">{fmt(m.paid_in_period)}</td>
                      <td className={`px-4 py-3 text-right font-mono font-semibold ${m.balance > 0 ? 'text-amber-600' : 'text-gray-400'}`}>{fmt(m.balance)}</td>
                      <td className="px-4 py-3 text-center text-gray-400">
                        {openId === m.master_id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </td>
                    </tr>
                    {openId === m.master_id && (
                      <tr key={`${m.master_id}-details`}>
                        <td colSpan={8} className="bg-gray-50/70 px-6 py-4">
                          <MasterDetails d={details[m.master_id]} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, highlight }) {
  return (
    <div className={`rounded-xl border p-4 ${highlight ? 'bg-amber-50 border-amber-200' : 'bg-white border-gray-200'}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold mt-1 ${highlight ? 'text-amber-700' : 'text-gray-800'}`}>{value}</p>
    </div>
  );
}

function MasterDetails({ d }) {
  if (!d) return <p className="text-sm text-gray-400">Загрузка…</p>;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Выполненные услуги за период</p>
        {d.records.length === 0 ? <p className="text-sm text-gray-400">Нет выполненных услуг.</p> : (
          <table className="w-full text-xs">
            <thead className="text-gray-500">
              <tr><th className="text-left py-1">Дата</th><th className="text-left py-1">Услуга</th><th className="text-left py-1">Клиент</th><th className="text-right py-1">Цена</th><th className="text-right py-1">Комиссия</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {d.records.map(r => (
                <tr key={r.id}>
                  <td className="py-1.5 text-gray-600">{r.date}</td>
                  <td className="py-1.5 text-gray-800">{r.service}</td>
                  <td className="py-1.5 text-gray-600">{r.customer || '—'}</td>
                  <td className="py-1.5 text-right font-mono">{fmt(r.price)}</td>
                  <td className="py-1.5 text-right font-mono font-medium">{fmt(r.commission)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Выплаты за период</p>
        {d.payouts.length === 0 ? <p className="text-sm text-gray-400">Выплат не было.</p> : (
          <table className="w-full text-xs">
            <thead className="text-gray-500">
              <tr><th className="text-left py-1">Дата</th><th className="text-right py-1">Сумма</th><th className="text-left py-1 pl-3">Заметка</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {d.payouts.map(p => (
                <tr key={p.id}>
                  <td className="py-1.5 text-gray-600">{p.date}</td>
                  <td className="py-1.5 text-right font-mono">{fmt(p.amount)}</td>
                  <td className="py-1.5 pl-3 text-gray-500">{p.note || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-sm mt-3">Остаток к выплате: <span className="font-semibold text-amber-600">{fmt(d.balance)} UZS</span></p>
      </div>
    </div>
  );
}
