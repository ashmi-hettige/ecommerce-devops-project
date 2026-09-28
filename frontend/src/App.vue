<template>
  <Login v-if="!token" @login-success="loginUser" />
  <AppShell v-else @logout="logoutUser" />
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue';
import Login from './components/Login.vue';
import AppShell from './components/AppShell.vue';
import { store } from './store';

// Check if a user is already logged in from a previous session
const token = ref(localStorage.getItem('token') || '');

const loginUser = (newToken) => {
  localStorage.setItem('token', newToken);
  token.value = newToken;
};

const logoutUser = () => {
  token.value = '';
  localStorage.removeItem('token');
  store.reset();
};

// api.js fires this when the backend answers 401 (token expired/invalid)
onMounted(() => window.addEventListener('auth-expired', logoutUser));
onUnmounted(() => window.removeEventListener('auth-expired', logoutUser));
</script>
