<!--
  Change password. Two modes:
    forced  full-page neon card, shown after an admin created/reset the account (can't be skipped)
    normal  plain form inside a modal, opened from the header
-->
<template>
  <AuthCard v-if="forced" title="New password" headline="Make it yours!" tagline="Your admin set a temporary password.">
    <form @submit.prevent="submit" novalidate>
      <div class="af">
        <input id="cp-cur" v-model="current" type="password" placeholder=" " autocomplete="current-password" required />
        <label for="cp-cur">Temporary password</label>
      </div>
      <div class="af">
        <input id="cp-new" v-model="next" type="password" placeholder=" " autocomplete="new-password" required />
        <label for="cp-new">New password</label>
      </div>
      <div class="af">
        <input id="cp-new2" v-model="confirm" type="password" placeholder=" " autocomplete="new-password" required />
        <label for="cp-new2">Confirm new password</label>
      </div>
      <ul class="rules-mini">
        <li v-for="r in rules" :key="r.text" :class="{ ok: r.ok }">{{ r.ok ? '✓' : '•' }} {{ r.text }}</li>
      </ul>
      <button type="submit" class="neon-btn" :disabled="!valid || saving">{{ saving ? 'Saving…' : 'Change password' }}</button>
      <p v-if="error" class="auth-msg error" role="alert">{{ error }}</p>
      <p class="auth-switch">Not you? <button type="button" @click="store.logout()">Log out</button></p>
    </form>
  </AuthCard>

  <form v-else class="form" @submit.prevent="submit">
    <label class="field">Current password
      <input class="input" type="password" v-model="current" autocomplete="current-password" required />
    </label>
    <label class="field">New password
      <input class="input" type="password" v-model="next" autocomplete="new-password" required />
    </label>
    <label class="field">Confirm new password
      <input class="input" type="password" v-model="confirm" autocomplete="new-password" required />
    </label>
    <ul class="rules">
      <li v-for="r in rules" :key="r.text" :class="{ ok: r.ok }">{{ r.ok ? '✓' : '○' }} {{ r.text }}</li>
    </ul>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="button" class="btn" @click="$emit('done')">Cancel</button>
      <button type="submit" class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : 'Change password' }}</button>
    </div>
  </form>
</template>

<script setup>
import { computed, ref } from 'vue';
import api from '../api';
import AuthCard from './AuthCard.vue';
import { errorText, store } from '../store';

defineProps({ forced: Boolean });
const emit = defineEmits(['done']);

const current = ref('');
const next = ref('');
const confirm = ref('');
const error = ref('');
const saving = ref(false);

// Same rules the auth-service enforces (the server is the real check)
const rules = computed(() => [
  { text: '8+ characters', ok: next.value.length >= 8 },
  { text: 'a letter', ok: /[A-Za-z]/.test(next.value) },
  { text: 'a number', ok: /\d/.test(next.value) },
  { text: 'not your username', ok: !!next.value && next.value.toLowerCase() !== store.session?.username.toLowerCase() },
  { text: 'passwords match', ok: !!next.value && next.value === confirm.value },
]);
const valid = computed(() => rules.value.every((r) => r.ok) && current.value);

async function submit() {
  saving.value = true;
  error.value = '';
  try {
    const { data } = await api.post('/auth/change-password', {
      current_password: current.value, new_password: next.value,
    });
    store.setToken(data.access_token);
    store.toast('Password changed');
    emit('done');
  } catch (e) {
    error.value = errorText(e, 'Could not change password');
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.form { display: grid; gap: 14px; width: 100%; }
.rules { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 14px; color: var(--muted); }
.rules li.ok { color: var(--primary); }
.error { margin: 0; color: var(--danger); font-weight: 550; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
