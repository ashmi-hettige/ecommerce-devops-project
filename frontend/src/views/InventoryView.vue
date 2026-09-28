<template>
  <div class="page">
    <section class="card panel">
      <h2>Inventory</h2>
      <p class="muted">{{ store.products.length }} products · {{ lowCount }} need restocking</p>

      <div class="toolbar">
        <input class="input search" v-model="query" placeholder="Search name, SKU, category…" />
        <span class="spacer"></span>
        <button class="btn btn-primary" @click="openAdd">＋ Add Product</button>
        <button class="btn btn-danger" :disabled="!selected.length" @click="confirmDelete = true">
          Delete Selected{{ selected.length ? ` (${selected.length})` : '' }}
        </button>
        <button class="btn" @click="refresh">⟳ Refresh</button>
      </div>

      <DataTable :rows="rows" :columns="columns" :query="query" :search-keys="['name', 'sku', 'category']"
                 v-model:selected="selected" :default-sort="{ key: 'name', dir: 'asc' }"
                 empty-text="No products match. Add one with “Add Product”.">
        <template #cell-name="{ row }">
          <strong>{{ row.name }}</strong>
          <div class="sku muted">{{ row.sku || 'No SKU' }}</div>
        </template>
        <template #cell-price="{ row }">{{ money(row.price) }}</template>
        <template #cell-quantity="{ row }">
          <span class="qty">
            <button class="btn btn-sm btn-icon" :disabled="row.quantity === 0" @click="adjust(row, -1)" aria-label="Decrease">−</button>
            <span class="n">{{ row.quantity }}</span>
            <button class="btn btn-sm btn-icon" @click="adjust(row, 1)" aria-label="Increase">+</button>
          </span>
        </template>
        <template #cell-status="{ row }">
          <span class="pill" :class="`pill-${stockStatus(row)}`">{{ statusLabel[stockStatus(row)] }}</span>
        </template>
        <template #cell-value="{ row }">{{ money(row.price * row.quantity) }}</template>
        <template #cell-actions="{ row }">
          <button class="btn btn-sm" @click="openEdit(row)">Edit</button>
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
        <label class="field">Unit price (LKR) <input class="input" type="number" min="0" step="0.01" v-model.number="form.price" required /></label>
        <label class="field">Quantity <input class="input" type="number" min="0" step="1" v-model.number="form.quantity" required /></label>
        <label class="field">Reorder level <input class="input" type="number" min="0" step="1" v-model.number="form.reorder_level" required /></label>
      </form>
      <template #footer>
        <button class="btn" @click="form = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="product-form" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save' }}
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
import { computed, ref } from 'vue';
import api from '../api';
import DataTable from '../components/DataTable.vue';
import Modal from '../components/Modal.vue';
import { errorText, money, stockStatus, store } from '../store';

const query = ref('');
const selected = ref([]);
const filter = ref('all');
const category = ref('');
const form = ref(null);
const saving = ref(false);
const confirmDelete = ref(false);

const statusLabel = { ok: 'In stock', low: 'Low stock', out: 'Out of stock' };

const columns = [
  { key: 'name', label: 'Product / SKU', sortable: true },
  { key: 'category', label: 'Category', sortable: true },
  { key: 'price', label: 'Unit price', sortable: true, align: 'right' },
  { key: 'quantity', label: 'Stock', sortable: true, align: 'center' },
  { key: 'status', label: 'Status', sortable: true, sortValue: (r) => r.quantity - r.reorder_level },
  { key: 'value', label: 'Stock value', sortable: true, align: 'right', sortValue: (r) => r.price * r.quantity },
  { key: 'actions', label: '', align: 'right' },
];

const lowCount = computed(() => store.products.filter((p) => stockStatus(p) !== 'ok').length);

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

const blank = () => ({ name: '', sku: '', category: 'General', price: 0, quantity: 0, reorder_level: 10 });
const openAdd = () => { form.value = blank(); };
const openEdit = (p) => { form.value = { ...p }; };

async function save() {
  saving.value = true;
  const { id, ...body } = form.value;
  try {
    if (id) await api.put(`/inventory/products/${id}`, body);
    else await api.post('/inventory/products', body);
    store.toast(id ? 'Product updated' : 'Product added');
    form.value = null;
    await store.loadProducts();
  } catch (e) {
    store.toast(errorText(e, 'Could not save product'), 'error');
  } finally {
    saving.value = false;
  }
}

async function adjust(p, delta) {
  try {
    const { data } = await api.post(`/inventory/products/${p.id}/adjust`, { delta });
    p.quantity = data.quantity;
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
  await store.loadProducts();
  store.toast('Inventory refreshed');
}
</script>

<style scoped>
.sku { font-size: 12px; }
.qty { display: inline-flex; align-items: center; gap: 6px; }
.qty .n { min-width: 34px; text-align: center; font-variant-numeric: tabular-nums; font-weight: 600; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.span2 { grid-column: span 2; }
</style>
