import { useState, useEffect } from 'react';
import { Plus, Pencil, Check, X, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../api';

const EMPTY_FORM = { name: '', role_description: '' };

export default function AdminStaff() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try { setItems(await api.getAdminStaff()); } catch (err) { setError(err.message); }
    setLoading(false);
  }

  function startEdit(item) {
    setEditId(item.id);
    setForm({ name: item.name, role_description: item.role_description || '' });
    setShowForm(true);
    setError('');
  }

  async function handleSave() {
    try {
      setError('');
      if (editId) { await api.updateAdminStaff(editId, form); } else { await api.createAdminStaff(form); }
      setShowForm(false);
      load();
    } catch (err) { setError(err.message); }
  }

  async function toggleActive(item) {
    try { await api.updateAdminStaff(item.id, { is_active: !item.is_active }); load(); } catch (err) { setError(err.message); }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Сотрудники</h1>
          <p className="text-gray-500 text-sm mt-1">Персонал курорта для привязки расходов</p>
        </div>
        <button onClick={() => { setEditId(null); setForm(EMPTY_FORM); setShowForm(true); setError(''); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
          <Plus size={18} /> Добавить
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">{editId ? 'Редактировать' : 'Новый сотрудник'}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ФИО</label>
              <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Иванов Иван" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Должность</label>
              <input type="text" value={form.role_description} onChange={(e) => setForm({ ...form, role_description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Администратор" />
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={handleSave} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
              <Check size={16} /> {editId ? 'Сохранить' : 'Создать'}
            </button>
            <button onClick={() => setShowForm(false)} className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
              <X size={16} /> Отмена
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.length === 0 ? (
            <div className="col-span-full text-center py-12 text-gray-400">Сотрудники не найдены</div>
          ) : items.map(item => (
            <div key={item.id} className={`bg-white rounded-xl border border-gray-200 p-5 ${!item.is_active ? 'opacity-50' : ''}`}>
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
                    {item.name?.charAt(0) || '?'}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-800">{item.name}</p>
                    <p className="text-xs text-gray-500">{item.role_description || 'Не указана'}</p>
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3">
                <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${item.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                  {item.is_active ? 'Активен' : 'Выкл'}
                </span>
                <div className="flex gap-1">
                  <button onClick={() => startEdit(item)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50"><Pencil size={16} /></button>
                  <button onClick={() => toggleActive(item)} className={`p-1.5 rounded-lg ${item.is_active ? 'text-green-600 hover:bg-green-50' : 'text-gray-400 hover:bg-gray-100'}`}>
                    {item.is_active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
