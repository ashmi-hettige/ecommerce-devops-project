<!--
  Reusable table: row selection, column sorting, text search and pagination.
  Used by both the Inventory and Orders tabs.

  Props:
    rows        array of objects (each needs an `id`)
    columns     [{ key, label, sortable?, align?, width?, sortValue?(row) }]
    query       search text (filters on searchKeys)
    searchKeys  which fields the search looks at
    selected    v-model:selected, array of selected ids
  Custom cell content:  <template #cell-status="{ row }">...</template>
-->
<template>
  <div class="dt">
    <div class="dt-scroll">
      <table>
        <thead>
          <tr>
            <th v-if="selectable" class="check">
              <input type="checkbox" :checked="allOnPageSelected" :indeterminate.prop="someOnPageSelected"
                     @change="togglePage" aria-label="Select all on this page" />
            </th>
            <th v-for="col in columns" :key="col.key" :class="[col.align, { sortable: col.sortable }]"
                :style="col.width && { width: col.width }" @click="col.sortable && sortBy(col.key)">
              {{ col.label }}
              <span v-if="col.sortable" class="arrow" :class="{ on: sortKey === col.key }">
                {{ sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '↕' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in pageRows" :key="row.id" :class="{ selected: selectedSet.has(row.id) }">
            <td v-if="selectable" class="check">
              <input type="checkbox" :checked="selectedSet.has(row.id)" @change="toggleRow(row.id)" aria-label="Select row" />
            </td>
            <td v-for="col in columns" :key="col.key" :class="col.align">
              <slot :name="`cell-${col.key}`" :row="row">{{ row[col.key] }}</slot>
            </td>
          </tr>
          <tr v-if="pageRows.length === 0">
            <td :colspan="columns.length + (selectable ? 1 : 0)" class="empty">{{ emptyText }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="dt-foot">
      <label class="show">
        Show
        <select class="input" v-model.number="pageSize">
          <option v-for="n in [10, 25, 50]" :key="n" :value="n">{{ n }}</option>
        </select>
        entries
        <span class="muted" v-if="filtered.length">· {{ rangeText }}</span>
      </label>
      <nav class="pager" v-if="pageCount > 1">
        <button class="btn btn-sm" :disabled="page === 1" @click="page = 1">First</button>
        <button class="btn btn-sm" :disabled="page === 1" @click="page--">Prev</button>
        <button v-for="n in pageNumbers" :key="n" class="btn btn-sm btn-icon"
                :class="{ 'btn-primary': n === page }" @click="page = n">{{ n }}</button>
        <button class="btn btn-sm" :disabled="page === pageCount" @click="page++">Next</button>
        <button class="btn btn-sm" :disabled="page === pageCount" @click="page = pageCount">Last</button>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';

const props = defineProps({
  rows: { type: Array, required: true },
  columns: { type: Array, required: true },
  query: { type: String, default: '' },
  searchKeys: { type: Array, default: () => [] },
  selectable: { type: Boolean, default: true },
  selected: { type: Array, default: () => [] },
  defaultSort: { type: Object, default: () => ({ key: null, dir: 'asc' }) },
  emptyText: { type: String, default: 'Nothing to show.' },
});
const emit = defineEmits(['update:selected']);

const sortKey = ref(props.defaultSort.key);
const sortDir = ref(props.defaultSort.dir);
const page = ref(1);
const pageSize = ref(10);

const selectedSet = computed(() => new Set(props.selected));

const filtered = computed(() => {
  const q = props.query.trim().toLowerCase();
  if (!q) return props.rows;
  return props.rows.filter((r) => props.searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(q)));
});

const sorted = computed(() => {
  if (!sortKey.value) return filtered.value;
  const col = props.columns.find((c) => c.key === sortKey.value);
  const val = col?.sortValue || ((r) => r[sortKey.value]);
  const dir = sortDir.value === 'asc' ? 1 : -1;
  return [...filtered.value].sort((a, b) => {
    const x = val(a), y = val(b);
    if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir;
    return String(x ?? '').localeCompare(String(y ?? ''), undefined, { numeric: true }) * dir;
  });
});

const pageCount = computed(() => Math.max(1, Math.ceil(sorted.value.length / pageSize.value)));
const pageRows = computed(() => sorted.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
const rangeText = computed(() => {
  const start = (page.value - 1) * pageSize.value + 1;
  return `${start}–${Math.min(start + pageSize.value - 1, sorted.value.length)} of ${sorted.value.length}`;
});
const pageNumbers = computed(() => {
  const start = Math.max(1, Math.min(page.value - 2, pageCount.value - 4));
  return Array.from({ length: Math.min(5, pageCount.value) }, (_, i) => start + i);
});

// Go back to page 1 whenever the filter or page size changes
watch(() => [props.query, pageSize.value, props.rows.length], () => { page.value = 1; });
watch(pageCount, (n) => { if (page.value > n) page.value = n; });

// Drop selections that no longer exist (e.g. after delete)
watch(() => props.rows, (rows) => {
  const ids = new Set(rows.map((r) => r.id));
  const kept = props.selected.filter((id) => ids.has(id));
  if (kept.length !== props.selected.length) emit('update:selected', kept);
});

function sortBy(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  else { sortKey.value = key; sortDir.value = 'asc'; }
}

const allOnPageSelected = computed(() => pageRows.value.length > 0 && pageRows.value.every((r) => selectedSet.value.has(r.id)));
const someOnPageSelected = computed(() => !allOnPageSelected.value && pageRows.value.some((r) => selectedSet.value.has(r.id)));

function toggleRow(id) {
  const next = new Set(props.selected);
  next.has(id) ? next.delete(id) : next.add(id);
  emit('update:selected', [...next]);
}
function togglePage() {
  const next = new Set(props.selected);
  const ids = pageRows.value.map((r) => r.id);
  if (allOnPageSelected.value) ids.forEach((id) => next.delete(id));
  else ids.forEach((id) => next.add(id));
  emit('update:selected', [...next]);
}
</script>

<style scoped>
.dt-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; white-space: nowrap; }
th {
  background: var(--surface-2); border-bottom: 1px solid var(--border);
  font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .04em;
  user-select: none;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--text); }
.arrow { font-size: 11px; opacity: .45; margin-left: 2px; }
.arrow.on { opacity: 1; color: var(--primary); }
td { border-bottom: 1px solid var(--border); height: 50px; }
tbody tr:nth-child(even) td { background: color-mix(in srgb, var(--surface-2) 55%, transparent); }
tbody tr:hover td { background: var(--primary-soft); }
tbody tr.selected td { background: var(--primary-soft); }
tbody tr:last-child td { border-bottom: 0; }
/* extra room after right-aligned numbers so they don't touch the next (left-aligned) column */
.right { text-align: right; padding-right: 32px; }
.right + :not(.right) { padding-left: 40px; }
.center { text-align: center; }
.check { width: 36px; text-align: center; }
.empty { text-align: center; color: var(--muted); padding: 32px; }

.dt-foot { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; margin-top: 12px; }
.show { display: flex; align-items: center; gap: 8px; color: var(--muted); }
.show select { width: 74px; height: 32px; }
.pager { display: flex; gap: 4px; flex-wrap: wrap; }
</style>
