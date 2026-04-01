import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

export default function Login({ onLogin }) {
  const widgetRef = useRef(null);
  const [error, setError] = useState('');
  const [devMode, setDevMode] = useState(false);
  const [devTelegramId, setDevTelegramId] = useState('');

  useEffect(() => {
    // Load Telegram Login Widget script
    if (widgetRef.current && !widgetRef.current.hasChildNodes()) {
      const script = document.createElement('script');
      script.src = 'https://telegram.org/js/telegram-widget.js?22';
      script.setAttribute('data-telegram-login', 'berdiev_shavkat_bot');
      script.setAttribute('data-size', 'large');
      script.setAttribute('data-radius', '8');
      script.setAttribute('data-onauth', 'onTelegramAuth(user)');
      script.setAttribute('data-request-access', 'write');
      script.async = true;
      widgetRef.current.appendChild(script);
    }

    // Global callback for Telegram widget
    window.onTelegramAuth = async (user) => {
      try {
        setError('');
        const result = await api.telegramLogin(user);
        onLogin(result.user, result.token);
      } catch (err) {
        setError(err.message);
      }
    };

    return () => {
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

        {/* Telegram Widget */}
        <div className="flex justify-center my-8" ref={widgetRef}></div>

        {error && (
          <div className="bg-red-50 text-red-600 rounded-lg px-4 py-3 text-sm mt-4">
            {error}
          </div>
        )}

        <p className="text-xs text-gray-400 mt-6">
          You must be registered in the Telegram bot first
        </p>

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
