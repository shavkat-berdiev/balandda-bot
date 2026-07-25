import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, LabelList,
} from 'recharts';

export function formatUZS(amount) {
  return new Intl.NumberFormat('ru-RU').format(Math.round(amount)) + ' UZS';
}

export function formatShort(amount) {
  if (amount >= 1_000_000) return (amount / 1_000_000).toFixed(1) + 'M';
  if (amount >= 1_000) return (amount / 1_000).toFixed(0) + 'k';
  return String(Math.round(amount));
}

export function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split('T')[0];
}

export function today() {
  return new Date().toISOString().split('T')[0];
}

// Maximally-distinct categorical fallback palette (no greens — green is
// reserved for "Наличные"). Adjacent hues are far apart on purpose.
export const DISTINCT_COLORS = [
  '#2563eb', // blue
  '#f97316', // orange
  '#8b5cf6', // violet
  '#dc2626', // red
  '#0891b2', // cyan
  '#db2777', // pink
  '#a16207', // brown
  '#64748b', // slate
  '#eab308', // yellow
  '#0f766e', // dark teal
  '#7c3aed', // deep purple
  '#9f1239', // dark rose
];

// Fixed colors for known series names (payment methods, POS types, business units)
export const SERIES_COLORS = {
  // Report payment methods
  'Наличные': '#16a34a',
  'Перевод на карту': '#2563eb',
  'Перечисление': '#0891b2',
  'Терминал Visa': '#8b5cf6',
  'Терминал UzCard': '#7c3aed',
  'PayMe': '#db2777',
  'Предоплата': '#eab308',
  // Billz (XUSH) payment types
  'Карта': '#f97316',
  'UzCard': '#7c3aed',
  'Marketplaces': '#a16207',
  'BILLZ Pay': '#0891b2',
  // iiko payment types
  'Rahmat': '#db2777',
  'UzCard/HUMO/VISA/MASTER': '#8b5cf6',
  'Аванс': '#64748b',
  // Business units
  'Курорт': '#2563eb',
  'Ресторан': '#f97316',
  'XUSH': '#8b5cf6',
};

export function seriesColor(name, index) {
  if (SERIES_COLORS[name]) return SERIES_COLORS[name];
  // Skip fallback colors already claimed by known names present in this chart
  return DISTINCT_COLORS[index % DISTINCT_COLORS.length];
}

const fmtDay = d => {
  const dt = new Date(d + 'T00:00:00');
  return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
};

// White value label inside a bar segment; hidden when the segment is too small
function segLabel(props) {
  const { x, y, width, height, value } = props;
  if (!value || height < 13 || width < 26) return null;
  return (
    <text x={x + width / 2} y={y + height / 2} fill="#ffffff" fontSize={9}
      fontWeight={600} textAnchor="middle" dominantBaseline="central"
      style={{ pointerEvents: 'none' }}>
      {formatShort(value)}
    </text>
  );
}

export function DailyRevenueChart({ data, methods, periodLabel, title = 'Выручка по дням' }) {
  const hasValues = data && data.length > 0 && data.some(d => d.total > 0);
  const totalRevenue = (data || []).reduce((s, d) => s + (d.total || 0), 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 mb-4">
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        <div className="text-sm text-gray-500">
          {periodLabel} · <span className="font-semibold text-gray-800">{formatUZS(totalRevenue)}</span>
        </div>
      </div>
      {hasValues ? (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={fmtDay}
              interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={formatShort} />
            <Tooltip
              formatter={(v, name) => [formatUZS(v), name]}
              labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU')}
              itemSorter={item => -item.value}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {methods.map((m, i) => (
              <Bar key={m} dataKey={m} name={m} stackId="rev"
                fill={seriesColor(m, i)}
                radius={i === methods.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}>
                <LabelList dataKey={m} content={segLabel} />
                {i === methods.length - 1 && (
                  <LabelList dataKey="total" position="top"
                    formatter={v => (v > 0 ? formatShort(v) : '')}
                    style={{ fontSize: 10, fill: '#374151', fontWeight: 600 }} />
                )}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-gray-400 text-center py-16">Нет данных о выручке за этот период</p>
      )}
    </div>
  );
}

export function MultiLineChart({ data, series, periodLabel, title, height = 320 }) {
  const hasValues = data && data.length > 0 && series && series.length > 0
    && data.some(d => series.some(s => d[s] > 0));

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 mb-4">
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        {periodLabel && <div className="text-sm text-gray-500">{periodLabel}</div>}
      </div>
      {hasValues ? (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={fmtDay}
              interval="preserveStartEnd" minTickGap={16} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={formatShort} />
            <Tooltip
              formatter={(v, name) => [formatUZS(v), name]}
              labelFormatter={d => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU')}
              itemSorter={item => -item.value}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((s, i) => (
              <Line key={s} type="monotone" dataKey={s} name={s}
                stroke={seriesColor(s, i)} strokeWidth={2}
                dot={{ r: 2 }} activeDot={{ r: 4 }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-gray-400 text-center py-16">Нет данных за этот период</p>
      )}
    </div>
  );
}
