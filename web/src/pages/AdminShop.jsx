import { useState, useEffect } from 'react';
import { Wine, ShoppingCart, Wallet, Check } from 'lucide-react';
import Tabs from '../components/Tabs';
import AdminMinibar from './AdminMinibar';
import { api } from '../api';

/**
 * Мини бар + Мини шоп in one screen — two shelves of the same catalog table.
 * Mini shop additionally pins its cash to one seller's wallet, configured below.
 */
export default function AdminShop() {
  return (
    <Tabs
      tabs={[
        { key: 'minibar', label: 'Мини бар', icon: Wine, render: () => <AdminMinibar section="MINIBAR" /> },
        {
          key: 'minishop',
          label: 'Мини шоп',
          icon: ShoppingCart,
          render: () => (
            <div>
              <MinishopSeller />
              <AdminMinibar section="MINISHOP" />
            </div>
          ),
        },
      ]}
    />
  );
}

/**
 * Picks whose wallet receives Mini shop cash. The bot reads this on every sale
 * (app_settings.minishop_seller_telegram_id) and credits that wallet regardless
 * of who typed the sale in — so a stand-in cashier can't misroute the money.
 */
function MinishopSeller() {
  const [users, setUsers] = useState([]);
  const [seller, setSeller] = useState(null);
  const [choice, setChoice] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    // Settled independently: a failure on one endpoint must not blank the whole
    // card (and must not surface as an unhandled rejection).
    const [uRes, sRes] = await Promise.allSettled([api.getUsers(), api.getMinishopSeller()]);

    if (uRes.status === 'fulfilled' && Array.isArray(uRes.value)) {
      setUsers(uRes.value.filter((x) => x.is_active));
    }
    if (sRes.status === 'fulfilled' && sRes.value) {
      setSeller(sRes.value);
      setChoice(sRes.value.telegram_id ? String(sRes.value.telegram_id) : '');
    }

    const failed = [uRes, sRes].find((r) => r.status === 'rejected');
    if (failed) setError(failed.reason?.message || 'Не удалось загрузить настройки');
  }

  async function save() {
    setSaving(true);
    setError('');
    try {
      const next = await api.setMinishopSeller(choice ? parseInt(choice, 10) : null);
      setSeller(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message);
    }
    setSaving(false);
  }

  const dirty = String(seller?.telegram_id ?? '') !== String(choice ?? '');

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-6">
      <div className="flex items-start gap-3">
        <Wallet size={20} className="text-amber-600 mt-0.5 shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-amber-900">Кошелёк мини-шопа</p>
          <p className="text-xs text-amber-700 mt-0.5">
            Продажи мини-шопа принимаются <strong>только наличными</strong> и всегда зачисляются
            в кошелёк выбранного продавца — даже если запись в бота внёс кто-то другой.
          </p>

          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-3">
            <select
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
              className="flex-1 px-3 py-2 border border-amber-300 rounded-lg text-sm bg-white"
            >
              <option value="">— не задан (деньги идут тому, кто внёс запись) —</option>
              {users.map((u) => (
                <option key={u.telegram_id} value={u.telegram_id}>
                  {u.full_name} · {u.telegram_id}
                </option>
              ))}
            </select>
            <button
              onClick={save}
              disabled={!dirty || saving}
              className="flex items-center justify-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Check size={16} /> {saving ? 'Сохраняю…' : 'Сохранить'}
            </button>
          </div>

          {saved && <p className="text-xs text-green-700 mt-2">✅ Продавец сохранён</p>}
          {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
          {!choice && !error && (
            <p className="text-xs text-amber-800 mt-2">
              ⚠️ Продавец не выбран — наличные будут попадать в кошелёк того, кто вносит продажу.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
