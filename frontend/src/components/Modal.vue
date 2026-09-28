<template>
  <div class="backdrop" @mousedown.self="$emit('close')">
    <div class="modal card" role="dialog" aria-modal="true" :style="{ maxWidth: width }">
      <header>
        <h3>{{ title }}</h3>
        <button class="btn btn-sm btn-icon" @click="$emit('close')" aria-label="Close">✕</button>
      </header>
      <div class="body"><slot /></div>
      <footer v-if="$slots.footer"><slot name="footer" /></footer>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue';

defineProps({ title: String, width: { type: String, default: '480px' } });
const emit = defineEmits(['close']);

const onKey = (e) => { if (e.key === 'Escape') emit('close'); };
onMounted(() => window.addEventListener('keydown', onKey));
onUnmounted(() => window.removeEventListener('keydown', onKey));
</script>

<style scoped>
.backdrop {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(10, 20, 17, .45);
  display: grid; place-items: center; padding: 16px;
}
.modal { width: 100%; max-height: calc(100vh - 32px); display: flex; flex-direction: column; }
header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.body { padding: 20px; overflow-y: auto; }
footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--border); }
</style>
