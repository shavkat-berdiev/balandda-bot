import { useState, useEffect } from 'react';
import { Sparkles } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { api } from '../api';
import {
  DailyRevenueChart, MultiLineChart, formatUZS, formatShort, daysAgo, today,
} from '../components/RevenueCharts';

const PRESETS = [
  { key: '7d', label: '7 дней', from: () => daysAgo(7) },
  { key: '30d', label: '30 дней', from: () => daysAgo(30) },
  { key: '90d', label: '90 дней', from: () => daysAgo(90) },
];

export default function SpaAnalytics() {
  const [activePreset, setActivePreset] = useState('30d');
  const [dateFrom, setDateFrom] = useState(daysAgo(30));
  const [dateTo, setDateTo] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getSpaDaily(dateFrom, dateTo)
      .then(res => { if (!cancelled) { setData(res); setLoading(false); } })
      .catch(err => { console.error('Failed to load SPA analytics:', err); if (!cancelled) { setData(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [dateFrom, dateTo]);

  function applyPreset(key) {
    const preset = PRESETS.find(p => p.key === key);
    if (preset) {
      setActivePreset(key);
      setDateFrom(preset.from());
      setDateTo(today());
    }
  }

  const periodLabel = activePreset === '7d' ? 'Последние 7 дней'
    : activePreset === '30d' ? 'Последние 30 дней'
    : activePreset === '90d' ? 'Последние 90 дней'
    : `${dateFrom} — ${dateTo}`;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
          <Sparkles size={22} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-800">SPA · Аналитика</h1>
          <p className="text-gray-500 text-sm">{periodLabel}</p>
        </div>
      </div>

      {/* Period selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex gap-1.5">
            {PRESETS.map(p => (
              <button key={p.key} onClick={() => applyPreset(p.key)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activePreset === p.key
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 hover:bg-blue-50 hover:text-blue-600 text-gray-600'
                }`}>
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <input type="date" value={dateFrom}
              onChange={e => { setActivePreset('custom'); setDateFrom(e.target.value); }}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
            <span className="text-gray-400 text-sm">—</span>
            <input type="date" value={dateTo}
              onChange={e => { setActivePreset('custom'); setDateTo(e.target.value); }}
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : !data ? (
        <p className="text-gray-400 text-center py-20">Не удалось загрузить данные</p>
      ) : (
        <>
          {/* Daily stacked revenue by service type */}
          <DailyRevenueChart
            title="Выручка SPA по дням"
            data={data.daily_by_service_type || []}
            methods={data.service_types || []}
            periodLabel={periodLabel}
          />

          {/* Trend lines per service type */}
          <MultiLineChart
            title="Тренды по типам услуг"
            data={data.daily_by_service_type || []}
            series={data.service_types || []}
            periodLabel={periodLabel}
          />

          {/* Totals by individual service */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">Доход по услугам (всего за период)</h2>
              <span className="text-sm font-semibold text-gray-800">{formatUZS(data.total || 0)}</span>
            </div>
            {data.by_service?.length > 0 ? (
              <ResponsiveContainer width="100%" height={Math.max(220, data.by_service.length * 34)}>
                <BarChart data={data.by_service} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={formatShort} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={190} />
                  <Tooltip formatter={(v) => formatUZS(v)} />
                  <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-gray-400 text-center py-16">Нет данных об услугах за этот период</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
