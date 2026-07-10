import { useState, useEffect } from 'react';
import { Plus, Pencil, Check, X, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../api';

const EMPTY = { name_ru: '', name_uz: '', sort_order: 0 };

export default function AdminSpaLocations() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try { setItems(await api.getSpaLocations()); } catch (err) { setError(err.message); }
    setLoading(false);
  }

  function startEdit(it) {
    setEditId(it.id);
    setForm({ name_ru: it.name_ru, name_uz: it.name_uz, sort_order: it.sort_order });
    setShowForm(true); setError('');
  }

  async function handleSave() {
    try {
      setError('');
      const payload = { ...form, sort_order: parseInt(form.sort_order) || 0 };
      if (editId) await api.updateSpaLocation(editId, payload);
      else await api.createSpaLocation(payload);
      setShowForm(false); load();
    } catch (err) { setError(err.message); }
  }

  async function toggleActive(it) {
    try { await api.updateSpaLocation(it.id, { is_active: !it.is_active }); load(); } catch (err) { setError(err.message); }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">SPA кабинеты</h1>
          <p className="text-gray-500 text-sm mt-1">Хаммам, массажные и другие помещения (ограниченный ресурс)</p>
        </div>
        <button onClick={() => { setEditId(null); setForm(EMPTY); setShowForm(true); setError(''); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
          <Plus size={18} /> Добавить
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">{editId ? 'Редактировать' : 'Новый кабинет'}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (RU)</label>
              <input type="text" value={form.name_ru} onChange={(e) => setForm({ ...form, name_ru: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (UZ)</label>
              <input type="text" value={form.name_uz} onChange={(e) => setForm({ ...form, name_uz: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Порядок</label>
              <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
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
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Кабинет</th>
                <th className="px-4 py-3 text-center">Порядок</th>
                <th className="px-4 py-3 text-center">Статус</th>
                <th className="px-4 py-3 text-center">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map(it => (
                <tr key={it.id} className={!it.is_active ? 'opacity-50 bg-gray-50' : 'hover:bg-gray-50'}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-800">{it.name_ru}</p>
                    <p className="text-xs text-gray-500">{it.name_uz}</p>
                  </td>
                  <td className="px-4 py-3 text-center text-gray-600">{it.sort_order}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${it.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {it.is_active ? 'Активен' : 'Выкл'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-2">
                      <button onClick={() => startEdit(it)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50"><Pencil size={16} /></button>
                      <button onClick={() => toggleActive(it)} className={`p-1.5 rounded-lg ${it.is_active ? 'text-green-600 hover:bg-green-50' : 'text-gray-400 hover:bg-gray-100'}`}>
                        {it.is_active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
