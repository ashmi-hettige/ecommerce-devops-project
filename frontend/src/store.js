// Shared app state: the signed-in user, products, orders, and toast messages.
// Every page reads from here, so Home, Inventory, Orders and Reports stay in sync.
import { reactive } from 'vue';
import api from './api';

export const money = (v) =>
  new Intl.NumberFormat('en-LK', { style: 'currency', currency: 'LKR' }).format(v || 0);

export const stockStatus = (p) =>
  p.quantity === 0 ? 'out' : p.quantity <= p.reorder_level ? 'low' : 'ok';

export const errorText = (error, fallback) => {
  const d = error.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg.replace(/^Value error, /, '');
  return fallback;
};

export const fmtDateTime = (iso) => new Date(iso).toLocaleString('en-GB', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
});

export const ROLE_LABELS = {
  admin: 'Admin',
  inventory_manager: 'Inventory manager',
  warehouse: 'Warehouse staff',
  sales: 'Sales / customer service',
};

export const PERMISSION_LABELS = {
  'products:read': 'View products and stock',
  'products:write': 'Create, edit and delete products',
  'products:price': 'Set and change prices',
  'stock:adjust': 'Adjust stock (+/−)',
  'stock:receive': 'Receive deliveries',
  'stock:count': 'Record stock counts',
  'orders:read': 'View orders',
  'orders:create': 'Create orders',
  'orders:delete': 'Cancel orders',
  'orders:fulfil': 'Pick, pack and ship orders',
  'orders:return': 'Process returns',
  'reports:read': 'View reports',
  'users:manage': 'Manage users and roles',
};

export const MOVE_LABELS = {
  create: 'New', receive: 'Received', count: 'Counted', adjust: 'Adjusted', edit: 'Edited',
  reserve: 'Ordered', release: 'Released', return: 'Returned',
};

// The JWT payload is base64url-encoded JSON: {sub, name, role, perms, pwd_change, exp}
function decodeToken(token) {
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(decodeURIComponent(escape(atob(b64.padEnd(b64.length + (4 - b64.length % 4) % 4, '=')))));
  } catch {
    return null;
  }
}

function readSession() {
  const token = localStorage.getItem('token');
  const claims = token && decodeToken(token);
  if (!claims || claims.exp * 1000 < Date.now()) return null;
  return {
    username: claims.sub,
    name: claims.name || claims.sub,
    role: claims.role,
    perms: claims.perms || [],
    mustChange: !!claims.pwd_change,
  };
}

export const store = reactive({
  session: readSession(),
  products: [],
  orders: [],
  movements: [],
  users: [],
  toasts: [],
  navFilter: null, // lets Home send you to e.g. Orders filtered to "pending"

  can(perm) {
    return !!this.session?.perms.includes(perm);
  },

  setToken(token) {
    localStorage.setItem('token', token);
    this.session = readSession();
  },

  logout() {
    localStorage.removeItem('token');
    this.session = null;
    this.products = []; this.orders = []; this.movements = []; this.users = [];
  },

  toast(text, type = 'ok') {
    const id = Date.now() + Math.random();
    this.toasts.push({ id, text, type });
    setTimeout(() => { this.toasts = this.toasts.filter((t) => t.id !== id); }, 3500);
  },

  async _load(key, url, label) {
    try {
      this[key] = (await api.get(url)).data;
    } catch (e) {
      if (e.response?.status !== 401) this.toast(`Could not load ${label}`, 'error');
    }
  },
  loadProducts() { return this.can('products:read') && this._load('products', '/inventory/products', 'inventory'); },
  loadOrders() { return this.can('orders:read') && this._load('orders', '/orders', 'orders (is order-service running?)'); },
  loadMovements() { return this.can('products:read') && this._load('movements', '/inventory/movements?limit=100', 'stock history'); },
  loadUsers() { return this.can('users:manage') && this._load('users', '/auth/users', 'users'); },

  async loadAll() {
    await Promise.all([this.loadProducts(), this.loadOrders(), this.loadMovements(), this.loadUsers()]);
  },
});
