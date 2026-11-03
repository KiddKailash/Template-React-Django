import axios from 'axios';

import { API_URL } from './api';

// Plain axios, not the `api` instance: sign-in has no token to send, and a 401
// here means "wrong password", not "refresh and retry".
export const login = async (username, password) => {
  const response = await axios.post(`${API_URL}/token/`, {
    username,
    password,
  });
  return response.data;
};
