/**
 * Centralized API client for PettyCash API.
 * Handles Bearer token authentication, correlation IDs, and error handling.
 */

const API_BASE = '/api';

function getAuthToken() {
  return localStorage.getItem('pettycash_auth_token') || '';
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem('pettycash_auth_token', token);
  } else {
    localStorage.removeItem('pettycash_auth_token');
  }
}

function getCurrentUser() {
  try {
    const raw = localStorage.getItem('pettycash_user');
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function setCurrentUser(user) {
  if (user) {
    localStorage.setItem('pettycash_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('pettycash_user');
  }
}

function generateCorrelationId() {
  return 'fe-' + Math.random().toString(36).substring(2, 12);
}

async function request(endpoint, options = {}) {
  const token = getAuthToken();
  const correlationId = options.correlationId || generateCorrelationId();
  
  const headers = {
    'X-Correlation-ID': correlationId,
    ...(options.headers || {}),
  };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Handle json payload vs FormData
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body === 'object') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
    body,
  });

  if (!response.ok) {
    let errorDetail = 'Request failed';
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || errJson.message || JSON.stringify(errJson);
    } catch (_) {
      errorDetail = await response.text();
    }
    const error = new Error(typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail));
    error.status = response.status;
    error.correlationId = response.headers.get('X-Correlation-ID') || correlationId;

    if (response.status === 401 && !url.includes('/auth/login') && !url.includes('/auth/me')) {
      window.dispatchEvent(new CustomEvent('pettycash:unauthorized', { detail: { error } }));
    }

    throw error;
  }

  // Check content type for binary vs json
  const contentType = response.headers.get('Content-Type') || '';
  if (contentType.includes('application/json')) {
    return await response.json();
  }
  return response;
}

export const api = {
  getAuthToken,
  setAuthToken,
  getCurrentUser,
  setCurrentUser,

  // ── Auth
  login: async (email, password) => {
    const res = await request('/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    setAuthToken(res.access_token);
    setCurrentUser(res.user);
    return res;
  },

  logout: async () => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } catch (_) {}
    setAuthToken(null);
    setCurrentUser(null);
  },

  getMe: () => request('/auth/me'),
  getBootstrapStatus: () => request('/auth/bootstrap-status'),
  bootstrapAdmin: (username, email, password) =>
    request('/auth/bootstrap', { method: 'POST', body: { username, email, password } }),
  setPassword: (token, password) =>
    request('/auth/set-password', { method: 'POST', body: { token, password } }),

  // ── Users & Assignments
  listUsers: () => request('/users'),
  provisionUser: (username, email, role) =>
    request('/users', { method: 'POST', body: { username, email, role } }),
  generateUserToken: (userId) => request(`/users/${userId}/token`, { method: 'POST' }),
  deleteUser: (userId) => request(`/users/${userId}`, { method: 'DELETE' }),
  listAssignments: () => request('/assignments'),
  createAssignment: (manager_id, employee_id) =>
    request('/assignments', { method: 'POST', body: { manager_id, employee_id } }),
  reviewAssignment: (assignment_id, decision, reason) =>
    request(`/assignments/${assignment_id}/review`, {
      method: 'POST',
      body: { decision, reason },
    }),

  // ── Master Data
  getProjects: () => request('/projects'),
  createProject: (name) => request('/projects', { method: 'POST', body: { name } }),
  updateProjectStatus: (id, is_active) =>
    request(`/projects/${id}`, { method: 'PATCH', body: { is_active } }),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  getLedgers: () => request('/ledgers'),
  createLedger: (name) => request('/ledgers', { method: 'POST', body: { name } }),
  updateLedgerStatus: (id, is_active) =>
    request(`/ledgers/${id}`, { method: 'PATCH', body: { is_active } }),
  deleteLedger: (id) => request(`/ledgers/${id}`, { method: 'DELETE' }),

  // ── Cash Balance & Controls
  getCashBalance: () => request('/cash-balance'),
  updateCashBalance: (opening_balance) =>
    request('/cash-balance', { method: 'PUT', body: { opening_balance } }),
  createBalanceAdjustment: (data) =>
    request('/cash-adjustments', { method: 'POST', body: data }),
  listBalanceAdjustments: () => request('/cash-adjustments'),

  // ── Company Receipts
  createCompanyReceipt: (data) =>
    request('/company-receipts', { method: 'POST', body: data }),
  listCompanyReceipts: () => request('/company-receipts'),
  reverseCompanyReceipt: (receipt_id, reason, effective_date) =>
    request(`/company-receipts/${receipt_id}/reverse`, {
      method: 'POST',
      body: { reason, effective_date },
    }),

  // ── Requests & Lifecycle
  listRequests: (limit = null, offset = 0) => {
    let url = '/requests';
    if (limit) url += `?limit=${limit}&offset=${offset}`;
    return request(url);
  },
  getRequest: (id) => request(`/requests/${id}`),
  createDraft: (data) => request('/requests', { method: 'POST', body: data }),
  updateDraft: (id, data) => request(`/requests/${id}`, { method: 'PATCH', body: data }),
  submitRequest: (id) => request(`/requests/${id}/submit`, { method: 'POST' }),
  submitForPosting: (id) => request(`/requests/${id}/submit-for-posting`, { method: 'POST' }),
  approveRequest: (id) => request(`/requests/${id}/approve`, { method: 'POST' }),
  requestChanges: (id, reason) =>
    request(`/requests/${id}/request-changes`, { method: 'POST', body: { reason } }),
  rejectRequest: (id, reason) =>
    request(`/requests/${id}/reject`, { method: 'POST', body: { reason } }),
  postRequest: (id, effective_date) =>
    request(`/requests/${id}/post`, { method: 'POST', body: { effective_date } }),
  returnForCorrection: (id, reason) =>
    request(`/requests/${id}/return-for-correction`, { method: 'POST', body: { reason } }),
  reverseRequest: (id, reason, effective_date) =>
    request(`/requests/${id}/reverse`, { method: 'POST', body: { reason, effective_date } }),

  // ── Supporting Files
  uploadSupportingFile: (requestId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request(`/requests/${requestId}/supporting-files`, {
      method: 'POST',
      body: formData,
    });
  },
  listSupportingFiles: (requestId) =>
    request(`/requests/${requestId}/supporting-files`),
  getSupportingFileDownloadUrl: (fileId) => {
    const token = api.getAuthToken();
    return `${API_BASE}/supporting-files/${fileId}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  // ── Periods
  listFinancialPeriods: () => request('/financial-periods'),
  createFinancialPeriod: (period_start, period_end) =>
    request('/financial-periods', { method: 'POST', body: { period_start, period_end } }),
  closeFinancialPeriod: (id) => request(`/financial-periods/${id}/close`, { method: 'POST' }),
  reopenFinancialPeriod: (id) => request(`/financial-periods/${id}/reopen`, { method: 'POST' }),

  // ── Reports
  getMonthlyReport: (month) =>
    request(`/reports/monthly${month ? `?month=${month}` : ''}`),
  getMonthlyExcelUrl: (month) => {
    const token = api.getAuthToken();
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (token) params.append('token', token);
    const qs = params.toString();
    return `${API_BASE}/reports/monthly/excel${qs ? `?${qs}` : ''}`;
  },
  getMonthlyZipUrl: (month) => {
    const token = api.getAuthToken();
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (token) params.append('token', token);
    const qs = params.toString();
    return `${API_BASE}/reports/monthly/zip${qs ? `?${qs}` : ''}`;
  },
  downloadFile: async (url, fallbackFilename) => {
    const token = api.getAuthToken();
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      let msg = `Download failed (HTTP ${res.status})`;
      try {
        const data = await res.json();
        if (data.detail) msg = data.detail;
      } catch (_) {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    let filename = fallbackFilename;
    const disposition = res.headers.get('content-disposition');
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename="?([^"]+)"?/);
      if (match && match[1]) filename = match[1];
    }
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename || 'download';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
  },

  // ── Operations & Observability
  getMetrics: () => request('/operations/metrics'),
  getErrors: (limit = 50) => request(`/operations/errors?limit=${limit}`),
  createBackup: () => request('/operations/backups/create', { method: 'POST' }),
  listBackups: () => request('/operations/backups'),
  downloadBackup: (backupId) =>
    api.downloadFile(`${API_BASE}/operations/backups/${backupId}/download`, backupId),
  verifyBackup: (backup_id) =>
    request('/operations/backups/verify', { method: 'POST', body: { backup_id } }),
  restoreBackup: (backup_id, target_db_path = null) =>
    request('/operations/backups/restore', { method: 'POST', body: { backup_id, target_db_path } }),
  executeRollback: (target_version, backup_id = null) =>
    request('/operations/rollback', { method: 'POST', body: { target_version, backup_id } }),
  getAlerts: () => request('/operations/alerts'),
  testAlert: (scenario) =>
    request('/operations/alerts/test', { method: 'POST', body: { scenario } }),
  acknowledgeAlert: (rule_id) =>
    request('/operations/alerts/acknowledge', { method: 'POST', body: { rule_id } }),
  getHealthLive: () => request('/health/live'),
  getHealthReady: () => request('/health/ready'),

  // ── Audit
  listAuditEvents: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/audit-events${q ? `?${q}` : ''}`);
  },

  // ── Legacy Ledger Workspace
  listLegacySessions: () => request('/legacy-ledger/sessions'),
  getLegacySession: (id) => request(`/legacy-ledger/sessions/${id}`),
  importSessionToLegacy: (sessionId) =>
    request(`/legacy-ledger/import-session/${sessionId}`, { method: 'POST' }),
  updateLegacySession: (id, data) =>
    request(`/legacy-ledger/sessions/${id}`, { method: 'PUT', body: data }),
  deleteLegacySession: (id) =>
    request(`/legacy-ledger/sessions/${id}`, { method: 'DELETE' }),
  getLegacyExportUrl: (id) => `${API_BASE}/legacy-ledger/sessions/${id}/export`,

  // ── Notifications
  listNotifications: (unreadOnly = false, limit = null, offset = 0) => {
    let url = `/notifications?unread_only=${unreadOnly}`;
    if (limit) url += `&limit=${limit}&offset=${offset}`;
    return request(url);
  },
  markNotificationRead: (id) =>
    request(`/notifications/${id}/read`, { method: 'POST' }),
  markNotificationUnread: (id) =>
    request(`/notifications/${id}/unread`, { method: 'POST' }),
  markAllNotificationsRead: () =>
    request('/notifications/mark-all-read', { method: 'POST' }),
  getNotificationPreferences: () => request('/notification-preferences'),
  updateNotificationPreferences: (in_app_enabled, email_enabled) =>
    request('/notification-preferences', {
      method: 'PUT',
      body: { in_app_enabled, email_enabled },
    }),

  // ── Spreadsheet Sessions (Compatibility Utility)
  getDefaultData: () => request('/default-data'),
  uploadSpreadsheet: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request('/upload', { method: 'POST', body: formData });
  },
  recalculateSpreadsheet: (data) => request('/recalculate', { method: 'POST', body: data }),
  listSpreadsheetSessions: () => request('/sessions'),
  getSpreadsheetSession: (id) => request(`/sessions/${id}`),
  createSpreadsheetSession: (data) => request('/sessions', { method: 'POST', body: data }),
  updateSpreadsheetSession: (id, data) => request(`/sessions/${id}`, { method: 'PUT', body: data }),
  renameSpreadsheetSession: (id, name) => request(`/sessions/${id}/rename`, { method: 'PATCH', body: { name } }),
  deleteSpreadsheetSession: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
  exportDrilldown: (data) => request('/export-drilldown', { method: 'POST', body: data }),
  exportFullExcel: (data) => request('/export', { method: 'POST', body: data }),
  exportSpreadsheetZip: (data) => request('/export-zip', { method: 'POST', body: data }),
  getSessionZipUrl: (id) => `${API_BASE}/sessions/${id}/zip`,
};
