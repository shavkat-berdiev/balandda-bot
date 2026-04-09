import { useState, useEffect } from 'react';
import { Calendar, ChevronDown, ChevronUp, FileText, Pencil, Trash2, Save, X, Building2 } from 'lucide-react';
import { api } from '../api';

const STATUS_LABELS = { DRAFT: 'Черновик', SUBMITTED: 'Отправлен', APPROVED: 'Утверждён' };
const STATUS_COLORS = {
  DRAFT: 'bg-yellow-50 text-yellow-700',
  SUBMITTED: 'bg-blue-50 text-blue-700',
  APPROVED: 'bg-green-50 text-green-700',
};

const BU_LABELS = { RESORT: 'Курорт', RESTAURANT: 'Ресторан' };

const PM_OPTIONS = [
  { value: 'CASH', label: 'Наличные' },
  { value: 'CARD_TRANSFER', label: 'Перевод на карту' },
  { value: 'TERMINAL_VISA', label: 'Терминал Visa' },
  { value: 'TERMINAL_UZCARD', label: 'Терминал UzCard' },
  { value: 'PAYME', label: 'Payme' },
  { value: 'PREPAYMENT', label: 'Предоплата' },
];

function getDefaultDates() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 30);
  return {
    from: from.toISOString().split('T')[0],
    to: today.toISOString().split('T')[0],
  };
}

export default function AdminReports({ user }) {
  const defaults = getDefaultDates();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [businessUnit, setBusinessUnit] = useState('ALL');

  // Edit states
  const [editingReportId, setEditingReportId] = useState(null);
  const [editReportDate, setEditReportDate] = useState('');
  const [editReportBU, setEditReportBU] = useState('');
  const [editingEntryId, setEditingEntryId] = useState(null);
  const [editEntryData, setEditEntryData] = useState({});

  const isOwner = user?.role?.toUpperCase() === 'OWNER';

  useEffect(() => { loadReports(); }, []);

  async function loadReports() {
    setLoading(true);
    setError('');
    try {
      const data = await api.getStructuredReportsList(dateFrom, dateTo, businessUnit);
      setReports(data);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  async function toggleDetail(reportId) {
    if (expandedId === reportId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(reportId);
    setDetailLoading(true);
    try {
      const data = await api.getStructuredReportDetail(reportId);
      setDetail(data);
    } catch (err) {
      setError(err.message);
    }
    setDetailLoading(false);
  }

  async function reloadDetail(reportId) {
    try {
      const data = await api.getStructuredReportDetail(reportId);
      setDetail(data);
      // Update summary in list
      setReports((prev) =>
        prev.map((r) =>
          r.id === reportId
            ? {
                ...r,
                report_date: data.report_date,
                total_income: data.total_income,
                total_expense: data.total_expense,
                net: data.net,
                income_count: data.income_entries.length,
                expense_count: data.expense_entries.length,
              }
            : r
        )
      );
    } catch (err) {
      setError(err.message);
    }
  }

  // ── Report metadata edit ──

  function startEditReport(report) {
    setEditingReportId(report.id);
    setEditReportDate(report.report_date);
    setEditReportBU(report.business_unit);
  }

  async function saveReportEdit() {
    setSaving(true);
    try {
      await api.updateReport(editingReportId, {
        report_date: editReportDate,
        business_unit: editReportBU,
      });
      setEditingReportId(null);
      await reloadDetail(expandedId);
      await loadReports();
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  // ── Income entry edit ──

  function startEditIncome(entry) {
    setEditingEntryId(`inc-${entry.id}`);
    setEditEntryData({
      amount: entry.amount,
      payment_method: entry.payment_method,
      quantity: entry.quantity,
      num_days: entry.num_days,
      note: entry.note || '',
    });
  }

  async function saveIncomeEdit(entryId) {
    setSaving(true);
    try {
      await api.updateIncomeEntry(entryId, editEntryData);
      setEditingEntryId(null);
      await reloadDetail(expandedId);
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  async function deleteIncome(entryId) {
    if (!confirm('Удалить эту запись дохода?')) return;
    setSaving(true);
    try {
      await api.deleteIncomeEntry(entryId);
      await reloadDetail(expandedId);
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  // ── Expense entry edit ──

  function startEditExpense(entry) {
    setEditingEntryId(`exp-${entry.id}`);
    setEditEntryData({
      amount: entry.amount,
      description: entry.description || '',
      note: entry.note || '',
    });
  }

  async function saveExpenseEdit(entryId) {
    setSaving(true);
    try {
      await api.updateExpenseEntry(entryId, editEntryData);
      setEditingEntryId(null);
      await reloadDetail(expandedId);
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  async function deleteExpense(entryId) {
    if (!confirm('Удалить эту запись расхода?')) return;
    setSaving(true);
    try {
      await api.deleteExpenseEntry(entryId);
      await reloadDetail(expandedId);
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  const fmt = (n) => Number(n).toLocaleString('ru-RU');
  const fmtDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('ru-RU');

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Отчёты</h1>
          <p className="text-gray-500 text-sm mt-1">Структурированные отчёты с предоплатами</p>
        </div>
      </div>

      {/* Date filter */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">С</label>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">По</label>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <div className="flex gap-1.5">
            {[
              { key: 'ALL', label: 'Все' },
              { key: 'RESORT', label: 'Курорт' },
              { key: 'RESTAURANT', label: 'Ресторан' },
            ].map(({ key, label }) => (
              <button key={key}
                onClick={() => { setBusinessUnit(key); }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  businessUnit === key
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-blue-50'
                }`}>
                {label}
              </button>
            ))}
          </div>
          <button onClick={loadReports}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            <Calendar size={16} /> Показать
          </button>
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : reports.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <FileText size={48} className="mx-auto mb-3 opacity-50" />
          <p>Нет отчётов за выбранный период</p>
        </div>
      ) : (
        <div className="space-y-3">
          {reports.map(report => (
            <div key={report.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              {/* Report header row */}
              <button onClick={() => toggleDetail(report.id)}
                className="w-full px-5 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-4">
                  <div className="text-left">
                    <p className="font-semibold text-gray-800">{fmtDate(report.report_date)}</p>
                    <div className="flex gap-3 text-xs text-gray-500 mt-1">
                      {businessUnit === 'ALL' && (
                        <span className={`px-1.5 py-0.5 rounded font-medium ${report.business_unit === 'RESORT' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>
                          {BU_LABELS[report.business_unit] || report.business_unit}
                        </span>
                      )}
                      <span>Доходы: {report.income_count}</span>
                      <span>Расходы: {report.expense_count}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-sm font-semibold text-green-600">+{fmt(report.total_income)}</p>
                    <p className="text-sm font-semibold text-red-500">-{fmt(report.total_expense)}</p>
                  </div>
                  <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[report.status] || 'bg-gray-100 text-gray-500'}`}>
                    {STATUS_LABELS[report.status] || report.status}
                  </span>
                  {expandedId === report.id ? <ChevronUp size={18} className="text-gray-400" /> : <ChevronDown size={18} className="text-gray-400" />}
                </div>
              </button>

              {/* Expanded detail */}
              {expandedId === report.id && (
                <div className="border-t border-gray-100 px-5 py-4">
                  {detailLoading ? (
                    <div className="flex justify-center py-4"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div></div>
                  ) : detail ? (
                    <div className="space-y-4">

                      {/* Report metadata edit (owner only) */}
                      {isOwner && (
                        <div className="bg-gray-50 rounded-lg p-3">
                          {editingReportId === detail.id ? (
                            <div className="flex flex-wrap items-end gap-3">
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Дата</label>
                                <input type="date" value={editReportDate}
                                  onChange={(e) => setEditReportDate(e.target.value)}
                                  className="px-2 py-1.5 border border-gray-300 rounded text-sm" />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Подразделение</label>
                                <select value={editReportBU}
                                  onChange={(e) => setEditReportBU(e.target.value)}
                                  className="px-2 py-1.5 border border-gray-300 rounded text-sm">
                                  <option value="RESORT">Курорт</option>
                                  <option value="RESTAURANT">Ресторан</option>
                                </select>
                              </div>
                              <div className="flex gap-1">
                                <button onClick={saveReportEdit} disabled={saving}
                                  className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                                  <Save size={14} /> Сохранить
                                </button>
                                <button onClick={() => setEditingReportId(null)}
                                  className="flex items-center gap-1 px-3 py-1.5 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300">
                                  <X size={14} />
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-3 text-sm text-gray-600">
                                <Building2 size={16} />
                                <span>{BU_LABELS[detail.business_unit] || detail.business_unit}</span>
                                <span className="text-gray-400">|</span>
                                <span>{fmtDate(detail.report_date)}</span>
                                {detail.note && (
                                  <>
                                    <span className="text-gray-400">|</span>
                                    <span className="text-gray-500 italic">{detail.note}</span>
                                  </>
                                )}
                              </div>
                              <button onClick={() => startEditReport(detail)}
                                className="flex items-center gap-1 px-2 py-1 text-blue-600 hover:bg-blue-50 rounded text-xs font-medium">
                                <Pencil size={13} /> Изменить
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Income entries */}
                      {detail.income_entries.length > 0 && (
                        <div>
                          <h3 className="text-sm font-semibold text-gray-700 mb-2">Доходы</h3>
                          <div className="space-y-2">
                            {detail.income_entries.map(entry => (
                              <div key={entry.id}>
                                {editingEntryId === `inc-${entry.id}` ? (
                                  /* Inline edit form for income */
                                  <div className="flex flex-wrap items-end gap-2 px-3 py-2 bg-green-50 rounded-lg text-sm border border-green-200">
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Сумма</label>
                                      <input type="number" value={editEntryData.amount}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, amount: Number(e.target.value) })}
                                        className="w-28 px-2 py-1 border border-gray-300 rounded text-sm" />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Оплата</label>
                                      <select value={editEntryData.payment_method}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, payment_method: e.target.value })}
                                        className="px-2 py-1 border border-gray-300 rounded text-sm">
                                        {PM_OPTIONS.map(pm => <option key={pm.value} value={pm.value}>{pm.label}</option>)}
                                      </select>
                                    </div>
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Кол-во</label>
                                      <input type="number" value={editEntryData.quantity}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, quantity: Number(e.target.value) })}
                                        className="w-16 px-2 py-1 border border-gray-300 rounded text-sm" />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Дни</label>
                                      <input type="number" value={editEntryData.num_days}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, num_days: Number(e.target.value) })}
                                        className="w-16 px-2 py-1 border border-gray-300 rounded text-sm" />
                                    </div>
                                    <div className="flex gap-1">
                                      <button onClick={() => saveIncomeEdit(entry.id)} disabled={saving}
                                        className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50">
                                        <Save size={12} />
                                      </button>
                                      <button onClick={() => setEditingEntryId(null)}
                                        className="flex items-center gap-1 px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300">
                                        <X size={12} />
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  /* Display mode for income */
                                  <div className="flex items-center justify-between px-3 py-2 bg-green-50 rounded-lg text-sm group">
                                    <div>
                                      <span className="font-medium text-gray-800">
                                        {entry.property_name || entry.service_name || entry.minibar_name || 'Запись'}
                                      </span>
                                      <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${entry.payment_method === 'PREPAYMENT' ? 'bg-yellow-100 text-yellow-700 font-semibold' : 'bg-gray-100 text-gray-500'}`}>
                                        {entry.payment_label}
                                      </span>
                                      {entry.num_days > 1 && <span className="ml-2 text-xs text-gray-500">{entry.num_days} дней</span>}
                                      {entry.discount_value && (
                                        <span className="ml-2 text-xs text-orange-600">
                                          скидка: {entry.discount_type === 'PERCENTAGE' ? `${entry.discount_value}%` : fmt(entry.discount_value)}
                                        </span>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="font-mono font-semibold text-green-700">{fmt(entry.amount)}</span>
                                      {isOwner && (
                                        <div className="hidden group-hover:flex gap-1">
                                          <button onClick={(e) => { e.stopPropagation(); startEditIncome(entry); }}
                                            className="p-1 text-gray-400 hover:text-blue-600 rounded" title="Редактировать">
                                            <Pencil size={14} />
                                          </button>
                                          <button onClick={(e) => { e.stopPropagation(); deleteIncome(entry.id); }}
                                            className="p-1 text-gray-400 hover:text-red-600 rounded" title="Удалить">
                                            <Trash2 size={14} />
                                          </button>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Expense entries */}
                      {detail.expense_entries.length > 0 && (
                        <div>
                          <h3 className="text-sm font-semibold text-gray-700 mb-2">Расходы</h3>
                          <div className="space-y-2">
                            {detail.expense_entries.map(entry => (
                              <div key={entry.id}>
                                {editingEntryId === `exp-${entry.id}` ? (
                                  /* Inline edit form for expense */
                                  <div className="flex flex-wrap items-end gap-2 px-3 py-2 bg-red-50 rounded-lg text-sm border border-red-200">
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Сумма</label>
                                      <input type="number" value={editEntryData.amount}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, amount: Number(e.target.value) })}
                                        className="w-28 px-2 py-1 border border-gray-300 rounded text-sm" />
                                    </div>
                                    <div>
                                      <label className="block text-xs text-gray-500 mb-0.5">Описание</label>
                                      <input type="text" value={editEntryData.description}
                                        onChange={(e) => setEditEntryData({ ...editEntryData, description: e.target.value })}
                                        className="w-40 px-2 py-1 border border-gray-300 rounded text-sm" />
                                    </div>
                                    <div className="flex gap-1">
                                      <button onClick={() => saveExpenseEdit(entry.id)} disabled={saving}
                                        className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50">
                                        <Save size={12} />
                                      </button>
                                      <button onClick={() => setEditingEntryId(null)}
                                        className="flex items-center gap-1 px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300">
                                        <X size={12} />
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  /* Display mode for expense */
                                  <div className="flex items-center justify-between px-3 py-2 bg-red-50 rounded-lg text-sm group">
                                    <div>
                                      <span className="font-medium text-gray-800">{entry.category_label}</span>
                                      {entry.staff_member_name && <span className="ml-2 text-xs text-gray-500">({entry.staff_member_name})</span>}
                                      {entry.description && <span className="ml-2 text-xs text-gray-500">— {entry.description}</span>}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="font-mono font-semibold text-red-600">{fmt(entry.amount)}</span>
                                      {isOwner && (
                                        <div className="hidden group-hover:flex gap-1">
                                          <button onClick={(e) => { e.stopPropagation(); startEditExpense(entry); }}
                                            className="p-1 text-gray-400 hover:text-blue-600 rounded" title="Редактировать">
                                            <Pencil size={14} />
                                          </button>
                                          <button onClick={(e) => { e.stopPropagation(); deleteExpense(entry.id); }}
                                            className="p-1 text-gray-400 hover:text-red-600 rounded" title="Удалить">
                                            <Trash2 size={14} />
                                          </button>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Net summary */}
                      <div className="flex justify-end pt-2 border-t border-gray-100">
                        <div className="text-right">
                          <p className="text-sm text-gray-600">Итого: <span className={`font-semibold ${detail.net >= 0 ? 'text-green-700' : 'text-red-600'}`}>{detail.net >= 0 ? '+' : ''}{fmt(detail.net)}</span></p>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
