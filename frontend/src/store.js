// Shared app state: products, orders and toast messages.
// Every tab reads from here, so Insights, Inventory and Orders stay in sync.
import { reactive } from 'vue';
import api from './api';

export const money = (v) =>
  new Intl.NumberFormat('en-LK', { style: 'currency', currency: 'LKR' }).format(v || 0);

export const stockStatus = (p) =>
  p.quantity === 0 ? 'out' : p.quantity <= p.reorder_level ? 'low' : 'ok';

export const errorText = (error, fallback) => error.response?.data?.detail
  ? (typeof error.response.data.detail === 'string' ? error.response.data.detail : fallback)
  : fallback;

export const store = reactive({
  products: [],
  orders: [],
  toasts: [],

  toast(text, type = 'ok') {
    const id = Date.now() + Math.random();
    this.toasts.push({ id, text, type });
    setTimeout(() => { this.toasts = this.toasts.filter((t) => t.id !== id); }, 3500);
  },

  async loadProducts() {
    try {
      this.products = (await api.get('/inventory/products')).data;
    } catch (e) {
      if (e.response?.status !== 401) this.toast('Could not load inventory', 'error');
    }
  },

  async loadOrders() {
    try {
      this.orders = (await api.get('/orders')).data;
    } catch (e) {
      if (e.response?.status !== 401) this.toast('Could not load orders (is order-service running?)', 'error');
    }
  },

  async loadAll() {
    await Promise.all([this.loadProducts(), this.loadOrders()]);
  },

  reset() {
    this.products = [];
    this.orders = [];
  },
});
