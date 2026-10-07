<template>
  <div class="page">
    <section class="card panel">
      <h2>Inventory</h2>
      <p class="muted">{{ store.products.length }} products · {{ lowCount }} need restocking</p>

      <div class="toolbar">
        <input class="input search" v-model="query" placeholder="Search name, SKU, category" />
        <span class="spacer"></span>
        <button v-if="can('stock:receive')" class="btn" @click="openStock('receive')">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 3v11" /><path d="m7.5 9.5 4.5 4.5 4.5-4.5" />
            <path d="M3 14v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4" />
          </svg>
          Receive
        </button>
        <button v-if="can('stock:count')" class="btn" @click="openStock('count')">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1" />
            <path d="m8.5 10 1.5 1.5 2.5-2.5" /><path d="M14.5 10.5H16" />
            <path d="m8.5 15.5 1.5 1.5 2.5-2.5" /><path d="M14.5 16H16" />
          </svg>
          Count
        </button>
        <button v-if="can('products:write')" class="btn btn-primary" @click="openAdd">＋ Add Product</button>
        <button v-if="can('products:write')" class="btn btn-danger" :disabled="!selected.length" @click="confirmDelete = true">
          Delete Selected{{ selected.length ? ` (${selected.length})` : '' }}
        </button>
        <button class="btn" @click="refresh">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" />
          </svg>
          Refresh
        </button>
      </div>

      <DataTable :rows="rows" :columns="columns" :query="query" :search-keys="['name', 'sku', 'category']"
                 :selectable="can('products:write')"
                 v-model:selected="selected" :default-sort="{ key: 'name', dir: 'asc' }"
                 empty-text="No products match.">
        <template #cell-name="{ row }">
          <strong>{{ row.name }}</strong>
          <div class="sku muted">{{ row.sku || 'No SKU' }}</div>
        </template>
        <template #cell-price="{ row }">{{ money(row.price) }}</template>
        <template #cell-quantity="{ row }">
          <span class="qty" v-if="can('stock:adjust')">
            <button class="btn btn-sm btn-icon" :disabled="row.quantity === 0" @click="adjust(row, -1)" aria-label="Decrease">−</button>
            <span class="n">{{ row.quantity }}</span>
            <button class="btn btn-sm btn-icon" @click="adjust(row, 1)" aria-label="Increase">+</button>
          </span>
          <span v-else class="n">{{ row.quantity }}</span>
        </template>
        <template #cell-status="{ row }">
          <span class="pill" :class="`pill-${stockStatus(row)}`">{{ statusLabel[stockStatus(row)] }}</span>
        </template>
        <template #cell-value="{ row }">{{ money(row.price * row.quantity) }}</template>
        <template #cell-actions="{ row }">
          <span class="row-actions">
            <button v-if="can('stock:receive')" class="btn btn-sm" @click="openStock('receive', row)">Receive</button>
            <button v-if="can('stock:count')" class="btn btn-sm" @click="openStock('count', row)">Count</button>
            <button v-if="can('products:write')" class="btn btn-sm" @click="openEdit(row)">Edit</button>
          </span>
        </template>
      </DataTable>
    </section>

    <aside class="card side">
      <h3>Stock</h3>
      <ul>
        <li v-for="f in stockFilters" :key="f.key">
          <button :class="{ active: filter === f.key }" @click="filter = f.key">
            {{ f.label }} <span class="count">{{ f.count }}</span>
          </button>
        </li>
      </ul>
      <div class="sub">Categories</div>
      <ul>
        <li><button :class="{ active: category === '' }" @click="category = ''">All categories</button></li>
        <li v-for="c in categories" :key="c.name">
          <button :class="{ active: category === c.name }" @click="category = c.name">
            {{ c.name }} <span class="count">{{ c.count }}</span>
          </button>
        </li>
      </ul>
    </aside>

    <!-- Add / edit product -->
    <Modal v-if="form" :title="form.id ? 'Edit product' : 'Add product'" @close="form = null">
      <form id="product-form" class="grid" @submit.prevent="save">
        <label class="field span2">Name <input class="input" v-model.trim="form.name" required maxlength="100" /></label>
        <label class="field">SKU <input class="input" v-model.trim="form.sku" maxlength="40" placeholder="e.g. EGG-001" /></label>
        <label class="field">Category
          <input class="input" v-model.trim="form.category" list="category-list" maxlength="40" />
          <datalist id="category-list"><option v-for="c in categories" :key="c.name" :value="c.name" /></datalist>
        </label>
        <label class="field">Unit price (LKR)
          <input class="input" type="number" min="0" step="0.01" v-model.number="form.price" required :disabled="!can('products:price')" />
          <span v-if="!can('products:price')" class="lock">🔒 Only managers can change prices</span>
        </label>
        <label class="field">Quantity
          <input class="input" type="number" min="0" step="1" v-model.number="form.quantity" required :disabled="!!form.id" />
          <span v-if="form.id" class="lock">Use Receive or Count to change stock</span>
        </label>
        <label class="field">Reorder level <input class="input" type="number" min="0" step="1" v-model.number="form.reorder_level" required /></label>
      </form>
      <template #footer>
        <button class="btn" @click="form = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="product-form" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
      </template>
    </Modal>

    <!-- Receive delivery / stock count -->
    <Modal v-if="stockForm" :title="stockForm.mode === 'receive' ? 'Receive delivery' : 'Stock count'" @close="stockForm = null">
      <form id="stock-form" class="grid" @submit.prevent="saveStock">
        <label class="field span2">Product
          <select class="input" v-model="stockForm.productId" required>
            <option value="" disabled>Choose a product…</option>
            <option v-for="p in sortedProducts" :key="p.id" :value="p.id">{{ p.name }} {{ p.sku ? `(${p.sku})` : '' }} · {{ p.quantity }} in stock</option>
          </select>
        </label>
        <template v-if="stockForm.mode === 'receive'">
          <label class="field">Quantity received <input class="input" type="number" min="1" step="1" v-model.number="stockForm.quantity" required /></label>
          <label class="field">Supplier / delivery ref. <input class="input" v-model.trim="stockForm.reference" maxlength="100" placeholder="e.g. PO-1042" /></label>
        </template>
        <template v-else>
          <label class="field">Counted on shelf <input class="input" type="number" min="0" step="1" v-model.number="stockForm.counted" required /></label>
          <label class="field">Note <input class="input" v-model.trim="stockForm.note" maxlength="200" placeholder="Optional" /></label>
        </template>
        <p v-if="stockPreview" class="span2 preview">{{ stockPreview }}</p>
      </form>
      <template #footer>
        <button class="btn" @click="stockForm = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="stock-form" :disabled="saving">
          {{ saving ? 'Saving…' : stockForm.mode === 'receive' ? 'Receive stock' : 'Save count' }}
        </button>
      </template>
    </Modal>

    <!-- Confirm delete -->
    <Modal v-if="confirmDelete" title="Delete products" @close="confirmDelete = false">
      <p>Delete {{ selected.length }} selected product{{ selected.length > 1 ? 's' : '' }}? This can't be undone.</p>
      <template #footer>
        <button class="btn" @click="confirmDelete = false">Cancel</button>
        <button class="btn btn-danger" @click="deleteSelected">Delete</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import api from '../api';
import DataTable from '../components/DataTable.vue';
import Modal from '../components/Modal.vue';
import { errorText, money, stockStatus, store } from '../store';

const can = (p) => store.can(p);
const query = ref('');
const selected = ref([]);
const filter = ref('all');
const category = ref('');
const form = ref(null);
const stockForm = ref(null);
const saving = ref(false);
const confirmDelete = ref(false);

const statusLabel = { ok: 'In stock', low: 'Low stock', out: 'Out of stock' };

const columns = computed(() => [
  { key: 'name', label: 'Product / SKU', sortable: true },
  { key: 'category', label: 'Category', sortable: true },
  { key: 'price', label: 'Unit price', sortable: true, align: 'right' },
  { key: 'quantity', label: 'Stock', sortable: true, align: 'center' },
  { key: 'status', label: 'Status', sortable: true, sortValue: (r) => r.quantity - r.reorder_level },
  { key: 'value', label: 'Stock value', sortable: true, align: 'right', sortValue: (r) => r.price * r.quantity },
  (can('products:write') || can('stock:receive') || can('stock:count')) && { key: 'actions', label: '', align: 'right' },
].filter(Boolean));

const lowCount = computed(() => store.products.filter((p) => stockStatus(p) !== 'ok').length);
const sortedProducts = computed(() => [...store.products].sort((a, b) => a.name.localeCompare(b.name)));

const stockFilters = computed(() => {
  const c = { ok: 0, low: 0, out: 0 };
  store.products.forEach((p) => c[stockStatus(p)]++);
  return [
    { key: 'all', label: 'All products', count: store.products.length },
    { key: 'ok', label: 'In stock', count: c.ok },
    { key: 'low', label: 'Low stock', count: c.low },
    { key: 'out', label: 'Out of stock', count: c.out },
  ];
});

const categories = computed(() => {
  const counts = {};
  store.products.forEach((p) => { counts[p.category] = (counts[p.category] || 0) + 1; });
  return Object.entries(counts).sort().map(([name, count]) => ({ name, count }));
});

const rows = computed(() => store.products.filter((p) =>
  (filter.value === 'all' || stockStatus(p) === filter.value) &&
  (!category.value || p.category === category.value)));

// ----- product form -----
const blank = () => ({ name: '', sku: '', category: 'General', price: 0, quantity: 0, reorder_level: 10 });
const openAdd = () => { form.value = blank(); };
const openEdit = (p) => { form.value = { ...p }; };

async function save() {
  saving.value = true;
  const { id, quantity, ...rest } = form.value;
  const body = id ? rest : { ...rest, quantity };
  if (!can('products:price')) delete body.price;
  try {
    if (id) await api.put(`/inventory/products/${id}`, body);
    else await api.post('/inventory/products', body);
    store.toast(id ? 'Product updated' : 'Product added');
    form.value = null;
    await Promise.all([store.loadProducts(), store.loadMovements()]);
  } catch (e) {
    store.toast(errorText(e, 'Could not save product'), 'error');
  } finally {
    saving.value = false;
  }
}

// ----- receive / count -----
function openStock(mode, product = null) {
  stockForm.value = {
    mode, productId: product?.id || '', quantity: 1, reference: '',
    counted: product?.quantity ?? 0, note: '',
  };
}

const stockPreview = computed(() => {
  const f = stockForm.value;
  const p = f && store.products.find((x) => x.id === f.productId);
  if (!p) return '';
  if (f.mode === 'receive') return `${p.quantity} → ${p.quantity + (f.quantity || 0)} in stock`;
  const diff = (f.counted ?? 0) - p.quantity;
  return diff === 0 ? 'Matches the system — no change.' : `System has ${p.quantity}; this ${diff > 0 ? 'adds' : 'removes'} ${Math.abs(diff)}.`;
});

async function saveStock() {
  const f = stockForm.value;
  saving.value = true;
  try {
    if (f.mode === 'receive') {
      await api.post(`/inventory/products/${f.productId}/receive`, { quantity: f.quantity, reference: f.reference });
      store.toast(`Received ${f.quantity} units`);
    } else {
      await api.post(`/inventory/products/${f.productId}/count`, { counted: f.counted, note: f.note });
      store.toast('Stock count saved');
    }
    stockForm.value = null;
    await Promise.all([store.loadProducts(), store.loadMovements()]);
  } catch (e) {
    store.toast(errorText(e, 'Could not update stock'), 'error');
  } finally {
    saving.value = false;
  }
}

async function adjust(p, delta) {
  try {
    const { data } = await api.post(`/inventory/products/${p.id}/adjust`, { delta, note: 'Quick adjust' });
    p.quantity = data.quantity;
    store.loadMovements();
  } catch (e) {
    store.toast(errorText(e, 'Could not update stock'), 'error');
  }
}

async function deleteSelected() {
  const ids = [...selected.value];
  confirmDelete.value = false;
  const results = await Promise.allSettled(ids.map((id) => api.delete(`/inventory/products/${id}`)));
  const failed = results.filter((r) => r.status === 'rejected').length;
  store.toast(failed ? `${failed} product(s) could not be deleted` : `Deleted ${ids.length} product(s)`, failed ? 'error' : 'ok');
  selected.value = [];
  await store.loadProducts();
}

async function refresh() {
  await Promise.all([store.loadProducts(), store.loadMovements()]);
  store.toast('Inventory refreshed');
}

// Shortcuts from the Home page
onMounted(() => {
  const nav = store.navFilter;
  store.navFilter = null;
  if (nav === 'low') filter.value = 'low';
  if (nav === 'receive' && can('stock:receive')) openStock('receive');
  if (nav === 'count' && can('stock:count')) openStock('count');
});
</script>

<style scoped>
.sku { font-size: 13px; }
.qty { display: inline-flex; align-items: center; gap: 6px; }
.n { display: inline-block; min-width: 34px; text-align: center; font-variant-numeric: tabular-nums; font-weight: 600; }
.row-actions { display: inline-flex; gap: 6px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.span2 { grid-column: span 2; }
.lock { font-weight: 500; font-size: 12.5px; }
.preview { margin: 0; padding: 10px 12px; border-radius: 8px; background: var(--surface-2); font-weight: 600; }
@media (max-width: 520px) { .grid { grid-template-columns: 1fr; } .span2 { grid-column: auto; } }
</style>
