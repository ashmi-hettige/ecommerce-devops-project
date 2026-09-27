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
      <button type="submit" style="width: 100%; padding: 10px; background-color: #4CAF50; color: white; border: none; cursor: pointer;">Login</button>
    </form>
    <p v-if="errorMessage" style="color: red; text-align: center;">{{ errorMessage }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import axios from 'axios';

const emit = defineEmits(['login-success']);

const username = ref('');
const password = ref('');
const errorMessage = ref('');
const API_URL = 'http://127.0.0.1:8000';

const handleLogin = async () => {
  try {
    const response = await axios.post(`${API_URL}/login`, {
      username: username.value,
      password: password.value
    });
    // Send the token up to the parent App.vue
    emit('login-success', response.data.access_token);
    errorMessage.value = '';
  } catch (error) {
    errorMessage.value = 'Invalid credentials. Use admin / admin123';
  }
};
</script>