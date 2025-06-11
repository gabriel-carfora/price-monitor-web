// Replace your frontend/src/api.ts

import axios from 'axios';

const API = axios.create({
  baseURL: 'http://localhost:5000/api',
});

export const setUser = (username: string) => {
  API.defaults.headers.common['X-User'] = username;
  localStorage.setItem('username', username);
};

// Auto-set user from localStorage on page load
const savedUsername = localStorage.getItem('username');
if (savedUsername) {
  API.defaults.headers.common['X-User'] = savedUsername;
}

export default API;