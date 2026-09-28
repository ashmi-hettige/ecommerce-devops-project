<template>
  <div class="insights">
    <div class="kpis">
      <div class="card kpi" v-for="k in kpis" :key="k.label">
        <span class="label">{{ k.label }}</span>
        <span class="value">{{ k.value }}</span>
        <span class="hint" :class="k.tone">{{ k.hint }}</span>
      </div>
    </div>

    <div class="grid">
      <section class="card panel">
        <div class="head"><h3>Needs restocking</h3>
          <button class="btn btn-sm" @click="$emit('go', 'inventory')">Open inventory →</button></div>
        <table class="list" v-if="lowStock.length"><tbody>
          <tr v-for="p in lowStock" :key="p.id">
            <td><strong>{{ p.name }}</strong> <span class="muted">{{ p.sku }}</span></td>
            <td class="num">{{ p.quantity }} / {{ p.reorder_level }}</td>
            <td class="num"><span class="pill" :class="p.quantity === 0 ? 'pill-out' : 'pill-low'">{{ p.quantity === 0 ? 'Out' : 'Low' }}</span></td>
          </tr>
        </tbody></table>
        <p v-else class="muted empty">All products are above their reorder level.</p>
      </section>

      <section class="card panel">
        <div class="head"><h3>Orders by status</h3>
          <button class="btn btn-sm" @click="$emit('go', 'orders')">Open orders →</button></div>
        <div class="bars">
          <div class="bar-row" v-for="s in statusBars" :key="s.key">
            <span class="bar-label">{{ s.label }}</span>
            <div class="track"><div class="fill" :class="`fill-${s.key}`" :style="{ width: s.pct + '%' }"></div></div>
            <span class="num">{{ s.count }}</span>
          </div>
        </div>
      </section>

      <section class="card panel">
        <div class="head"><h3>Top products by stock value</h3></div>
        <div class="bars" v-if="topValue.length">
          <div class="bar-row" v-for="p in topValue" :key="p.id">
            <span class="bar-label" :title="p.name">{{ p.name }}</span>
            <div class="track"><div class="fill fill-value" :style="{ width: p.pct + '%' }"></div></div>
            <span class="num">{{ money(p.value) }}</span>
          </div>
        </div>
        <p v-else class="muted empty">Add prices to your products to see stock value.</p>
      </section>

      <section class="card panel">
        <div class="head"><h3>Recent orders</h3></div>
        <table class="list" v-if="recent.length"><tbody>
          <tr v-for="o in recent" :key="o.id">
            <td><strong>#{{ o.order_no }}</strong> <span class="muted">{{ o.customer }}</span></td>
            <td class="num">{{ money(o.total) }}</td>
            <td class="num"><span class="pill" :class="`pill-${o.status}`">{{ o.status[0].toUpperCase() + o.status.slice(1) }}</span></td>
          </tr>
        </tbody></table>
        <p v-else class="muted empty">No orders yet.</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { money, stockStatus, store } from '../store';

defineEmits(['go']);

const kpis = computed(() => {
  const p = store.products, o = store.orders;
  const units = p.reduce((s, x) => s + x.quantity, 0);
  const value = p.reduce((s, x) => s + x.price * x.quantity, 0);
  const low = p.filter((x) => stockStatus(x) !== 'ok').length;
  const revenue = o.reduce((s, x) => s + x.total, 0);
  const pending = o.filter((x) => x.status !== 'shipped').length;
  return [
    { label: 'Products', value: p.length, hint: `${units.toLocaleString()} units in stock` },
    { label: 'Inventory value', value: money(value), hint: 'at unit price' },
    { label: 'Low / out of stock', value: low, hint: low ? 'need restocking' : 'all healthy', tone: low ? 'warn' : 'good' },
    { label: 'Orders', value: o.length, hint: `${pending} not shipped yet`, tone: pending ? 'warn' : 'good' },
    { label: 'Revenue', value: money(revenue), hint: 'all orders' },
  ];
});

const lowStock = computed(() => store.products
  .filter((p) => stockStatus(p) !== 'ok')
  .sort((a, b) => a.quantity - b.quantity).slice(0, 6));

const statusBars = computed(() => {
  const total = store.orders.length || 1;
  return ['pending', 'picked', 'shipped'].map((key) => {
    const count = store.orders.filter((o) => o.status === key).length;
    return { key, label: key[0].toUpperCase() + key.slice(1), count, pct: (count / total) * 100 };
  });
});

const topValue = computed(() => {
  const rows = store.products.map((p) => ({ ...p, value: p.price * p.quantity }))
    .filter((p) => p.value > 0).sort((a, b) => b.value - a.value).slice(0, 5);
  const max = rows[0]?.value || 1;
  return rows.map((r) => ({ ...r, pct: (r.value / max) * 100 }));
});

const recent = computed(() => [...store.orders].sort((a, b) => b.order_no - a.order_no).slice(0, 5));
</script>

<style scoped>
.insights { display: grid; gap: 20px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr)); gap: 14px; }
.kpi { padding: 16px 18px; display: grid; gap: 4px; min-width: 0; }
.kpi .label { font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.kpi .value { font-size: clamp(18px, 1.9vw, 24px); overflow-wrap: anywhere; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi .hint { font-size: 12.5px; color: var(--muted); }
.kpi .hint.warn { color: var(--warn); }
.kpi .hint.good { color: var(--primary); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr)); gap: 20px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.list { width: 100%; border-collapse: collapse; }
.list td { padding: 8px 0 8px 10px; border-bottom: 1px solid var(--border); }
.list td:first-child { padding-left: 0; }
.list tr:last-child td { border-bottom: 0; }
.empty { padding: 16px 0; }
.bars { display: grid; gap: 12px; }
.bar-row { display: grid; grid-template-columns: minmax(80px, 130px) 1fr auto; gap: 10px; align-items: center; }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { height: 10px; border-radius: 5px; background: var(--surface-2); overflow: hidden; }
.fill { height: 100%; border-radius: 5px; transition: width .4s; }
.fill-pending { background: var(--warn); }
.fill-picked { background: var(--info); }
.fill-shipped, .fill-value { background: var(--primary); }
@media (max-width: 480px) { .grid { grid-template-columns: 1fr; } }
</style>
