import axios from 'axios';

// Get the URL from the environment file you just edited
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const client = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 1. Interceptor: Add Token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 2. Interceptor: Handle 401 (Unauthorized)
client.interceptors.response.use(
  (response) => response,
  (error) => {
    // If the token is invalid or expired, kick user to login
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      // Only redirect if we are not already on the login page
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);