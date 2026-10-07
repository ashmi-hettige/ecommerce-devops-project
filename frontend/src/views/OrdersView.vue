<template>
  <div class="page">
    <section class="card panel">
      <h2>Orders</h2>
      <p class="muted">You have {{ store.orders.length }} orders · {{ toFulfil }} still to fulfil</p>

      <div class="toolbar">
        <input class="input search" v-model="query" placeholder="Search order, customer, address" />
        <span class="spacer"></span>
        <button v-if="can('orders:create')" class="btn btn-primary" @click="openNew">＋ Add an Order</button>
        <button v-if="can('orders:delete')" class="btn btn-danger" :disabled="!selected.length" @click="confirmDelete = true">
          Cancel Selected{{ selected.length ? ` (${selected.length})` : '' }}
        </button>
        <button class="btn" @click="refresh">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" />
          </svg>
          Refresh
        </button>
      </div>

      <DataTable :rows="rows" :columns="columns" :query="query"
                 :search-keys="['order_no', 'customer', 'ship_to', 'status']"
                 :selectable="can('orders:delete')"
                 v-model:selected="selected" :default-sort="{ key: 'order_no', dir: 'desc' }"
                 empty-text="No orders here.">
        <template #cell-order_no="{ row }">
          <button class="link" @click="detail = row">#{{ row.order_no }}</button>
        </template>
        <template #cell-created_at="{ row }">{{ fmtDate(row.created_at) }}</template>
        <template #cell-ship_to="{ row }"><span class="muted">{{ row.ship_to || '—' }}</span></template>
        <template #cell-total="{ row }">{{ money(row.total) }}</template>
        <template #cell-status="{ row }"><span class="pill" :class="`pill-${row.status}`">{{ cap(row.status) }}</span></template>
        <template #cell-action="{ row }">
          <template v-if="NEXT[row.status] && can('orders:fulfil')">
            <button class="btn btn-sm" :class="{ 'btn-primary': row.status === 'packed' }" @click="advance(row)">
              {{ NEXT[row.status].label }}
            </button>
          </template>
          <button v-else-if="row.status === 'shipped' && can('orders:return')" class="btn btn-sm" @click="returning = row">Return</button>
          <span v-else class="muted small">{{ waitingText(row) }}</span>
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
      <p><b>{{ detail.customer }}</b><br /><span class="muted">{{ detail.ship_to || 'No address' }} · created by {{ detail.created_by || '—' }}</span></p>
      <table class="mini"><tbody>
        <tr v-for="it in detail.items" :key="it.product_id">
          <td>{{ it.name }} <span class="muted">{{ it.sku }}</span></td>
          <td class="num">{{ it.quantity }} × {{ money(it.price) }}</td>
          <td class="num">{{ money(it.quantity * it.price) }}</td>
        </tr>
        <tr class="sum"><td colspan="2">Total</td><td class="num">{{ money(detail.total) }}</td></tr>
      </tbody></table>
      <h3 class="tl-title">History</h3>
      <ol class="timeline">
        <li v-for="(h, i) in detail.history" :key="i">
          <span class="pill" :class="`pill-${h.status}`">{{ cap(h.status) }}</span>
          <span>by <b>{{ h.by }}</b> · {{ fmtDateTime(h.at) }}</span>
          <span v-if="h.note" class="muted">— {{ h.note }}</span>
        </li>
      </ol>
    </Modal>

    <!-- Return -->
    <Modal v-if="returning" :title="`Return order #${returning.order_no}`" @close="returning = null">
      <form id="return-form" class="order-form" @submit.prevent="submitReturn">
        <p class="muted" style="margin:0">All {{ returning.item_count }} item(s) will be put back into stock.</p>
        <label class="field">Reason <input class="input" v-model.trim="returnReason" maxlength="200" placeholder="e.g. Damaged in transit" /></label>
      </form>
      <template #footer>
        <button class="btn" @click="returning = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="return-form" :disabled="saving">Process return</button>
      </template>
    </Modal>

    <!-- Confirm cancel -->
    <Modal v-if="confirmDelete" title="Cancel orders" @close="confirmDelete = false">
      <p>Cancel {{ selected.length }} selected order{{ selected.length > 1 ? 's' : '' }}?
        Their stock will be returned to inventory. Shipped orders can't be cancelled (use Return).</p>
      <template #footer>
        <button class="btn" @click="confirmDelete = false">Keep</button>
        <button class="btn btn-danger" @click="deleteSelected">Cancel orders</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import api from '../api';
import DataTable from '../components/DataTable.vue';
import Modal from '../components/Modal.vue';
import { errorText, fmtDateTime, money, store } from '../store';

const can = (p) => store.can(p);
const query = ref('');
const selected = ref([]);
const status = ref('all');
const draft = ref(null);
const detail = ref(null);
const returning = ref(null);
const returnReason = ref('');
const saving = ref(false);
const confirmDelete = ref(false);

const NEXT = {
  pending: { status: 'picked', label: 'Pick' },
  picked: { status: 'packed', label: 'Pack' },
  packed: { status: 'shipped', label: 'Ship' },
};
const STATUSES = ['pending', 'picked', 'packed', 'shipped', 'returned'];

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const fmtDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
const waitingText = (row) => ({
  pending: 'Awaiting warehouse', picked: 'Awaiting packing', packed: 'Awaiting dispatch',
  shipped: '✓', returned: '—',
}[row.status]);

const columns = [
  { key: 'order_no', label: 'Order #', sortable: true },
  { key: 'created_at', label: 'Order date', sortable: true },
  { key: 'customer', label: 'Customer', sortable: true },
  { key: 'ship_to', label: 'Ship to', sortable: true },
  { key: 'item_count', label: '# Items', sortable: true, align: 'center' },
  { key: 'total', label: 'Total', sortable: true, align: 'right' },
  { key: 'status', label: 'Status', sortable: true, sortValue: (r) => STATUSES.indexOf(r.status) },
  { key: 'action', label: 'Action', align: 'center' },
];

const counts = computed(() => {
  const c = Object.fromEntries(STATUSES.map((s) => [s, 0]));
  store.orders.forEach((o) => c[o.status]++);
  return c;
});
const toFulfil = computed(() => counts.value.pending + counts.value.picked + counts.value.packed);
const statusFilters = computed(() => [
  { key: 'all', label: 'All orders', count: store.orders.length },
  ...STATUSES.map((s) => ({ key: s, label: cap(s), count: counts.value[s] })),
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
    await store.loadAll();
  } catch (e) {
    store.toast(errorText(e, 'Could not place order'), 'error');
  } finally {
    saving.value = false;
  }
}

async function advance(order) {
  const next = NEXT[order.status];
  try {
    const { data } = await api.patch(`/orders/${order.id}/status`, { status: next.status });
    Object.assign(order, data);
    store.toast(`Order #${order.order_no} ${next.status}`);
  } catch (e) {
    store.toast(errorText(e, 'Could not update order'), 'error');
  }
}

async function submitReturn() {
  saving.value = true;
  try {
    const { data } = await api.post(`/orders/${returning.value.id}/return`, { reason: returnReason.value });
    store.toast(`Order #${data.order_no} returned; stock restored`);
    returning.value = null;
    returnReason.value = '';
    await store.loadAll();
  } catch (e) {
    store.toast(errorText(e, 'Could not process return'), 'error');
  } finally {
    saving.value = false;
  }
}

async function deleteSelected() {
  const ids = [...selected.value];
  confirmDelete.value = false;
  const results = await Promise.allSettled(ids.map((id) => api.delete(`/orders/${id}`)));
  const failed = results.filter((r) => r.status === 'rejected');
  if (failed.length) store.toast(errorText(failed[0].reason, `${failed.length} order(s) could not be cancelled`), 'error');
  else store.toast(`Cancelled ${ids.length} order(s)`);
  selected.value = [];
  await store.loadAll();
}

async function refresh() {
  await store.loadAll();
  store.toast('Orders refreshed');
}

// Shortcuts from the Home page
onMounted(() => {
  const nav = store.navFilter;
  store.navFilter = null;
  if (STATUSES.includes(nav)) status.value = nav;
  if (nav === 'new-order' && can('orders:create')) openNew();
});
</script>

<style scoped>
.link { border: 0; background: none; padding: 0; color: var(--primary); font: inherit; font-weight: 650; cursor: pointer; }
.link:hover { text-decoration: underline; }
.small { font-size: 13.5px; }
.help { padding: 0 16px 16px; margin: 4px 0 0; font-size: 14px; }
.order-form { display: grid; gap: 18px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.lines { display: grid; gap: 8px; }
.line { display: grid; grid-template-columns: 1fr 80px 110px 28px; gap: 8px; align-items: center; }
.line.head { font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.add-line { justify-self: start; }
.total { display: flex; justify-content: flex-end; gap: 12px; font-size: 17px; border-top: 1px solid var(--border); padding-top: 12px; }
.mini { width: 100%; border-collapse: collapse; margin: 8px 0 14px; }
.mini td { padding: 8px 0; border-bottom: 1px solid var(--border); }
.mini .sum td { font-weight: 700; border-bottom: 0; }
.tl-title { margin: 6px 0 8px; }
.timeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.timeline li { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px; }
@media (max-width: 560px) {
  .two { grid-template-columns: 1fr; }
  .line { grid-template-columns: 1fr 64px 28px; }
  .line > .num { display: none; }
}
</style>
