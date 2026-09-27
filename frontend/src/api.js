// One shared axios instance for the whole app.
//
// baseURL is RELATIVE ("/api"), so the browser always calls the same host
// that served the page. Who forwards /api/auth and /api/inventory to the
// right microservice depends on where the app runs:
//   - locally:     the Vite dev server proxy (see vite.config.js)
//   - Docker/K8s:  Nginx or a Kubernetes Ingress
// That's why there is no "http://127.0.0.1:8000" hardcoded anywhere.
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// Attach the JWT to every request automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// If the token is missing/expired, tell the app to log out
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLogin = error.config?.url?.includes('/auth/login');
    if (error.response?.status === 401 && !isLogin) {
      window.dispatchEvent(new Event('auth-expired'));
    }
    return Promise.reject(error);
  }
);

export default api;
