import { useState, useEffect } from 'react';
import { Plus, UserCheck, UserX, Check, X } from 'lucide-react';
import { api } from '../api';

const ROLES = [
  { value: 'ADMIN', label: 'Администратор' },
  { value: 'RESORT_MANAGER', label: 'Менеджер курорта' },
  { value: 'RESTAURANT_MANAGER', label: 'Менеджер ресторана' },
];

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ telegram_id: '', full_name: '', role: 'RESORT_MANAGER' });
  const [error, setError] = useState('');

  useEffect(() => { loadUsers(); }, []);

  async function loadUsers() {
    setLoading(true);
    try {
      const data = await api.getUsers();
      setUsers(data);
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  async function handleCreate() {
    try {
      setError('');
      await api.createUser({
        telegram_id: parseInt(form.telegram_id),
        full_name: form.full_name,
        role: form.role,
      });
      setShowForm(false);
      setForm({ telegram_id: '', full_name: '', role: 'RESORT_MANAGER' });
      loadUsers();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleActive(user) {
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      loadUsers();
    } catch (err) {
      setError(err.message);
    }
  }

  async function changeRole(userId, newRole) {
    try {
      await api.updateUser(userId, { role: newRole });
      loadUsers();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Users</h1>
          <p className="text-gray-500 text-sm mt-1">Manage bot users and their roles</p>
        </div>
        <button
          onClick={() => { setShowForm(true); setError(''); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Plus size={18} /> Add Manager
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {/* Add user form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Add New Manager</h2>
          <p className="text-sm text-gray-500 mb-4">
            The user must know their Telegram ID. They can get it by messaging @userinfobot on Telegram.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Telegram ID</label>
              <input
                type="text"
                value={form.telegram_id}
                onChange={(e) => setForm({ ...form, telegram_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="123456789"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Aziz Karimov"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              >
                {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={handleCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
              <Check size={16} /> Add User
            </button>
            <button onClick={() => setShowForm(false)} className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
              <X size={16} /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Users list */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? (
          <div className="col-span-full flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : users.length === 0 ? (
          <div className="col-span-full text-center py-12 text-gray-400">No users found</div>
        ) : (
          users.map(user => (
            <div
              key={user.id}
              className={`bg-white rounded-xl border border-gray-200 p-5 ${!user.is_active ? 'opacity-50' : ''}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
                    {user.full_name?.charAt(0) || '?'}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-800">{user.full_name}</p>
                    <p className="text-xs text-gray-500">ID: {user.telegram_id}</p>
                  </div>
                </div>
                <button
                  onClick={() => toggleActive(user)}
                  className={`p-1.5 rounded-lg ${
                    user.is_active
                      ? 'text-green-600 hover:bg-green-50'
                      : 'text-gray-400 hover:bg-gray-50'
                  }`}
                  title={user.is_active ? 'Deactivate' : 'Activate'}
                >
                  {user.is_active ? <UserCheck size={18} /> : <UserX size={18} />}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={user.role}
                  onChange={(e) => changeRole(user.id, e.target.value)}
                  className="flex-1 px-2 py-1.5 border border-gray-200 rounded-lg text-xs bg-gray-50"
                >
                  {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                  user.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
                }`}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              {user.created_at && (
                <p className="text-xs text-gray-400 mt-3">
                  Added: {new Date(user.created_at).toLocaleDateString('ru-RU')}
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
