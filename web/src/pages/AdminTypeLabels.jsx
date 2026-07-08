import { useState, useEffect } from 'react';
import { Check } from 'lucide-react';
import { api } from '../api';

export default function AdminTypeLabels() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingType, setSavingType] = useState(null);
  const [savedType, setSavedType] = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      setRows(await api.getTypeLabels());
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  }

  function setField(type, field, value) {
    setRows((rs) => rs.map((r) => (r.property_type === type ? { ...r, [field]: value } : r)));
  }

  async function save(row) {
    setSavingType(row.property_type);
    setError('');
    try {
      await api.updateTypeLabel(row.property_type, {
        label_ru: row.label_ru, label_uz: row.label_uz, label_en: row.label_en || '',
      });
      setSavedType(row.property_type);
      setTimeout(() => setSavedType(null), 1800);
    } catch (err) {
      setError(err.message);
    }
    setSavingType(null);
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Названия типов размещения</h1>
        <p className="text-gray-500 text-sm mt-1">
          Названия категорий, которые видят клиенты в боте и на сайте (booking-форма и страницы домов).
          Меняются здесь один раз — обновляются везде.
        </p>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Тип (код)</th>
                  <th className="px-4 py-3 text-left">Русский</th>
                  <th className="px-4 py-3 text-left">O‘zbekcha</th>
                  <th className="px-4 py-3 text-left">English</th>
                  <th className="px-4 py-3 text-center">Действие</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row) => (
                  <tr key={row.property_type} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-xs text-gray-400 font-mono">{row.property_type}</td>
                    <td className="px-3 py-2">
                      <input value={row.label_ru} onChange={(e) => setField(row.property_type, 'label_ru', e.target.value)}
                        className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-sm" />
                    </td>
                    <td className="px-3 py-2">
                      <input value={row.label_uz} onChange={(e) => setField(row.property_type, 'label_uz', e.target.value)}
                        className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-sm" />
                    </td>
                    <td className="px-3 py-2">
                      <input value={row.label_en || ''} onChange={(e) => setField(row.property_type, 'label_en', e.target.value)}
                        className="w-full px-2 py-1.5 border border-gray-200 rounded-lg text-sm" />
                    </td>
                    <td className="px-4 py-2 text-center">
                      <button onClick={() => save(row)} disabled={savingType === row.property_type}
                        className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium ${savedType === row.property_type ? 'bg-green-100 text-green-700' : 'bg-blue-600 text-white hover:bg-blue-700'}`}>
                        <Check size={15} /> {savedType === row.property_type ? 'Сохранено' : (savingType === row.property_type ? '…' : 'Сохранить')}
                      </button>
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
