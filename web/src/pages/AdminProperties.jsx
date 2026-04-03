import { useState, useEffect } from 'react';
import { Plus, Pencil, Check, X, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../api';

const EMPTY_FORM = {
  code: '', name_ru: '', name_uz: '', property_type: '', unit_number: '',
  capacity: 2, has_sauna: false, price_weekday: 0, price_weekend: 0,
  emoji: '🏠', sort_order: 0, business_unit: 'RESORT',
};

export default function AdminProperties() {
  const [items, setItems] = useState([]);
  const [enums, setEnums] = useState({ property_types: [], business_units: [] });
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');

  useEffect(() => {
    load();
    api.getAdminEnums().then(setEnums).catch(() => {});
  }, []);

  async function load() {
    setLoading(true);
    try {
      setItems(await api.getAdminProperties());
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  function startEdit(item) {
    setEditId(item.id);
    setForm({
      code: item.code,
      name_ru: item.name_ru,
      name_uz: item.name_uz,
      property_type: item.property_type,
      unit_number: item.unit_number || '',
      capacity: item.capacity,
      has_sauna: item.has_sauna,
      price_weekday: item.price_weekday,
      price_weekend: item.price_weekend,
      emoji: item.emoji,
      sort_order: item.sort_order,
      business_unit: item.business_unit,
    });
    setShowForm(true);
    setError('');
  }

  function startCreate() {
    setEditId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
    setError('');
  }

  async function handleSave() {
    try {
      setError('');
      const payload = {
        ...form,
        capacity: parseInt(form.capacity),
        price_weekday: parseFloat(form.price_weekday),
        price_weekend: parseFloat(form.price_weekend),
        sort_order: parseInt(form.sort_order),
      };
      if (editId) {
        await api.updateAdminProperty(editId, payload);
      } else {
        await api.createAdminProperty(payload);
      }
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleActive(item) {
    try {
      await api.updateAdminProperty(item.id, { is_active: !item.is_active });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const fmt = (n) => Number(n).toLocaleString('ru-RU');

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Объекты размещения</h1>
          <p className="text-gray-500 text-sm mt-1">Домики, апартаменты, виллы — всё, что отображается в боте</p>
        </div>
        <button onClick={startCreate} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          <Plus size={18} /> Добавить
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            {editId ? 'Редактировать объект' : 'Новый объект'}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Код</label>
              <input type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="H-GL1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (RU)</label>
              <input type="text" value={form.name_ru} onChange={(e) => setForm({ ...form, name_ru: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Домик №1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Название (UZ)</label>
              <input type="text" value={form.name_uz} onChange={(e) => setForm({ ...form, name_uz: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="Uycha №1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Тип</label>
              <select value={form.property_type} onChange={(e) => setForm({ ...form, property_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm">
                <option value="">-- Выберите --</option>
                {enums.property_types.map(pt => <option key={pt.value} value={pt.value}>{pt.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Номер</label>
              <input type="text" value={form.unit_number} onChange={(e) => setForm({ ...form, unit_number: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Вместимость</label>
              <input type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Цена будни</label>
              <input type="number" value={form.price_weekday} onChange={(e) => setForm({ ...form, price_weekday: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Цена выходные</label>
              <input type="number" value={form.price_weekend} onChange={(e) => setForm({ ...form, price_weekend: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Эмодзи</label>
              <input type="text" value={form.emoji} onChange={(e) => setForm({ ...form, emoji: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Порядок</label>
              <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
            </div>
            <div className="flex items-end gap-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input type="checkbox" checked={form.has_sauna} onChange={(e) => setForm({ ...form, has_sauna: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-blue-600" />
                Сауна
              </label>
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
                  <th className="px-4 py-3 text-left">Объект</th>
                  <th className="px-4 py-3 text-left">Тип</th>
                  <th className="px-4 py-3 text-right">Будни</th>
                  <th className="px-4 py-3 text-right">Выходные</th>
                  <th className="px-4 py-3 text-center">Вмест.</th>
                  <th className="px-4 py-3 text-center">Статус</th>
                  <th className="px-4 py-3 text-center">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map(item => (
                  <tr key={item.id} className={!item.is_active ? 'opacity-50 bg-gray-50' : 'hover:bg-gray-50'}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{item.emoji}</span>
                        <div>
                          <p className="font-medium text-gray-800">{item.name_ru}</p>
                          <p className="text-xs text-gray-500">{item.code}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{item.property_type_label}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-800">{fmt(item.price_weekday)}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-800">{fmt(item.price_weekend)}</td>
                    <td className="px-4 py-3 text-center text-gray-600">{item.capacity}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${item.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                        {item.is_active ? 'Активен' : 'Выкл'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        <button onClick={() => startEdit(item)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-lg hover:bg-blue-50" title="Редактировать">
                          <Pencil size={16} />
                        </button>
                        <button onClick={() => toggleActive(item)} className={`p-1.5 rounded-lg ${item.is_active ? 'text-green-600 hover:bg-green-50' : 'text-gray-400 hover:bg-gray-100'}`} title={item.is_active ? 'Деактивировать' : 'Активировать'}>
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
