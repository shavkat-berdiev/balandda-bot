const API_BASE = '/api/v1';

function getToken() {
  return localStorage.getItem('token');
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });

  if (res.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
    return;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    let msg = err.detail || 'Request failed';
    if (typeof msg !== 'string') {
      msg = Array.isArray(msg) ? msg.map(e => e.msg || JSON.stringify(e)).join('; ') : JSON.stringify(msg);
    }
    throw new Error(msg);
  }

  return res.json();
}

export const api = {
  // Auth
  telegramLogin: (data) => request('/auth/telegram', { method: 'POST', body: JSON.stringify(data) }),

  // Transactions
  getTransactions: (params = '') => request(`/transactions/${params ? '?' + params : ''}`),

  // Reports
  getDailyReport: (unit, date) =>
    request(`/reports/daily?business_unit=${unit}${date ? '&report_date=' + date : ''}`),

  // Categories
  getCategories: (params = '') => request(`/categories/${params ? '?' + params : ''}`),
  createCategory: (data) => request('/categories/', { method: 'POST', body: JSON.stringify(data) }),
  updateCategory: (id, data) => request(`/categories/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCategory: (id) => request(`/categories/${id}`, { method: 'DELETE' }),

  // Users
  getUsers: () => request('/users/'),
  createUser: (data) => request('/users/', { method: 'POST', body: JSON.stringify(data) }),
  updateUser: (id, data) => request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Analytics Dashboard
  getDailyReports: (from, to) =>
    request(`/daily-reports/list?from_date=${from}&to_date=${to}`),
  getReportDetail: (id) =>
    request(`/daily-reports/detail/${id}`),
  getBreakdown: (from, to) =>
    request(`/daily-reports/breakdown?from_date=${from}&to_date=${to}`),
  getStructuredReports: (from, to) =>
    request(`/structured-reports/list?from_date=${from}&to_date=${to}`),
  getProperties: () =>
    request('/properties'),
  getHealth: () =>
    request('/health'),

  // Admin — Enums
  getAdminEnums: () => request('/admin/enums'),

  // Admin — Properties
  getAdminProperties: () => request('/admin/properties'),
  createAdminProperty: (data) => request('/admin/properties', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminProperty: (id, data) => request(`/admin/properties/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Services
  getAdminServices: () => request('/admin/services'),
  createAdminService: (data) => request('/admin/services', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminService: (id, data) => request(`/admin/services/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Minibar
  getAdminMinibar: () => request('/admin/minibar'),
  createAdminMinibar: (data) => request('/admin/minibar', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminMinibar: (id, data) => request(`/admin/minibar/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Staff
  getAdminStaff: () => request('/admin/staff'),
  createAdminStaff: (data) => request('/admin/staff', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminStaff: (id, data) => request(`/admin/staff/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Structured Reports (with date filter)
  getStructuredReportsList: (from, to) =>
    request(`/structured/list?start_date=${from}&end_date=${to}`),
  getStructuredReportDetail: (id) =>
    request(`/structured/detail/${id}`),

  // New structured endpoints
  getStructuredDashboard: (unit, from, to) => {
    const params = new URLSearchParams({ business_unit: unit });
    if (from) params.set('start_date', from);
    if (to) params.set('end_date', to);
    return request(`/structured/dashboard?${params}`);
  },
  getStructuredTransactions: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.business_unit) sp.set('business_unit', params.business_unit);
    if (params.entry_type) sp.set('entry_type', params.entry_type);
    if (params.start_date) sp.set('start_date', params.start_date);
    if (params.end_date) sp.set('end_date', params.end_date);
    if (params.limit) sp.set('limit', params.limit);
    return request(`/structured/transactions?${sp}`);
  },
  getStructuredBreakdown: (unit, from, to) => {
    const params = new URLSearchParams({ business_unit: unit });
    if (from) params.set('start_date', from);
    if (to) params.set('end_date', to);
    return request(`/structured/breakdown?${params}`);
  },
};
