import { useState, useEffect, useCallback } from 'react';
import { MessageSquare, Send, Phone, Globe, Bot } from 'lucide-react';
import { api } from '../api';

const CH_LABEL = { website: 'Сайт', phone: 'Телефон', telegram: 'Telegram', instagram: 'Instagram' };
const ST_LABEL = {
  new: 'Новая', in_progress: 'В работе', booked: 'Бронь', declined: 'Отказ',
  no_answer: 'Не дозвон', waiting: 'Ждёт ответа', answered: 'Отвечено',
};

function isoDaysAgo(n) {
  const d = new Date(); d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
function fmtTime(s) {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d) ? '—' : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function Stats() {
  const [tab, setTab] = useState('requests');
  const [from, setFrom] = useState(isoDaysAgo(30));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [ov, setOv] = useState(null);
  const [bot, setBot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [o, b] = await Promise.all([
        api.getStatsOverview(from, to),
        api.getStatsBot(from, to).catch(() => null),
      ]);
      setOv(o); setBot(b);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }, [from, to]);

  useEffect(() => { load(); }, [load]);

  const channels = ov?.stats?.channels || {};
  const bySrc = ov?.stats?.leadsBySource || {};

  const rows = [];
  for (const l of (ov?.leads || [])) {
    rows.push({ kind: 'Заявка', ch: l.source, name: l.name || '—', status: l.status,
      info: [l.phone, l.cottage].filter(Boolean).join(' · '), time: l.createdAt });
  }
  for (const c of (ov?.conversations || [])) {
    rows.push({ kind: 'Сообщение', ch: c.channel, name: c.name || (c.username ? '@' + c.username : '—'),
      status: c.status, info: c.preview || '', time: c.waitingSince || c.lastReplyAt || c.createdAt });
  }
  rows.sort((a, b) => String(b.time).localeCompare(String(a.time)));

  const card = 'bg-white border border-gray-200 rounded-xl p-4';
  const CH_ICON = { website: Globe, phone: Phone, telegram: Send, instagram: MessageSquare };

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Статистика</h1>
          <p className="text-gray-500 text-sm mt-1">Запросы по каналам и активность бота — данные из CRM</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="date" value={from} onChange={e => setFrom(e.target.value)} className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          <span className="text-gray-400">—</span>
          <input type="date" value={to} onChange={e => setTo(e.target.value)} className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
        </div>
      </div>

      <div className="flex gap-2 mb-5">
        <button onClick={() => setTab('requests')} className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === 'requests' ? 'bg-blue-600 text-white' : 'bg-white border border-gray-200 text-gray-600'}`}>Запросы</button>
        <button onClick={() => setTab('bot')} className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === 'bot' ? 'bg-blue-600 text-white' : 'bg-white border border-gray-200 text-gray-600'}`}>Бот</button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">⚠ {error}</div>}
      {loading && <p className="text-sm text-gray-400 mb-4">Загрузка…</p>}

      {tab === 'requests' && ov && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            {['telegram', 'instagram'].map(k => {
              const s = channels[k] || { conversations: 0, waiting: 0, avgResponseMin: null };
              const Icon = CH_ICON[k];
              return (
                <div key={k} className={card}>
                  <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500"><Icon size={14} /> {CH_LABEL[k]}</div>
                  <div className="text-2xl font-bold text-gray-800 mt-1">{s.conversations}</div>
                  <div className="text-xs text-gray-500">диалогов · <b>{s.waiting}</b> ждут{s.avgResponseMin != null ? ` · ⏱ ${s.avgResponseMin} мин` : ''}</div>
                </div>
              );
            })}
            <div className={card}>
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500"><Globe size={14} /> Сайт</div>
              <div className="text-2xl font-bold text-gray-800 mt-1">{bySrc.website || 0}</div>
              <div className="text-xs text-gray-500">заявок</div>
            </div>
            <div className={card}>
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-gray-500"><Phone size={14} /> Телефон</div>
              <div className="text-2xl font-bold text-gray-800 mt-1">{bySrc.phone || 0}</div>
              <div className="text-xs text-gray-500">заявок</div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left">Тип</th>
                    <th className="px-4 py-3 text-left">Канал</th>
                    <th className="px-4 py-3 text-left">Имя</th>
                    <th className="px-4 py-3 text-left">Инфо</th>
                    <th className="px-4 py-3 text-left">Статус</th>
                    <th className="px-4 py-3 text-left">Время</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.slice(0, 300).map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 text-gray-500">{r.kind}</td>
                      <td className="px-4 py-2.5">{CH_LABEL[r.ch] || r.ch}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{r.name}</td>
                      <td className="px-4 py-2.5 text-gray-600 max-w-xs truncate">{r.info}</td>
                      <td className="px-4 py-2.5"><span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700">{ST_LABEL[r.status] || r.status}</span></td>
                      <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{fmtTime(r.time)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {tab === 'bot' && (
        !bot ? <p className="text-sm text-gray-400">Нет данных по боту за этот период.</p> : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <div className={card}><div className="text-xs uppercase tracking-wide text-gray-500 flex items-center gap-2"><Bot size={14} /> Пользователей</div><div className="text-2xl font-bold text-gray-800 mt-1">{bot.uniqueUsers}</div></div>
              <div className={card}><div className="text-xs uppercase tracking-wide text-gray-500">Дошли до запроса</div><div className="text-2xl font-bold text-gray-800 mt-1">{bot.funnel?.requested ?? 0}</div></div>
              <div className={card}><div className="text-xs uppercase tracking-wide text-gray-500">Отправили заявку</div><div className="text-2xl font-bold text-gray-800 mt-1">{bot.funnel?.submitted ?? 0}</div></div>
              <div className={card}><div className="text-xs uppercase tracking-wide text-gray-500">Конверсия</div><div className="text-2xl font-bold text-gray-800 mt-1">{bot.conversion}%</div></div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className={card}>
                <h3 className="font-semibold text-gray-800 mb-3">Воронка</h3>
                {[['Запустили бот', bot.funnel?.reached], ['Смотрели контент', bot.funnel?.browsed], ['Начали заявку', bot.funnel?.requested], ['Отправили заявку', bot.funnel?.submitted]].map(([lbl, n]) => {
                  const base = bot.funnel?.reached || 1;
                  const pct = Math.round(((n || 0) / base) * 100);
                  return (
                    <div key={lbl} className="mb-2">
                      <div className="flex justify-between text-xs text-gray-600 mb-1"><span>{lbl}</span><span>{n || 0} · {pct}%</span></div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden"><div className="h-full bg-blue-500" style={{ width: `${pct}%` }} /></div>
                    </div>
                  );
                })}
              </div>

              <div className={card}>
                <h3 className="font-semibold text-gray-800 mb-3">Языки</h3>
                {(bot.byLang || []).map(l => (
                  <div key={l.lang} className="flex justify-between text-sm py-1 border-b border-gray-50">
                    <span className="text-gray-700">{l.lang}</span><span className="font-medium">{l.users}</span>
                  </div>
                ))}
                <h3 className="font-semibold text-gray-800 mt-4 mb-2">Популярный контент</h3>
                {(bot.topContent || []).map(c => (
                  <div key={c.key} className="flex justify-between text-sm py-1 border-b border-gray-50">
                    <span className="text-gray-700">{c.key}</span><span className="font-medium">{c.views}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )
      )}
    </div>
  );
}
