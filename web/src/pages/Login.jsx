import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

export default function Login({ onLogin }) {
  const widgetRef = useRef(null);
  const [error, setError] = useState('');
  const [devMode, setDevMode] = useState(false);
  const [devTelegramId, setDevTelegramId] = useState('');
  const [registerBot, setRegisterBot] = useState('berdiev_shavkat_bot');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');

  const handlePasswordLogin = async (e) => {
    e.preventDefault();
    try {
      setError('');
      const result = await api.passwordLogin({ login, password });
      onLogin(result.user, result.token);
    } catch (err) {
      setError(err.message || 'Ошибка входа');
    }
  };

  useEffect(() => {
    let cancelled = false;

    // Global callback for Telegram widget
    window.onTelegramAuth = async (user) => {
      try {
        setError('');
        const result = await api.telegramLogin(user);
        onLogin(result.user, result.token);
      } catch (err) {
        const notReg = /not registered/i.test(err.message || '');
        setError(notReg ? 'Вы ещё не зарегистрированы. Нажмите «Запросить доступ» ниже.' : err.message);
      }
    };

    // Ask the server which Login Widget bot to use for this domain
    // (calendar.balandda.uz uses the front-office bot), then mount the widget.
    (async () => {
      let botLogin = 'berdiev_shavkat_bot';
      try {
        const res = await fetch('/api/v1/public/login-config');
        if (res.ok) {
          const d = await res.json();
          if (d && d.bot_login) botLogin = d.bot_login;
        if (d && d.register_bot) setRegisterBot(d.register_bot);
        }
      } catch { /* fall back to default bot */ }
      if (cancelled || !widgetRef.current || widgetRef.current.hasChildNodes()) return;
      const script = document.createElement('script');
      script.src = 'https://telegram.org/js/telegram-widget.js?22';
      script.setAttribute('data-telegram-login', botLogin);
      script.setAttribute('data-size', 'large');
      script.setAttribute('data-radius', '8');
      script.setAttribute('data-onauth', 'onTelegramAuth(user)');
      script.setAttribute('data-request-access', 'write');
      script.async = true;
      widgetRef.current.appendChild(script);
    })();

    return () => {
      cancelled = true;
      delete window.onTelegramAuth;
    };
  }, [onLogin]);

  // Dev mode login (for local testing without Telegram widget)
  const handleDevLogin = async () => {
    try {
      setError('');
      // Direct token creation for development
      const res = await fetch('/api/v1/auth/dev-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: parseInt(devTelegramId) }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Login failed');
      }
      const result = await res.json();
      onLogin(result.user, result.token);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-xl p-8 w-full max-w-md text-center">
        {/* Logo */}
        <div className="mb-6">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl font-bold text-white">B</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-800">Balandda Analytics</h1>
          <p className="text-gray-500 mt-1">Sign in to access the dashboard</p>
        </div>

        {/* Username / password login (browser can save it) */}
        <form onSubmit={handlePasswordLogin} className="space-y-3 text-left" autoComplete="on">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Логин</label>
            <input name="username" autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="логин" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Пароль</label>
            <input name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="пароль" />
          </div>
          <button type="submit" className="w-full py-2.5 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700">Войти</button>
        </form>

        <div className="flex items-center gap-3 my-5 text-xs text-gray-400">
          <div className="flex-1 h-px bg-gray-200" />или<div className="flex-1 h-px bg-gray-200" />
        </div>

        {/* Telegram Widget */}
        <div className="flex justify-center mb-2" ref={widgetRef}></div>

        {error && (
          <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mt-4">
            {error}
          </div>
        )}

        <div className="mt-6">
          <p className="text-xs text-gray-400">Нет доступа? Отправьте заявку — администратор подтвердит, и вы сможете войти.</p>
          <a
            href={`https://t.me/${registerBot}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-2 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            📩 Запросить доступ
          </a>
        </div>

        {/* Dev mode toggle (only for localhost) */}
        {window.location.hostname === 'localhost' && (
          <div className="mt-6 pt-4 border-t border-gray-100">
            <button
              onClick={() => setDevMode(!devMode)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              {devMode ? 'Hide' : 'Dev mode'}
            </button>
            {devMode && (
              <div className="mt-3 flex gap-2">
                <input
                  type="text"
                  placeholder="Telegram User ID"
                  value={devTelegramId}
                  onChange={(e) => setDevTelegramId(e.target.value)}
                  className="flex-1 px-3 py-2 border rounded-lg text-sm"
                />
                <button
                  onClick={handleDevLogin}
                  className="px-4 py-2 bg-gray-800 text-white rounded-lg text-sm"
                >
                  Login
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
