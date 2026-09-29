<template>
  <Login v-if="!store.session" />
  <ChangePassword v-else-if="store.session.mustChange" forced />
  <AppShell v-else />
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue';
import Login from './components/Login.vue';
import ChangePassword from './components/ChangePassword.vue';
import AppShell from './components/AppShell.vue';
import { store } from './store';

// api.js fires this when the backend answers 401 (token expired/invalid)
const expired = () => {
  if (store.session) store.toast('Your session has expired. Please sign in again.', 'error');
  store.logout();
};
onMounted(() => window.addEventListener('auth-expired', expired));
onUnmounted(() => window.removeEventListener('auth-expired', expired));
</script>
