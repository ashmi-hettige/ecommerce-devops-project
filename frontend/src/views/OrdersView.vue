<template>
  <div class="page">
    <section class="card panel">
      <h2>Orders</h2>
      <p class="muted">You have {{ store.orders.length }} orders · {{ counts.pending }} waiting to be picked</p>

      <div class="toolbar">
        <input class="input search" v-model="query" placeholder="Search order #, customer, address…" />
        <span class="spacer"></span>
        <button class="btn btn-primary" @click="openNew">＋ Add an Order</button>
        <button class="btn btn-danger" :disabled="!selected.length" @click="confirmDelete = true">
          Delete Selected{{ selected.length ? ` (${selected.length})` : '' }}
        </button>
        <button class="btn" @click="refresh">⟳ Refresh</button>
      </div>

      <DataTable :rows="rows" :columns="columns" :query="query"
                 :search-keys="['order_no', 'customer', 'ship_to', 'status']"
                 v-model:selected="selected" :default-sort="{ key: 'order_no', dir: 'desc' }"
                 empty-text="No orders yet. Create one with “Add an Order”.">
        <template #cell-order_no="{ row }">
          <button class="link" @click="detail = row">#{{ row.order_no }}</button>
        </template>
        <template #cell-created_at="{ row }">{{ fmtDate(row.created_at) }}</template>
        <template #cell-ship_to="{ row }"><span class="muted">{{ row.ship_to || '—' }}</span></template>
        <template #cell-total="{ row }">{{ money(row.total) }}</template>
        <template #cell-status="{ row }"><span class="pill" :class="`pill-${row.status}`">{{ cap(row.status) }}</span></template>
        <template #cell-action="{ row }">
          <button v-if="row.status === 'pending'" class="btn btn-sm" @click="advance(row, 'picked')">Pick</button>
          <button v-else-if="row.status === 'picked'" class="btn btn-sm btn-primary" @click="advance(row, 'shipped')">Ship</button>
          <span v-else class="muted">✓ Done</span>
        </template>
      </DataTable>
    </section>

    <aside class="card side">
      <h3>Orders</h3>
      <ul>
        <li v-for="s in statusFilters" :key="s.key">
          <button :class="{ active: status === s.key }" @click="status = s.key">
            {{ s.label }} <span class="count">{{ s.count }}</span>
          </button>
        </li>
      </ul>
      <div class="sub">How it works</div>
      <p class="help muted">
        New orders reserve stock straight away. <b>Pick</b> when packed, <b>Ship</b> when sent.
        Deleting an order that hasn't shipped puts its stock back.
      </p>
    </aside>

    <!-- New order -->
    <Modal v-if="draft" title="New order" width="620px" @close="draft = null">
      <form id="order-form" @submit.prevent="submitOrder" class="order-form">
        <div class="two">
          <label class="field">Customer <input class="input" v-model.trim="draft.customer" required maxlength="100" /></label>
          <label class="field">Ship to <input class="input" v-model.trim="draft.ship_to" maxlength="200" placeholder="City or address" /></label>
        </div>

        <div class="lines">
          <div class="line head"><span>Product</span><span>Qty</span><span class="num">Line total</span><span></span></div>
          <div class="line" v-for="(line, i) in draft.items" :key="i">
            <select class="input" v-model="line.product_id" required>
              <option value="" disabled>Choose a product…</option>
              <option v-for="p in store.products" :key="p.id" :value="p.id" :disabled="p.quantity === 0">
                {{ p.name }} — {{ money(p.price) }} ({{ p.quantity }} in stock)
              </option>
            </select>
            <input class="input" type="number" min="1" :max="productById[line.product_id]?.quantity" v-model.number="line.quantity" required />
            <span class="num">{{ money((productById[line.product_id]?.price || 0) * (line.quantity || 0)) }}</span>
            <button type="button" class="btn btn-sm btn-icon" :disabled="draft.items.length === 1" @click="draft.items.splice(i, 1)" aria-label="Remove line">✕</button>
          </div>
          <button type="button" class="btn btn-sm add-line" @click="draft.items.push({ product_id: '', quantity: 1 })">＋ Add item</button>
        </div>

        <div class="total">Total <strong>{{ money(draftTotal) }}</strong></div>
      </form>
      <template #footer>
        <button class="btn" @click="draft = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="order-form" :disabled="saving">
          {{ saving ? 'Placing…' : 'Place order' }}
        </button>
      </template>
    </Modal>

    <!-- Order detail -->
    <Modal v-if="detail" :title="`Order #${detail.order_no}`" @close="detail = null">
      <p><b>{{ detail.customer }}</b><br /><span class="muted">{{ detail.ship_to || 'No address' }} · {{ fmtDate(detail.created_at) }}</span></p>
      <table class="mini"><tbody>
        <tr v-for="it in detail.items" :key="it.product_id">
          <td>{{ it.name }} <span class="muted">{{ it.sku }}</span></td>
          <td class="num">{{ it.quantity }} × {{ money(it.price) }}</td>
          <td class="num">{{ money(it.quantity * it.price) }}</td>
        </tr>
        <tr class="sum"><td colspan="2">Total</td><td class="num">{{ money(detail.total) }}</td></tr>
      </tbody></table>
      <p>Status: <span class="pill" :class="`pill-${detail.status}`">{{ cap(detail.status) }}</span></p>
    </Modal>

    <!-- Confirm delete -->
    <Modal v-if="confirmDelete" title="Delete orders" @close="confirmDelete = false">
      <p>Delete {{ selected.length }} selected order{{ selected.length > 1 ? 's' : '' }}?
        Stock from unshipped orders will be returned to inventory.</p>
      <template #footer>
        <button class="btn" @click="confirmDelete = false">Cancel</button>
        <button class="btn btn-danger" @click="deleteSelected">Delete</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import api from '../api';
import DataTable from '../components/DataTable.vue';
import Modal from '../components/Modal.vue';
import { errorText, money, store } from '../store';

const query = ref('');
const selected = ref([]);
const status = ref('all');
const draft = ref(null);
const detail = ref(null);
const saving = ref(false);
const confirmDelete = ref(false);

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const fmtDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

const columns = [
  { key: 'order_no', label: 'Order #', sortable: true },
  { key: 'created_at', label: 'Order date', sortable: true },
  { key: 'customer', label: 'Customer', sortable: true },
  { key: 'ship_to', label: 'Ship to', sortable: true },
  { key: 'item_count', label: '# Items', sortable: true, align: 'center' },
  { key: 'total', label: 'Total', sortable: true, align: 'right' },
  { key: 'status', label: 'Status', sortable: true, sortValue: (r) => ['pending', 'picked', 'shipped'].indexOf(r.status) },
  { key: 'action', label: 'Action', align: 'center' },
];

const counts = computed(() => {
  const c = { pending: 0, picked: 0, shipped: 0 };
  store.orders.forEach((o) => c[o.status]++);
  return c;
});
const statusFilters = computed(() => [
  { key: 'all', label: 'All orders', count: store.orders.length },
  { key: 'pending', label: 'Pending', count: counts.value.pending },
  { key: 'picked', label: 'Picked', count: counts.value.picked },
  { key: 'shipped', label: 'Shipped', count: counts.value.shipped },
]);

const rows = computed(() => store.orders.filter((o) => status.value === 'all' || o.status === status.value));

const productById = computed(() => Object.fromEntries(store.products.map((p) => [p.id, p])));
const draftTotal = computed(() => (draft.value?.items || [])
  .reduce((sum, l) => sum + (productById.value[l.product_id]?.price || 0) * (l.quantity || 0), 0));

async function openNew() {
  if (!store.products.length) await store.loadProducts();
  draft.value = { customer: '', ship_to: '', items: [{ product_id: '', quantity: 1 }] };
}

async function submitOrder() {
  saving.value = true;
  try {
    const { data } = await api.post('/orders', draft.value);
    store.toast(`Order #${data.order_no} placed`);
    draft.value = null;
    await store.loadAll(); // stock levels changed too
  } catch (e) {
    store.toast(errorText(e, 'Could not place order'), 'error');
  } finally {
    saving.value = false;
  }
}

async function advance(order, next) {
  try {
    const { data } = await api.patch(`/orders/${order.id}/status`, { status: next });
    order.status = data.status;
    store.toast(`Order #${order.order_no} ${next}`);
  } catch (e) {
    store.toast(errorText(e, 'Could not update order'), 'error');
  }
}

async function deleteSelected() {
  const ids = [...selected.value];
  confirmDelete.value = false;
  const results = await Promise.allSettled(ids.map((id) => api.delete(`/orders/${id}`)));
  const failed = results.filter((r) => r.status === 'rejected').length;
  store.toast(failed ? `${failed} order(s) could not be deleted` : `Deleted ${ids.length} order(s)`, failed ? 'error' : 'ok');
  selected.value = [];
  await store.loadAll();
}

async function refresh() {
  await store.loadAll();
  store.toast('Orders refreshed');
}
</script>

<style scoped>
.link { border: 0; background: none; padding: 0; color: var(--primary); font: inherit; font-weight: 650; cursor: pointer; }
.link:hover { text-decoration: underline; }
.help { padding: 0 16px 16px; margin: 4px 0 0; font-size: 13px; }
.order-form { display: grid; gap: 18px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.lines { display: grid; gap: 8px; }
.line { display: grid; grid-template-columns: 1fr 80px 110px 28px; gap: 8px; align-items: center; }
.line.head { font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.add-line { justify-self: start; }
.total { display: flex; justify-content: flex-end; gap: 12px; font-size: 16px; border-top: 1px solid var(--border); padding-top: 12px; }
.mini { width: 100%; border-collapse: collapse; margin: 8px 0 14px; }
.mini td { padding: 8px 0; border-bottom: 1px solid var(--border); }
.mini .sum td { font-weight: 700; border-bottom: 0; }
@media (max-width: 560px) {
  .two { grid-template-columns: 1fr; }
  .line { grid-template-columns: 1fr 64px 28px; }
  .line > .num { display: none; }
}
</style>
