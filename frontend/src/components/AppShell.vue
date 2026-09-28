<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <span class="logo" aria-hidden="true">▣</span>
        <div>
          <small>Scalable E-Commerce</small>
          <strong>Inventory Management</strong>
        </div>
      </div>
      <div class="user">
        <span>Welcome, <b>{{ username }}</b></span>
        <button class="btn btn-sm logout" @click="$emit('logout')">Log out</button>
      </div>
    </header>

    <nav class="tabs" aria-label="Sections">
      <button v-for="t in tabs" :key="t.key" :class="{ active: tab === t.key }" @click="go(t.key)">
        {{ t.label }}
        <span v-if="t.badge" class="badge">{{ t.badge }}</span>
      </button>
    </nav>

    <main>
      <InsightsView v-if="tab === 'insights'" @go="go" />
      <InventoryView v-else-if="tab === 'inventory'" />
      <OrdersView v-else />
    </main>

    <div class="toasts" aria-live="polite">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.type">{{ t.text }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { stockStatus, store } from '../store';
import InsightsView from '../views/InsightsView.vue';
import InventoryView from '../views/InventoryView.vue';
import OrdersView from '../views/OrdersView.vue';

defineEmits(['logout']);

// Username comes from the JWT payload ("sub")
const username = computed(() => {
  try { return JSON.parse(atob(localStorage.getItem('token').split('.')[1])).sub; }
  catch { return 'user'; }
});

// The tab lives in the URL hash (#orders) so a page refresh keeps you on it
const valid = ['insights', 'inventory', 'orders'];
const fromHash = () => (valid.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'insights');
const tab = ref(fromHash());
const go = (key) => { tab.value = key; location.hash = key; };
const onHash = () => { tab.value = fromHash(); };

const tabs = computed(() => [
  { key: 'insights', label: 'Insights' },
  { key: 'inventory', label: 'Inventory', badge: store.products.filter((p) => stockStatus(p) !== 'ok').length || null },
  { key: 'orders', label: 'Orders', badge: store.orders.filter((o) => o.status === 'pending').length || null },
]);

onMounted(() => { store.loadAll(); window.addEventListener('hashchange', onHash); });
onUnmounted(() => window.removeEventListener('hashchange', onHash));
</script>

<style scoped>
.shell { min-height: 100vh; }
.topbar {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 12px 28px; background: var(--header); color: var(--header-text);
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  display: grid; place-items: center; width: 38px; height: 38px; border-radius: 9px;
  background: var(--primary); color: #fff; font-size: 20px;
}
.brand small { display: block; font-size: 11.5px; opacity: .7; }
.brand strong { font-size: 18px; letter-spacing: -.01em; }
.user { display: flex; align-items: center; gap: 14px; font-size: 13.5px; }
.logout { background: transparent; color: var(--header-text); border-color: rgba(255, 255, 255, .25); }
.logout:hover { background: rgba(255, 255, 255, .1) !important; }

.tabs {
  display: flex; gap: 4px; padding: 0 28px;
  background: var(--surface); border-bottom: 1px solid var(--border);
  overflow-x: auto;
}
.tabs button {
  position: relative; padding: 14px 18px; border: 0; background: none;
  color: var(--muted); font: inherit; font-weight: 650; cursor: pointer;
  text-transform: uppercase; letter-spacing: .05em; font-size: 12.5px; white-space: nowrap;
}
.tabs button:hover { color: var(--text); }
.tabs button.active { color: var(--primary); }
.tabs button.active::after {
  content: ''; position: absolute; left: 12px; right: 12px; bottom: -1px;
  height: 3px; border-radius: 3px 3px 0 0; background: var(--primary);
}
.badge {
  display: inline-block; min-width: 18px; padding: 0 5px; margin-left: 4px;
  border-radius: 9px; background: var(--warn-soft); color: var(--warn);
  font-size: 11px; line-height: 18px; text-align: center; letter-spacing: 0;
}
main { max-width: 1480px; margin: 0 auto; padding: 24px 28px 48px; }

.toasts { position: fixed; right: 20px; bottom: 20px; display: grid; gap: 8px; z-index: 60; }
.toast {
  padding: 10px 16px; border-radius: 8px; box-shadow: var(--shadow);
  background: var(--header); color: var(--header-text); font-weight: 550;
  animation: pop .2s ease-out;
}
.toast.error { background: var(--danger); color: #fff; }
@keyframes pop { from { transform: translateY(8px); opacity: 0; } }

@media (max-width: 640px) {
  .topbar, .tabs, main { padding-left: 16px; padding-right: 16px; }
  .user > span { display: none; }
}
</style>
