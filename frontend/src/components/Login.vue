<template>
  <div class="wrap">
    <form class="card login" @submit.prevent="handleLogin">
      <div class="brand">
        <span class="logo" aria-hidden="true">▣</span>
        <div>
          <small>Scalable E-Commerce</small>
          <strong>Inventory Management</strong>
        </div>
      </div>
      <p class="muted">Sign in to manage stock and orders.</p>

      <label class="field">Username
        <input class="input" v-model="username" autocomplete="username" required />
      </label>
      <label class="field">Password
        <input class="input" v-model="password" type="password" autocomplete="current-password" required />
      </label>

      <button type="submit" class="btn btn-primary full" :disabled="loading">
        {{ loading ? 'Signing in…' : 'Sign in' }}
      </button>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import api from '../api';

const emit = defineEmits(['login-success']);

const username = ref('');
const password = ref('');
const errorMessage = ref('');
const loading = ref(false);

const handleLogin = async () => {
  loading.value = true;
  errorMessage.value = '';
  try {
    const response = await api.post('/auth/login', {
      username: username.value,
      password: password.value
    });
    emit('login-success', response.data.access_token);
  } catch (error) {
    // Distinguish "wrong password" from "service down"
    errorMessage.value = error.response?.status === 401
      ? 'Invalid username or password.'
      : 'Auth service unavailable. Please try again.';
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.wrap { min-height: 100vh; display: grid; place-items: center; padding: 16px;
  background: linear-gradient(160deg, var(--header) 0 38%, var(--bg) 38%); }
.login { width: 100%; max-width: 380px; padding: 28px; display: grid; gap: 16px; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 10px;
  background: var(--primary); color: #fff; font-size: 22px; }
.brand small { display: block; font-size: 12px; color: var(--muted); }
.brand strong { font-size: 19px; }
.muted { margin: 0; }
.full { width: 100%; justify-content: center; height: 40px; }
.error { margin: 0; color: var(--danger); text-align: center; font-weight: 550; }
</style>
