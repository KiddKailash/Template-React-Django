/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect } from 'react';
import { login as apiLogin } from '../services/authService';
import { clearTokens, fetchCurrentUser, logoutSession } from '../services/api';
import { forgetThisDevice, reportDeviceActivity } from '../services/push';

const UserContext = createContext();

export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');
      if (token) {
        try {
          const response = await fetchCurrentUser();
          setUser(response.data);
        } catch {
          // Token is invalid / expired. The api interceptor will already
          // have cleared credentials + redirected on 401.
          setUser(null);
        }
      }
      setLoading(false);
    };
    checkAuth();
  }, []);

  const login = async (username, password) => {
    try {
      const response = await apiLogin(username, password);
      if (response.access) {
        localStorage.setItem('access_token', response.access);
        localStorage.setItem('refresh_token', response.refresh);
        const me = await fetchCurrentUser();
        setUser(me.data);
        return { success: true };
      }
      return { success: false, message: 'Invalid response from server' };
    } catch (error) {
      console.error('Login error', error);
      return {
        success: false,
        message:
          error.response?.status === 429
            ? 'Too many sign-in attempts. Try again later.'
            : error.response?.data?.detail || 'Login failed',
      };
    }
  };

  // Ends this device's session on the server first, so the tokens stop working
  // everywhere they might have been copied, then forgets them locally. Local
  // sign-out still happens if the server cannot be reached.
  const logout = async () => {
    try {
      await logoutSession();
    } catch {
      // Offline, or the session was already ended elsewhere.
    }
    await forgetThisDevice();
    clearTokens();
    // Earlier template builds cached /api/ responses in the service worker
    // (vite.config.js); drop that cache so nothing personal survives sign-out.
    if (typeof caches !== 'undefined') {
      caches.delete('api-cache').catch(() => {});
    }
    setUser(null);
  };

  // While signed in, keep this device on push rather than email: report that
  // the app is open now and whenever it comes back to the foreground.
  useEffect(() => {
    if (!user) return undefined;
    reportDeviceActivity();
    const onVisible = () => {
      if (document.visibilityState === 'visible') reportDeviceActivity();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [user]);

  return (
    <UserContext.Provider value={{ user, login, logout, loading, isLoggedIn: !!user }}>
      {children}
    </UserContext.Provider>
  );
};

export default UserContext;
