import axios from 'axios';

const API_URL = `${import.meta.env.VITE_BACKEND_URL}/api`;

export const login = async (username, password) => {
  const response = await axios.post(`${API_URL}/token/`, {
    username,
    password,
  });
  return response.data;
};
