import { useState, useEffect } from 'react';
import { Plus, Pencil, Check, X, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../api';

const EMPTY_FORM = { name_ru: '', name_uz: '', price: 0, sort_order: 0 };

export default function AdminMinibar() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try { setItems(await api.getAdminMinibar()); } catch (err) { setError(err.message); }
    setLoading(false);
  }

  function startEdit(item) {
    setEditId(item.id);
    setForm({ name_ru: item.name_ru, name_uz: item.name_uz, price: item.price, sort_order: item.sort_order });
    setShowForm(true);
    setError('');
  }

  async function handleSave() {
    try {
      setError('');
      const payload = { ...form, price: parseFloat(form.price), sort_order: parseInt(form.sort_order) };
      if (editId) { await api.updateAdminMinibar(editId, payload); } else { await api.createAdminMinibar(payload); }
      setShowForm(false);
      load();
    } catch (err) { setError(err.message); }
  }

  async function toggleActive(item) {
    try { await api.updateAdminMinibar(item.id, { is_active: !item.is_active }); load(); } catch (err) { setError(err.message); }
  }

  const fmt = (n) => Number(n).toLocaleString('ru-RU');

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Минибар</h1>
          <p className="text-gray-500 text-sm mt-1">Напитки и закуски из минибара</p>
        </div>
        <button onClick={() => { setEditId(null); setForm(EMPTY_FORM); setShowForm(true); setError(''); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
          <Plus size={18} /> Добавить
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">{editId ? 'Редактировать' : 'Новый товар'}</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (RU)</label>
              <input type="text" value={form.name_ru} onChange={(e) => setForm({ ...form, name_ru: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Кока-Кола" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (UZ)</label>
              <input type="text" value={form.name_uz} onChange={(e) => setForm({ ...form, name_uz: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Coca-Cola" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Цена</label>
              <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })}
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Товар</th>
                  <th className="px-4 py-3 text-right">Цена</th>
                  <th className="px-4 py-3 text-center">Статус</th>
                  <th className="px-4 py-3 text-center">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map(item => (
                  <tr key={item.id} className={!item.is_active ? 'opacity-50 bg-gray-50' : 'hover:bg-gray-50'}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{item.name_ru}</p>
                      <p className="text-xs text-gray-500">{item.name_uz}</p>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-800">{fmt(item.price)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${item.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                        {item.is_active ? 'Активен' : 'Выкл'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        <button onClick={() => startEdit(item)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50"><Pencil size={16} /></button>
                        <button onClick={() => toggleActive(item)} className={`p-1.5 rounded-lg ${item.is_active ? 'text-green-600 hover:bg-green-50' : 'text-gray-400 hover:bg-gray-100'}`}>
                          {item.is_active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
