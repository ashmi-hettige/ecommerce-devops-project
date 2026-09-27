<template>
  <div style="font-family: Arial, sans-serif;">
    <Login v-if="!token" @login-success="loginUser" />
    <Dashboard v-else @logout="logoutUser" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import Login from './components/Login.vue';
import Dashboard from './components/Dashboard.vue';

// Check if a user is already logged in from a previous session
const token = ref(localStorage.getItem('token') || '');

const loginUser = (newToken) => {
  token.value = newToken;
  localStorage.setItem('token', newToken);
};

const logoutUser = () => {
  token.value = '';
  localStorage.removeItem('token');
};

// api.js fires this when the backend answers 401 (token expired/invalid)
onMounted(() => window.addEventListener('auth-expired', logoutUser));
onUnmounted(() => window.removeEventListener('auth-expired', logoutUser));
</script>
