import axios from 'axios';

const API = axios.create({
  baseURL: 'http://localhost:5000/api',
});

export const setUser = (username: string) => {
  API.defaults.headers.common['X-User'] = username;
};

export default API;