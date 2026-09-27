<template>
  <div style="max-width: 400px; margin: 40px auto; padding: 20px; border: 1px solid #ccc; border-radius: 8px;">
    <h2>🔒 E-Commerce Login</h2>
    <form @submit.prevent="handleLogin">
      <div style="margin-bottom: 10px;">
        <input v-model="username" placeholder="Username" required style="width: 100%; padding: 8px; box-sizing: border-box;" />
      </div>
      <div style="margin-bottom: 10px;">
        <input v-model="password" type="password" placeholder="Password" required style="width: 100%; padding: 8px; box-sizing: border-box;" />
      </div>
      <button type="submit" :disabled="loading" style="width: 100%; padding: 10px; background-color: #4CAF50; color: white; border: none; cursor: pointer;">
        {{ loading ? 'Logging in…' : 'Login' }}
      </button>
    </form>
    <p v-if="errorMessage" style="color: red; text-align: center;">{{ errorMessage }}</p>
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
    // Don't print the password on screen; distinguish "wrong password" from "service down"
    errorMessage.value = error.response?.status === 401
      ? 'Invalid username or password.'
      : 'Auth service unavailable. Please try again.';
  } finally {
    loading.value = false;
  }
};
</script>
