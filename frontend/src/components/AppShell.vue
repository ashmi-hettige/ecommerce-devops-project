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
        <span class="who">
          <b>{{ store.session.name }}</b>
          <span class="role">{{ ROLE_LABELS[store.session.role] }}</span>
        </span>
        <button class="btn btn-sm ghost" @click="showPassword = true">Change password</button>
        <button class="btn btn-sm ghost" @click="store.logout()">Log out</button>
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
      <OrdersView v-else-if="tab === 'orders'" />
      <UsersView v-else-if="tab === 'users'" />
    </main>

    <Modal v-if="showPassword" title="Change password" @close="showPassword = false">
      <ChangePassword @done="showPassword = false" />
    </Modal>

    <div class="toasts" aria-live="polite">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.type">{{ t.text }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { ROLE_LABELS, stockStatus, store } from '../store';
import Modal from './Modal.vue';
import ChangePassword from './ChangePassword.vue';
import InsightsView from '../views/InsightsView.vue';
import InventoryView from '../views/InventoryView.vue';
import OrdersView from '../views/OrdersView.vue';
import UsersView from '../views/UsersView.vue';

const showPassword = ref(false);

// Tabs are shown only if your role has the permission for them.
// (Hiding is for convenience; the backend enforces every permission anyway.)
const tabs = computed(() => [
  store.can('reports:read') && { key: 'insights', label: 'Insights' },
  store.can('products:read') && {
    key: 'inventory', label: 'Inventory',
    badge: store.products.filter((p) => stockStatus(p) !== 'ok').length || null,
  },
  store.can('orders:read') && {
    key: 'orders', label: 'Orders',
    badge: store.orders.filter((o) => ['pending', 'picked', 'packed'].includes(o.status)).length || null,
  },
  store.can('users:manage') && { key: 'users', label: 'Users' },
].filter(Boolean));

// The tab lives in the URL hash (#orders) so a page refresh keeps you on it
const allowed = () => tabs.value.map((t) => t.key);
// Default tab = the first one your role can see (Insights for admin/manager,
// Inventory for warehouse and sales staff)
const fromHash = () => (allowed().includes(location.hash.slice(1)) ? location.hash.slice(1) : allowed()[0]);
const tab = ref(fromHash());
const go = (key, filter = null) => { store.navFilter = filter; tab.value = key; location.hash = key; };
const onHash = () => { tab.value = fromHash(); };

// If the role changes (e.g. after re-login) and the tab is no longer allowed, go to the first allowed one
watch(tabs, () => { if (!allowed().includes(tab.value)) go(allowed()[0]); });

onMounted(() => { store.loadAll(); window.addEventListener('hashchange', onHash); });
onUnmounted(() => window.removeEventListener('hashchange', onHash));
</script>

<style scoped>
.shell { min-height: 100vh; }
.topbar {
  display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 12px 28px; background: var(--header); color: var(--header-text);
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  display: grid; place-items: center; width: 38px; height: 38px; border-radius: 9px;
  background: var(--primary); color: #fff; font-size: 20px;
}
.brand small { display: block; font-size: 11.5px; opacity: .7; }
.brand strong { font-size: 18px; letter-spacing: -.01em; }
.user { display: flex; align-items: center; gap: 10px; font-size: 13.5px; }
.who { display: grid; text-align: right; line-height: 1.25; margin-right: 4px; }
.role { font-size: 11.5px; opacity: .75; }
.ghost { background: transparent; color: var(--header-text); border-color: rgba(255, 255, 255, .25); }
.ghost:hover { background: rgba(255, 255, 255, .1) !important; }

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

@media (max-width: 720px) {
  .topbar, .tabs, main { padding-left: 16px; padding-right: 16px; }
  .who { display: none; }
}
</style>
