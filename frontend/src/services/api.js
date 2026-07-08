import axios from 'axios';

const API_URL = `${import.meta.env.VITE_BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
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

export default api;
