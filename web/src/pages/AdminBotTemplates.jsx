import { useState, useEffect } from 'react';
import { Plus, Trash2, ChevronDown, ChevronRight, ImagePlus, X, ArrowUp, ArrowDown, Save, CornerDownRight, Download, Eye, EyeOff } from 'lucide-react';
import { api } from '../api';

const LANGS = [
  { code: 'ru', label: 'Русский' },
  { code: 'uz', label: "O'zbek" },
  { code: 'en', label: 'English' },
];

const ACTIONS = [
  { value: 'reply', label: 'Показать ответ' },
  { value: 'submenu', label: 'Открыть подменю' },
  { value: 'book', label: 'Начать бронирование' },
  { value: 'agent', label: 'Позвать оператора' },
  { value: 'lang', label: 'Сменить язык' },
];

const PRICE_BLOCKS = [
  { value: 'none', label: 'Без цен' },
  { value: 'houses', label: '+ Живые цены: дома' },
  { value: 'pool', label: '+ Живые цены: бассейн' },
  { value: 'spa', label: '+ Живые цены: SPA' },
];

const KW_HINT = {
  ru: 'шале, домик с сауной, коттедж',
  uz: 'shale, saunali uy, шале, коттедж',   // Uzbek customers often type in Cyrillic
  en: 'chalet, sauna house, cottage',
};

const FLD = 'w-full px-3 py-2 border border-gray-200 rounded-lg text-sm';
const LBL = 'block text-xs font-medium text-gray-600 mb-1';

const EMPTY = {
  parent_id: null, action: 'reply',
  label_ru: '', label_uz: '', label_en: '',
  ig_label_ru: '', ig_label_uz: '', ig_label_en: '',
  body_ru: '', body_uz: '', body_en: '',
  images: [], keywords_ru: '', keywords_uz: '', keywords_en: '',
  price_block: 'none', sort_order: 0, is_active: true,
};

export default function AdminBotTemplates() {
  const [items, setItems] = useState([]);
  const [lang, setLang] = useState('ru');
  const [open, setOpen] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [note, setNote] = useState('');

  useEffect(() => { load(); }, []);

  async function seed() {
    const has = items.length > 0;
    if (has && !confirm('Это удалит текущие кнопки и пересоздаст меню из Telegram-бота и каталога. Продолжить?')) return;
    setSeeding(true); setError(''); setNote('');
    try {
      const r = await api.seedBotTemplates(has);
      setNote(`Готово: создано ${r.created} кнопок, типов жилья — ${r.types}, импортировано текстов — ${r.texts_imported}.`);
      await load();
    } catch (e) { setError(e.message); }
    setSeeding(false);
  }

  async function load() {
    setLoading(true);
    try { setItems(await api.getBotTemplates()); setError(''); }
    catch (e) { setError(e.message); }
    setLoading(false);
  }

  const roots = items.filter(i => !i.parent_id).sort((a, b) => a.sort_order - b.sort_order);
  const kids = (id) => items.filter(i => i.parent_id === id).sort((a, b) => a.sort_order - b.sort_order);

  function patch(id, field, value) {
    setItems(items.map(i => (i.id === id ? { ...i, [field]: value } : i)));
  }

  async function save(item) {
    setSaving(item.id);
    try { await api.updateBotTemplate(item.id, item); setError(''); }
    catch (e) { setError(e.message); }
    setSaving(null);
  }

  async function add(parentId) {
    const siblings = parentId ? kids(parentId) : roots;
    try {
      const created = await api.createBotTemplate({
        ...EMPTY, parent_id: parentId, sort_order: siblings.length,
        label_ru: parentId ? 'Новый пункт' : 'Новая кнопка',
      });
      setItems([...items, created]);
      setOpen({ ...open, [created.id]: true });
    } catch (e) { setError(e.message); }
  }

  async function remove(item) {
    const n = kids(item.id).length;
    if (!confirm(`Удалить «${item.label_ru || 'без названия'}»${n ? ` и ${n} вложенных пункт(ов)` : ''}?`)) return;
    try {
      await api.deleteBotTemplate(item.id);
      setItems(items.filter(i => i.id !== item.id && i.parent_id !== item.id));
    } catch (e) { setError(e.message); }
  }

  // Instant show/hide — seasonal items disappear from both bots straight away.
  async function toggleActive(item) {
    const next = { ...item, is_active: !item.is_active };
    setItems(items.map(i => (i.id === item.id ? next : i)));
    try { await api.updateBotTemplate(item.id, next); setError(''); }
    catch (e) { setError(e.message); load(); }
  }

  // Move a button into a submenu (or back to the main menu).
  async function moveTo(item, parentValue) {
    const parent_id = parentValue === '' ? null : Number(parentValue);
    const siblings = parent_id ? kids(parent_id) : roots;
    const next = { ...item, parent_id, sort_order: siblings.length };
    setItems(items.map(i => (i.id === item.id ? next : i)));
    try { await api.updateBotTemplate(item.id, next); setError(''); }
    catch (e) { setError(e.message); load(); }   // reload on a rejected move (e.g. nesting too deep)
  }

  async function move(item, dir) {
    const list = item.parent_id ? kids(item.parent_id) : roots;
    const idx = list.findIndex(i => i.id === item.id);
    const swap = list[idx + dir];
    if (!swap) return;
    const a = { ...item, sort_order: swap.sort_order };
    const b = { ...swap, sort_order: item.sort_order };
    setItems(items.map(i => (i.id === a.id ? a : i.id === b.id ? b : i)));
    try { await api.updateBotTemplate(a.id, a); await api.updateBotTemplate(b.id, b); }
    catch (e) { setError(e.message); }
  }

  async function upload(item, file) {
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { url } = await api.uploadBotImage(fd);
      const next = { ...item, images: [...(item.images || []), url] };
      setItems(items.map(i => (i.id === item.id ? next : i)));
      await api.updateBotTemplate(item.id, next);
    } catch (e) { setError(e.message); }
  }

  async function dropImage(item, url) {
    const next = { ...item, images: (item.images || []).filter(u => u !== url) };
    setItems(items.map(i => (i.id === item.id ? next : i)));
    try { await api.updateBotTemplate(item.id, next); } catch (e) { setError(e.message); }
  }

  // Only top-level submenu items can hold children (the tree is capped at two levels).
  const menus = roots.filter(r => r.action === 'submenu');
  const ctx = { lang, open, setOpen, patch, save, saving, remove, move, upload, dropImage, kids, add, toggleActive, moveTo, menus };

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Ответы бота</h1>
          <p className="text-gray-500 text-sm mt-1">Один источник для Telegram и Instagram — что здесь, то и в обоих ботах.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {LANGS.map(l => (
              <button key={l.code} onClick={() => setLang(l.code)}
                className={`px-3 py-2 text-sm ${lang === l.code ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
                {l.label}
              </button>
            ))}
          </div>
          <button onClick={seed} disabled={seeding}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50">
            <Download size={17} /> {seeding ? 'Импорт…' : 'Импорт из Telegram-бота'}
          </button>
          <button onClick={() => add(null)} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            <Plus size={18} /> Кнопка
          </button>
        </div>
      </div>

      {error && <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>}
      {note && <div className="bg-emerald-50 text-emerald-700 rounded-lg px-4 py-3 text-sm mb-4">{note}</div>}

      <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3 text-sm text-blue-900 mb-5">
        Заполняйте по одному языку за раз — переключатель справа сверху. Instagram обрезает кнопки до 20 знаков,
        поэтому для длинных названий задайте короткий вариант. Цены не вписывайте руками — выберите «живые цены».
        Изменения сохраняются кнопкой «Сохранить» в каждом блоке.
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
      ) : roots.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-500">
          Пока нет кнопок. Нажмите «Импорт из Telegram-бота», чтобы создать меню автоматически.
        </div>
      ) : (
        roots.map(r => <Row key={r.id} item={r} depth={0} ctx={ctx} />)
      )}
    </div>
  );
}

/* Defined at module scope on purpose: if this lived inside the page component, React
   would treat it as a NEW component type on every keystroke, remount the row, and the
   input would lose focus after each character. */
function Row({ item, depth, ctx }) {
    const { lang, open, setOpen, patch, save, saving, remove, move, upload, dropImage, kids, add,
            toggleActive, moveTo, menus } = ctx;
    const fld = FLD, lbl = LBL;
    const isOpen = !!open[item.id];
    const label = item[`label_${lang}`] || item.label_ru || '(без названия)';
    const igRaw = item[`ig_label_${lang}`] || '';
    const igShown = igRaw || label.slice(0, 20);
    const over = igShown.length > 20;

    return (
      <div className={depth ? 'ml-8' : ''}>
        <div className="bg-white border border-gray-200 rounded-xl mb-2 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2.5">
            <button onClick={() => setOpen({ ...open, [item.id]: !isOpen })} className="p-1 text-gray-400 hover:text-gray-700">
              {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
            {depth > 0 && <CornerDownRight size={14} className="text-gray-300" />}
            <span className={`flex-1 text-sm font-medium ${item.is_active ? 'text-gray-800' : 'text-gray-400 line-through'}`}>{label}</span>
            <span className="text-[11px] text-gray-400">{ACTIONS.find(a => a.value === item.action)?.label}</span>
            {(item.images?.length > 0) && <span className="text-[11px] text-gray-400">🖼 {item.images.length}</span>}
            <button onClick={() => toggleActive(item)} title={item.is_active ? 'Скрыть от клиентов' : 'Показать клиентам'}
              className={`p-1 ${item.is_active ? 'text-emerald-600 hover:text-emerald-800' : 'text-gray-300 hover:text-gray-500'}`}>
              {item.is_active ? <Eye size={15} /> : <EyeOff size={15} />}
            </button>
            <button onClick={() => move(item, -1)} className="p-1 text-gray-300 hover:text-gray-700"><ArrowUp size={14} /></button>
            <button onClick={() => move(item, 1)} className="p-1 text-gray-300 hover:text-gray-700"><ArrowDown size={14} /></button>
            <button onClick={() => remove(item)} className="p-1 text-gray-300 hover:text-red-600"><Trash2 size={14} /></button>
          </div>

          {isOpen && (
            <div className="border-t border-gray-100 p-4 bg-gray-50/50">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                <div>
                  <label className={lbl}>Текст кнопки ({lang.toUpperCase()})</label>
                  <input value={item[`label_${lang}`] || ''} onChange={e => patch(item.id, `label_${lang}`, e.target.value)} className={fld} />
                </div>
                <div>
                  <label className={lbl}>
                    Короткая кнопка для Instagram{' '}
                    <span className={over ? 'text-red-600 font-bold' : 'text-gray-400'}>{igShown.length}/20</span>
                  </label>
                  <input value={igRaw} placeholder={label.slice(0, 20)} maxLength={20}
                    onChange={e => patch(item.id, `ig_label_${lang}`, e.target.value)} className={fld} />
                </div>
                <div>
                  <label className={lbl}>Что делает кнопка</label>
                  <select value={item.action} onChange={e => patch(item.id, 'action', e.target.value)} className={fld}>
                    {ACTIONS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </div>
              </div>

              <div className="mb-3">
                <label className={lbl}>Где находится кнопка</label>
                <select value={item.parent_id ?? ''} onChange={e => moveTo(item, e.target.value)} className={fld}>
                  <option value="">Главное меню (первый экран)</option>
                  {menus.filter(m => m.id !== item.id).map(m => (
                    <option key={m.id} value={m.id}>Внутри: {m[`label_${lang}`] || m.label_ru}</option>
                  ))}
                </select>
                <p className="text-[11px] text-gray-400 mt-1">
                  В главном меню держите 3 кнопки — остальное прячьте внутрь подменю. Вложенность — только один уровень.
                </p>
              </div>

              <div className="mb-3">
                <label className={lbl}>Ключевые слова ({lang.toUpperCase()}) — если клиент их напишет, бот пришлёт этот ответ</label>
                <input value={item[`keywords_${lang}`] || ''} onChange={e => patch(item.id, `keywords_${lang}`, e.target.value)}
                  className={fld} placeholder={KW_HINT[lang]} />
                <p className="text-[11px] text-gray-400 mt-1">
                  Через запятую. <b>Свой список для каждого языка</b> — по нему бот и определяет язык клиента.
                  Узбекские клиенты часто пишут кириллицей, поэтому вписывайте такие варианты в узбекский список
                  (например: <i>шале, шоле</i>).
                </p>
              </div>

              {(item.action === 'reply' || item.action === 'book') && (
                <>
                  <label className={lbl}>Текст ответа ({lang.toUpperCase()})</label>
                  <textarea rows={5} value={item[`body_${lang}`] || ''} onChange={e => patch(item.id, `body_${lang}`, e.target.value)}
                    className={`${fld} mb-3`} placeholder="Что бот отправит клиенту…" />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className={lbl}>Живые цены (подставятся автоматически)</label>
                      <select value={item.price_block} onChange={e => patch(item.id, 'price_block', e.target.value)} className={fld}>
                        {PRICE_BLOCKS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                      </select>
                      <p className="text-[11px] text-gray-400 mt-1">Цены берутся из каталога — не нужно править вручную.</p>
                    </div>
                    <div>
                      <label className={lbl}>Фото (отправляются с ответом)</label>
                      {(item.images || []).length === 0 && (
                        <p className="text-[11px] text-gray-500 mb-1">
                          Пусто → бот берёт галерею с сайта balandda.uz (раздел этого дома).
                          Загрузите фото здесь, только если хотите <b>переопределить</b> сайт.
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        {(item.images || []).map(u => (
                          <div key={u} className="relative">
                            <img src={u} alt="" className="w-16 h-16 object-cover rounded-lg border border-gray-200" />
                            <button onClick={() => dropImage(item, u)}
                              className="absolute -top-1.5 -right-1.5 bg-white border border-gray-200 rounded-full p-0.5 text-gray-500 hover:text-red-600">
                              <X size={12} />
                            </button>
                          </div>
                        ))}
                        <label className="w-16 h-16 border-2 border-dashed border-gray-200 rounded-lg flex items-center justify-center text-gray-400 hover:border-blue-400 hover:text-blue-500 cursor-pointer">
                          <ImagePlus size={18} />
                          <input type="file" accept="image/*" hidden
                            onChange={e => { if (e.target.files?.[0]) upload(item, e.target.files[0]); e.target.value = ''; }} />
                        </label>
                      </div>
                    </div>
                  </div>
                </>
              )}

              <div className="flex items-center gap-3">
                <button onClick={() => save(item)} disabled={saving === item.id}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
                  <Save size={15} /> {saving === item.id ? 'Сохранение…' : 'Сохранить'}
                </button>
                <span className="text-xs text-gray-400">
                  {item.is_active ? 'Показывается клиентам' : 'Скрыта от клиентов'} — переключается 👁 в строке
                </span>
                {item.action === 'submenu' && (
                  <button onClick={() => add(item.id)} className="ml-auto flex items-center gap-1.5 px-3 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">
                    <Plus size={15} /> Пункт подменю
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        {kids(item.id).map(k => <Row key={k.id} item={k} depth={depth + 1} ctx={ctx} />)}
      </div>
    );
}
