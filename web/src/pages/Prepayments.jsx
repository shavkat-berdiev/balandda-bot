import { useState, useEffect, useMemo } from 'react';
import { api } from '../api';

const STATUS_COLORS = {
  PENDING: { bg: 'bg-yellow-100', text: 'text-yellow-800', dot: 'bg-yellow-400' },
  CONFIRMED: { bg: 'bg-blue-100', text: 'text-blue-800', dot: 'bg-blue-400' },
  SETTLED: { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-400' },
  CANCELLED: { bg: 'bg-red-100', text: 'text-red-800', dot: 'bg-red-400' },
};

const STATUS_LABELS = {
  PENDING: 'Ожидает',
  CONFIRMED: 'Подтверждён',
  SETTLED: 'Зачтён',
  CANCELLED: 'Отменён',
};

const STATUSES = ['PENDING', 'CONFIRMED', 'SETTLED', 'CANCELLED'];

function formatAmount(n) {
  return Number(n).toLocaleString('ru-RU').replace(/,/g, ' ');
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function shortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function getMonthDays(year, month) {
  const days = [];
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  // Pad start to Monday
  let startPad = (firstDay.getDay() + 6) % 7; // Monday=0
  for (let i = startPad - 1; i >= 0; i--) {
    const d = new Date(year, month, -i);
    days.push({ date: d, isCurrentMonth: false });
  }
  for (let i = 1; i <= lastDay.getDate(); i++) {
    days.push({ date: new Date(year, month, i), isCurrentMonth: true });
  }
  // Pad end
  while (days.length % 7 !== 0) {
    const last = days[days.length - 1].date;
    const next = new Date(last);
    next.setDate(next.getDate() + 1);
    days.push({ date: next, isCurrentMonth: false });
  }
  return days;
}

function toISO(d) {
  return d.toISOString().split('T')[0];
}

export default function Prepayments() {
  const [calendarDate, setCalendarDate] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const [calendarData, setCalendarData] = useState({});
  const [stats, setStats] = useState({ total: 0, total_amount: 0, by_status: {} });
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedPrepayment, setSelectedPrepayment] = useState(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [allPrepayments, setAllPrepayments] = useState([]);

  // Load calendar data
  useEffect(() => {
    loadCalendar();
  }, [calendarDate, filterStatus]);

  async function loadCalendar() {
    setLoading(true);
    try {
      const startDate = new Date(calendarDate.year, calendarDate.month, 1);
      const endDate = new Date(calendarDate.year, calendarDate.month + 1, 0);
      // Extend range to show prepayments visible in padded days
      startDate.setDate(startDate.getDate() - 7);
      endDate.setDate(endDate.getDate() + 7);

      const params = {
        start_date: toISO(startDate),
        end_date: toISO(endDate),
      };
      if (filterStatus) params.status = filterStatus;

      const data = await api.getPrepaymentsList(params);
      setAllPrepayments(data.prepayments || []);
      setStats({ total: data.total, total_amount: data.total_amount });

      // Group by check_in_date
      const byDate = {};
      for (const p of (data.prepayments || [])) {
        if (!byDate[p.check_in_date]) byDate[p.check_in_date] = [];
        byDate[p.check_in_date].push(p);
      }
      setCalendarData(byDate);

      // Build status counts
      const bySt = {};
      for (const p of (data.prepayments || [])) {
        bySt[p.status] = (bySt[p.status] || 0) + 1;
      }
      setStats(prev => ({ ...prev, by_status: bySt }));
    } catch (err) {
      console.error('Failed to load prepayments', err);
    }
    setLoading(false);
  }

  const days = useMemo(
    () => getMonthDays(calendarDate.year, calendarDate.month),
    [calendarDate]
  );

  const monthName = new Date(calendarDate.year, calendarDate.month, 1)
    .toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });

  function prevMonth() {
    setCalendarDate(prev => {
      let m = prev.month - 1, y = prev.year;
      if (m < 0) { m = 11; y--; }
      return { year: y, month: m };
    });
    setSelectedDate(null);
    setSelectedPrepayment(null);
  }

  function nextMonth() {
    setCalendarDate(prev => {
      let m = prev.month + 1, y = prev.year;
      if (m > 11) { m = 0; y++; }
      return { year: y, month: m };
    });
    setSelectedDate(null);
    setSelectedPrepayment(null);
  }

  function onDayClick(dateISO) {
    setSelectedDate(dateISO === selectedDate ? null : dateISO);
    setSelectedPrepayment(null);
  }

  async function onStatusChange(prepaymentId, newStatus) {
    try {
      await api.updatePrepaymentStatus(prepaymentId, newStatus);
      await loadCalendar();
      if (selectedPrepayment?.id === prepaymentId) {
        setSelectedPrepayment(prev => ({ ...prev, status: newStatus, status_label: STATUS_LABELS[newStatus] }));
      }
    } catch (err) {
      alert('Ошибка: ' + err.message);
    }
  }

  const dayPrepayments = selectedDate ? (calendarData[selectedDate] || []) : [];
  const todayISO = toISO(new Date());

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Предоплаты</h1>
          <p className="text-sm text-gray-500 mt-1">Мониторинг предоплат по датам заезда</p>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase">Всего</p>
          <p className="text-xl font-bold text-gray-900">{stats.total}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase">Сумма</p>
          <p className="text-xl font-bold text-gray-900">{formatAmount(stats.total_amount)} <span className="text-sm text-gray-500">UZS</span></p>
        </div>
        {STATUSES.slice(0, 3).map(s => (
          <div key={s} className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500 uppercase">{STATUS_LABELS[s]}</p>
            <p className={`text-xl font-bold ${STATUS_COLORS[s].text}`}>{stats.by_status?.[s] || 0}</p>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-sm text-gray-600">Фильтр:</span>
        <button
          onClick={() => setFilterStatus('')}
          className={`px-3 py-1 rounded-full text-sm ${!filterStatus ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
        >
          Все
        </button>
        {STATUSES.map(s => (
          <button
            key={s}
            onClick={() => setFilterStatus(filterStatus === s ? '' : s)}
            className={`px-3 py-1 rounded-full text-sm ${filterStatus === s ? `${STATUS_COLORS[s].bg} ${STATUS_COLORS[s].text} font-medium` : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-5">
          {/* Calendar header */}
          <div className="flex items-center justify-between mb-4">
            <button onClick={prevMonth} className="px-3 py-1.5 rounded-lg hover:bg-gray-100 text-gray-600 font-medium">◀</button>
            <h2 className="text-lg font-semibold text-gray-800 capitalize">{monthName}</h2>
            <button onClick={nextMonth} className="px-3 py-1.5 rounded-lg hover:bg-gray-100 text-gray-600 font-medium">▶</button>
          </div>

          {/* Day headers */}
          <div className="grid grid-cols-7 text-center text-xs font-medium text-gray-500 mb-2">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(d => (
              <div key={d} className="py-1">{d}</div>
            ))}
          </div>

          {/* Day grid */}
          <div className="grid grid-cols-7">
            {days.map(({ date: d, isCurrentMonth }, i) => {
              const iso = toISO(d);
              const entries = calendarData[iso] || [];
              const isToday = iso === todayISO;
              const isSelected = iso === selectedDate;
              const hasEntries = entries.length > 0;

              return (
                <div
                  key={i}
                  onClick={() => onDayClick(iso)}
                  className={`relative min-h-[72px] p-1 border border-gray-100 cursor-pointer transition-colors
                    ${!isCurrentMonth ? 'bg-gray-50 text-gray-300' : 'hover:bg-blue-50'}
                    ${isSelected ? 'bg-blue-50 ring-2 ring-blue-400 z-10' : ''}
                    ${isToday ? 'bg-yellow-50' : ''}
                  `}
                >
                  <span className={`text-xs font-medium ${isToday ? 'text-blue-600 font-bold' : isCurrentMonth ? 'text-gray-700' : 'text-gray-300'}`}>
                    {d.getDate()}
                  </span>
                  {hasEntries && (
                    <div className="mt-0.5 space-y-0.5">
                      {entries.slice(0, 2).map((p, j) => (
                        <div
                          key={j}
                          className={`text-[10px] leading-tight px-1 py-0.5 rounded truncate ${STATUS_COLORS[p.status]?.bg || 'bg-gray-100'} ${STATUS_COLORS[p.status]?.text || 'text-gray-700'}`}
                        >
                          {p.guest_name}
                        </div>
                      ))}
                      {entries.length > 2 && (
                        <div className="text-[10px] text-gray-500 px-1">+{entries.length - 2} ещё</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Side panel: selected date detail or prepayment detail */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 max-h-[600px] overflow-y-auto">
          {selectedPrepayment ? (
            <PrepaymentDetail
              p={selectedPrepayment}
              onBack={() => setSelectedPrepayment(null)}
              onStatusChange={onStatusChange}
            />
          ) : selectedDate ? (
            <div>
              <h3 className="font-semibold text-gray-800 mb-3">
                📅 {formatDate(selectedDate)}
              </h3>
              {dayPrepayments.length === 0 ? (
                <p className="text-gray-400 text-sm py-8 text-center">Нет предоплат на эту дату</p>
              ) : (
                <div className="space-y-3">
                  {dayPrepayments.map(p => (
                    <div
                      key={p.id}
                      onClick={() => setSelectedPrepayment(p)}
                      className="p-3 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-gray-800">{p.guest_name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[p.status]?.bg} ${STATUS_COLORS[p.status]?.text}`}>
                          {p.status_label}
                        </span>
                      </div>
                      <div className="text-sm text-gray-500">
                        {p.property_emoji} {p.property_name}
                      </div>
                      <div className="text-sm text-gray-500">
                        {shortDate(p.check_in_date)} → {shortDate(p.check_out_date)} ({p.nights} н.)
                      </div>
                      <div className="text-sm font-semibold text-gray-800 mt-1">
                        {formatAmount(p.amount)} UZS
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-gray-400 text-sm py-12 text-center">
              Выберите дату на календаре для просмотра предоплат
            </div>
          )}
        </div>
      </div>

      {/* Timeline list below calendar */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Все предоплаты</h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-400">Загрузка...</div>
        ) : allPrepayments.length === 0 ? (
          <div className="p-8 text-center text-gray-400">Нет предоплат за выбранный период</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-100">
                  <th className="px-5 py-3">Дата заезда</th>
                  <th className="px-5 py-3">Гость</th>
                  <th className="px-5 py-3">Объект</th>
                  <th className="px-5 py-3">Ночей</th>
                  <th className="px-5 py-3">Оплата</th>
                  <th className="px-5 py-3">Сумма</th>
                  <th className="px-5 py-3">Статус</th>
                </tr>
              </thead>
              <tbody>
                {allPrepayments.map(p => (
                  <tr
                    key={p.id}
                    onClick={() => {
                      setSelectedDate(p.check_in_date);
                      setSelectedPrepayment(p);
                    }}
                    className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
                  >
                    <td className="px-5 py-3 whitespace-nowrap">{formatDate(p.check_in_date)}</td>
                    <td className="px-5 py-3 font-medium text-gray-800">{p.guest_name}</td>
                    <td className="px-5 py-3 text-gray-600">{p.property_emoji} {p.property_name}</td>
                    <td className="px-5 py-3 text-gray-600">{p.nights}</td>
                    <td className="px-5 py-3 text-gray-600">{p.payment_method_label}</td>
                    <td className="px-5 py-3 font-semibold text-gray-800">{formatAmount(p.amount)}</td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full ${STATUS_COLORS[p.status]?.bg} ${STATUS_COLORS[p.status]?.text}`}>
                        {p.status_label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function PrepaymentDetail({ p, onBack, onStatusChange }) {
  return (
    <div>
      <button onClick={onBack} className="text-sm text-blue-600 hover:text-blue-800 mb-3 flex items-center gap-1">
        ← Назад
      </button>
      <h3 className="font-semibold text-gray-800 text-lg mb-4">Детали предоплаты</h3>

      <div className="space-y-3">
        <div>
          <span className="text-xs text-gray-500 uppercase">Гость</span>
          <p className="font-medium text-gray-800">{p.guest_name}</p>
        </div>
        <div>
          <span className="text-xs text-gray-500 uppercase">Объект</span>
          <p className="text-gray-800">{p.property_emoji} {p.property_name}</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className="text-xs text-gray-500 uppercase">Заезд</span>
            <p className="text-gray-800">{formatDate(p.check_in_date)}</p>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase">Выезд</span>
            <p className="text-gray-800">{formatDate(p.check_out_date)}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className="text-xs text-gray-500 uppercase">Ночей</span>
            <p className="text-gray-800">{p.nights}</p>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase">Оплата</span>
            <p className="text-gray-800">{p.payment_method_label}</p>
          </div>
        </div>
        <div>
          <span className="text-xs text-gray-500 uppercase">Сумма</span>
          <p className="text-xl font-bold text-gray-900">{formatAmount(p.amount)} UZS</p>
        </div>
        <div>
          <span className="text-xs text-gray-500 uppercase">Скриншот</span>
          <p className="text-gray-800">{p.has_screenshot ? '✅ Загружен' : '❌ Нет'}</p>
        </div>
        <div>
          <span className="text-xs text-gray-500 uppercase">Создано</span>
          <p className="text-gray-600 text-sm">{p.created_at ? new Date(p.created_at).toLocaleString('ru-RU') : '—'}</p>
        </div>

        {/* Status management */}
        <div className="pt-3 border-t border-gray-100">
          <span className="text-xs text-gray-500 uppercase block mb-2">Статус</span>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map(s => (
              <button
                key={s}
                onClick={() => onStatusChange(p.id, s)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                  ${p.status === s
                    ? `${STATUS_COLORS[s].bg} ${STATUS_COLORS[s].text} ring-2 ring-offset-1 ring-current`
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
              >
                {STATUS_LABELS[s]}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
