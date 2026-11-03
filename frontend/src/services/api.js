import axios from 'axios';

/** Exported so authService (sign-in has no token and must bypass the refresh
 * interceptor) derives its URL from the same place.
 *
 * `?? ''` (from Store-Arbitrage): a missing VITE_BACKEND_URL otherwise
 * interpolates the string "undefined" and the app requests `undefined/api`, a
 * relative path that 404s like a routing bug. In production leave it EMPTY:
 * that gives the relative `/api`, which this host's nginx proxies to its own
 * backend, and keeps the CSP's `connect-src 'self'` true. Local dev sets it to
 * http://localhost:8000 (frontend/.env.example). */
export const API_URL = `${import.meta.env.VITE_BACKEND_URL ?? ''}/api`;

/** Back to sign-in, remembering where the user was (`?next=`), once. */
export const redirectToLogin = () => {
  const current = window.location.pathname + window.location.search;
  if (current.startsWith('/login')) return;
  window.location.href = `/login?next=${encodeURIComponent(current)}`;
};

export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

/** No instance-wide `Content-Type`, on purpose (Store-Arbitrage finding F20).
 * axios labels each body itself: objects as JSON, and a `FormData` is left for
 * the browser to send as `multipart/form-data; boundary=...`. A default of
 * `application/json` makes axios 1.x serialise a FormData upload to JSON, and
 * a multipart-only view answers 415. */
const api = axios.create({ baseURL: API_URL });

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          // A device signed out from another session (Settings -> Devices)
          // fails here: its session is revoked, so refresh answers 401.
          const response = await axios.post(`${API_URL}/token/refresh/`, {
            refresh: refreshToken,
          });
          if (response.status === 200) {
            localStorage.setItem('access_token', response.data.access);
            if (response.data.refresh) {
              localStorage.setItem('refresh_token', response.data.refresh);
            }
            api.defaults.headers.common['Authorization'] = `Bearer ${response.data.access}`;
            return api(originalRequest);
          }
        } catch (refreshError) {
          console.error('Token refresh failed', refreshError);
          clearTokens();
          redirectToLogin();
        }
      } else {
        redirectToLogin();
      }
    }
    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Endpoint wrappers — add your project's endpoints below.
// ---------------------------------------------------------------------------

export const fetchCurrentUser = () => api.get('me/');
export const fetchHealth = () => api.get('health/');

// Account + device sessions (backend/accounts/).
export const logoutSession = () => api.post('auth/logout/');
export const changePassword = (currentPassword, newPassword) =>
  api.post('auth/password/', {
    current_password: currentPassword,
    new_password: newPassword,
  });
export const fetchSessions = () => api.get('sessions/');
export const revokeSession = (id) => api.delete(`sessions/${id}/`);
export const revokeOtherSessions = () => api.post('sessions/revoke-others/');

export default api;
