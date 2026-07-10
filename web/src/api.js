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

// Multipart upload (no JSON Content-Type — browser sets the boundary).
async function upload(path, formData) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    credentials: 'include',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Upload failed');
  }
  return res.json();
}

// Fetch an auth-protected image and return an object URL (for <img src>).
async function blobUrl(path) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: 'include',
  });
  if (!res.ok) throw new Error('image failed');
  return URL.createObjectURL(await res.blob());
}

export const api = {
  // Auth
  telegramLogin: (data) => request('/auth/telegram', { method: 'POST', body: JSON.stringify(data) }),
  passwordLogin: (data) => request('/auth/password', { method: 'POST', body: JSON.stringify(data) }),

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
  setUserCredentials: (id, data) => request(`/users/${id}/credentials`, { method: 'PUT', body: JSON.stringify(data) }),

  // Analytics Dashboard
  getDailyReports: (from, to) =>
    request(`/daily-reports/list?start_date=${from}&end_date=${to}`),
  getReportDetail: (id) =>
    request(`/daily-reports/detail/${id}`),
  getBreakdown: (from, to) =>
    request(`/daily-reports/breakdown?start_date=${from}&end_date=${to}`),
  getStructuredReports: (from, to) =>
    request(`/structured-reports/list?start_date=${from}&end_date=${to}`),
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

  // Prepayments — add from a booking (with screenshot) + view screenshot
  prepaymentsByReservation: (rid) => request(`/prepayments/by-reservation/${rid}`),
  addPrepaymentFromReservation: (formData) => upload('/prepayments/from-reservation', formData),
  prepaymentScreenshotUrl: (id) => blobUrl(`/prepayments/screenshot-image/${id}`),

  // Admin — Type labels (editable category titles per language)
  getTypeLabels: () => request('/admin/type-labels'),
  updateTypeLabel: (type, data) => request(`/admin/type-labels/${type}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Services
  getAdminServices: () => request('/admin/services'),
  createAdminService: (data) => request('/admin/services', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminService: (id, data) => request(`/admin/services/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — SPA categories
  getServiceCategories: () => request('/admin/service-categories'),
  createServiceCategory: (data) => request('/admin/service-categories', { method: 'POST', body: JSON.stringify(data) }),
  updateServiceCategory: (id, data) => request(`/admin/service-categories/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — SPA locations (rooms)
  getSpaLocations: () => request('/admin/spa-locations'),
  createSpaLocation: (data) => request('/admin/spa-locations', { method: 'POST', body: JSON.stringify(data) }),
  updateSpaLocation: (id, data) => request(`/admin/spa-locations/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — SPA masters
  getSpaMasters: () => request('/admin/spa-masters'),
  createSpaMaster: (data) => request('/admin/spa-masters', { method: 'POST', body: JSON.stringify(data) }),
  updateSpaMaster: (id, data) => request(`/admin/spa-masters/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Minibar
  getAdminMinibar: () => request('/admin/minibar'),
  createAdminMinibar: (data) => request('/admin/minibar', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminMinibar: (id, data) => request(`/admin/minibar/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Admin — Staff
  getAdminStaff: () => request('/admin/staff'),
  createAdminStaff: (data) => request('/admin/staff', { method: 'POST', body: JSON.stringify(data) }),
  updateAdminStaff: (id, data) => request(`/admin/staff/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Structured Reports (with date filter)
  getStructuredReportsList: (from, to, unit) => {
    const sp = new URLSearchParams();
    if (from) sp.set('start_date', from);
    if (to) sp.set('end_date', to);
    if (unit) sp.set('business_unit', unit);
    return request(`/structured/list?${sp}`);
  },
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
  // Report editing (owner only)
  updateReport: (id, data) => request(`/structured/report/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  updateIncomeEntry: (id, data) => request(`/structured/income-entry/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  updateExpenseEntry: (id, data) => request(`/structured/expense-entry/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteIncomeEntry: (id) => request(`/structured/income-entry/${id}`, { method: 'DELETE' }),
  deleteExpenseEntry: (id) => request(`/structured/expense-entry/${id}`, { method: 'DELETE' }),

  getStructuredBreakdown: (unit, from, to) => {
    const params = new URLSearchParams({ business_unit: unit });
    if (from) params.set('start_date', from);
    if (to) params.set('end_date', to);
    return request(`/structured/breakdown?${params}`);
  },

  // Prepayments
  getPrepaymentsList: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.start_date) sp.set('start_date', params.start_date);
    if (params.end_date) sp.set('end_date', params.end_date);
    if (params.status) sp.set('status', params.status);
    return request(`/prepayments/list?${sp}`);
  },
  getPrepaymentDetail: (id) => request(`/prepayments/detail/${id}`),
  updatePrepaymentStatus: (id, status) =>
    request(`/prepayments/status/${id}`, { method: 'PUT', body: JSON.stringify({ status }) }),
  getPrepaymentCalendar: (from, to) => {
    const sp = new URLSearchParams();
    if (from) sp.set('start_date', from);
    if (to) sp.set('end_date', to);
    return request(`/prepayments/calendar?${sp}`);
  },

  // Wallets
  getWalletsList: () => request('/wallets/list'),
  getWalletsTransactions: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.telegram_id) sp.set('telegram_id', params.telegram_id);
    if (params.transaction_type) sp.set('transaction_type', params.transaction_type);
    if (params.start_date) sp.set('start_date', params.start_date);
    if (params.end_date) sp.set('end_date', params.end_date);
    return request(`/wallets/transactions?${sp}`);
  },
  getWalletBalance: (telegramId) => request(`/wallets/balance/${telegramId}`),
  setWalletBalance: (telegram_id, balance) => request('/wallets/set-balance', { method: 'POST', body: JSON.stringify({ telegram_id, balance }) }),
  resetAllWallets: () => request('/wallets/reset-all', { method: 'POST' }),
  getCentralWallets: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.start_date) sp.set('start_date', params.start_date);
    if (params.end_date) sp.set('end_date', params.end_date);
    if (params.business_unit) sp.set('business_unit', params.business_unit);
    return request(`/wallets/central?${sp}`);
  },

  // Registration requests
  getRegistrationRequests: (params = {}) => {
    const sp = new URLSearchParams();
    if (params.status) sp.set('status', params.status);
    return request(`/registration/list?${sp}`);
  },
  getRegistrationRoles: () => request('/registration/roles'),
  decideRegistrationRequest: (id, data) =>
    request(`/registration/decide/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Reservations / availability calendar
  getReservations: (from, to) => request(`/reservations?from=${from}&to=${to}`),
  createReservation: (data) => request('/reservations', { method: 'POST', body: JSON.stringify(data) }),
  updateReservation: (id, data) => request(`/reservations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  cancelReservation: (id) => request(`/reservations/${id}/cancel`, { method: 'POST' }),
  extendHold: (id) => request(`/reservations/${id}/extend-hold`, { method: 'POST' }),
  connectLink: (id) => request(`/reservations/${id}/connect-link`, { method: 'POST' }),
  waivePrepayment: (id) => request(`/reservations/${id}/waive-prepayment`, { method: 'POST' }),
  restoreReservation: (id) => request(`/reservations/${id}/restore`, { method: 'POST' }),
  deleteReservation: (id) => request(`/reservations/${id}`, { method: 'DELETE' }),
  importPrepayments: () => request('/reservations/import-prepayments', { method: 'POST' }),
  getReservationEvents: (id) => request(`/reservations/${id}/events`),
  getAllReservationEvents: (limit = 300) => request(`/reservations/events?limit=${limit}`),
  getInactiveReservations: (limit = 200) => request(`/reservations/inactive?limit=${limit}`),
  acceptPayment: (id, data) => request(`/reservations/${id}/payment`, { method: 'POST', body: JSON.stringify(data) }),
  getReservationPayments: (id) => request(`/reservations/${id}/payments`),
  editReservationPayment: (id, incomeId, data) => request(`/reservations/${id}/payments/${incomeId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteReservationPayment: (id, incomeId) => request(`/reservations/${id}/payments/${incomeId}`, { method: 'DELETE' }),
  getAvailability: (checkIn, checkOut, guests = 1) =>
    request(`/public/availability?check_in=${checkIn}&check_out=${checkOut}&guests=${guests}`),
};
