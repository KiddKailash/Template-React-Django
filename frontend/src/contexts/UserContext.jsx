/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect } from 'react';
import { login as apiLogin } from '../services/authService';
import { fetchCurrentUser } from '../services/api';

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
        message: error.response?.data?.detail || 'Login failed',
      };
    }
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  };

  return (
    <UserContext.Provider value={{ user, login, logout, loading, isLoggedIn: !!user }}>
      {children}
    </UserContext.Provider>
  );
};

export default UserContext;
