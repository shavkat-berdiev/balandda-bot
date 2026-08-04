import { useSearchParams } from 'react-router-dom';

/**
 * URL-synced tab bar for "hub" pages that merge several former sidebar entries
 * into one screen. The active tab lives in ?tab=<key> so links and browser
 * back/forward keep working (e.g. /admin/users?tab=staff).
 *
 * Usage:
 *   <Tabs tabs={[{ key: 'users', label: 'Пользователи', icon: Users, render: () => <Users /> }]} />
 *
 * Each child page still renders its own <h1> heading, so nothing inside the
 * existing page components had to change.
 */
export default function Tabs({ tabs, param = 'tab' }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get(param);
  const active = tabs.find((t) => t.key === requested) || tabs[0];

  function select(key) {
    const next = new URLSearchParams(searchParams);
    if (key === tabs[0].key) next.delete(param);
    else next.set(param, key);
    setSearchParams(next, { replace: false });
  }

  return (
    <div>
      <div className="mb-6 border-b border-gray-200">
        <nav className="-mb-px flex gap-1 overflow-x-auto">
          {tabs.map(({ key, label, icon: Icon }) => {
            const isActive = key === active.key;
            return (
              <button
                key={key}
                onClick={() => select(key)}
                className={`flex items-center gap-2 whitespace-nowrap px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  isActive
                    ? 'border-blue-600 text-blue-700'
                    : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-300'
                }`}
              >
                {Icon && <Icon size={16} />}
                {label}
              </button>
            );
          })}
        </nav>
      </div>

      <div>{active.render()}</div>
    </div>
  );
}
