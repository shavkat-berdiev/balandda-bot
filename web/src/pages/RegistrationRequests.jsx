import { useState, useEffect } from 'react';
import { api } from '../api';

const STATUS_COLORS = {
  PENDING: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  APPROVED: { bg: 'bg-green-100', text: 'text-green-800' },
  REJECTED: { bg: 'bg-red-100', text: 'text-red-800' },
};

function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function RegistrationRequests() {
  const [requests, setRequests] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  const [filterStatus, setFilterStatus] = useState('');
  const [processing, setProcessing] = useState(null);
  const [selectedRoles, setSelectedRoles] = useState({});

  useEffect(() => {
    loadData();
  }, [filterStatus]);

  async function loadData() {
    try {
      const [reqData, roleData] = await Promise.all([
        api.getRegistrationRequests(filterStatus ? { status: filterStatus } : {}),
        api.getRegistrationRoles(),
      ]);
      setRequests(reqData.requests || []);
      setPendingCount(reqData.pending_count || 0);
      setRoles(roleData.roles || []);
    } catch (err) {
      console.error('Failed to load:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDecision(requestId, status) {
    const role = selectedRoles[requestId];
    if (status === 'APPROVED' && !role) {
      alert('Выберите роль для пользователя');
      return;
    }

    setProcessing(requestId);
    try {
      await api.decideRegistrationRequest(requestId, {
        status,
        role: status === 'APPROVED' ? role : undefined,
      });
      await loadData();
    } catch (err) {
      alert(err.message || 'Ошибка');
    } finally {
      setProcessing(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Заявки на регистрацию</h1>
          {pendingCount > 0 && (
            <p className="text-sm text-yellow-600 mt-1">
              {pendingCount} {pendingCount === 1 ? 'заявка ожидает' : 'заявок ожидают'} рассмотрения
            </p>
          )}
        </div>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-1.5"
        >
          <option value="">Все статусы</option>
          <option value="PENDING">Ожидающие</option>
          <option value="APPROVED">Одобренные</option>
          <option value="REJECTED">Отклонённые</option>
        </select>
      </div>

      {requests.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center text-gray-400">
          Нет заявок
        </div>
      ) : (
        <div className="space-y-4">
          {requests.map((r) => {
            const colors = STATUS_COLORS[r.status] || STATUS_COLORS.PENDING;
            const isPending = r.status === 'PENDING';
            const isProcessing = processing === r.id;

            return (
              <div key={r.id} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold">
                      {r.full_name?.charAt(0) || '?'}
                    </div>
                    <div>
                      <div className="font-medium text-gray-900">{r.full_name}</div>
                      <div className="text-sm text-gray-500">
                        {r.username ? `@${r.username}` : `ID: ${r.telegram_id}`}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {formatDateTime(r.created_at)}
                      </div>
                    </div>
                  </div>

                  <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
                    {r.status_label}
                  </span>
                </div>

                {isPending && (
                  <div className="mt-4 flex items-center gap-3 pt-4 border-t border-gray-100">
                    <select
                      value={selectedRoles[r.id] || ''}
                      onChange={(e) => setSelectedRoles({ ...selectedRoles, [r.id]: e.target.value })}
                      className="text-sm border border-gray-300 rounded-lg px-3 py-2 flex-1"
                    >
                      <option value="">Выберите роль...</option>
                      {roles.map((role) => (
                        <option key={role.value} value={role.value}>{role.label}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleDecision(r.id, 'APPROVED')}
                      disabled={isProcessing}
                      className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50"
                    >
                      {isProcessing ? '...' : '✅ Одобрить'}
                    </button>
                    <button
                      onClick={() => handleDecision(r.id, 'REJECTED')}
                      disabled={isProcessing}
                      className="px-4 py-2 bg-red-50 text-red-600 text-sm font-medium rounded-lg hover:bg-red-100 disabled:opacity-50"
                    >
                      ❌ Отклонить
                    </button>
                  </div>
                )}

                {r.status === 'APPROVED' && r.assigned_role_label && (
                  <div className="mt-3 text-sm text-gray-500">
                    Роль: <span className="font-medium text-gray-700">{r.assigned_role_label}</span>
                    {r.reviewed_at && <span className="ml-2">• {formatDateTime(r.reviewed_at)}</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
