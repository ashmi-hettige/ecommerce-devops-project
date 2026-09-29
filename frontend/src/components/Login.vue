<template>
  <!-- ---------- Sign in ---------- -->
  <AuthCard v-if="mode === 'login'" title="Login" headline="Welcome back!" tagline="Secure your stock.">
    <form @submit.prevent="handleLogin" novalidate>
      <div class="af">
        <input id="lg-user" v-model.trim="username" placeholder=" " autocomplete="username" required />
        <label for="lg-user">Username</label>
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5Zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5Z"/></svg>
      </div>
      <div class="af">
        <input id="lg-pass" v-model="password" :type="show ? 'text' : 'password'" placeholder=" " autocomplete="current-password" required />
        <label for="lg-pass">Password</label>
        <button v-if="password" type="button" class="toggle" @click="show = !show">{{ show ? 'Hide' : 'Show' }}</button>
        <svg v-else class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 9V7a5 5 0 0 0-10 0v2H5v13h14V9Zm-8-2a3 3 0 0 1 6 0v2H9Zm3 11a2 2 0 1 1 2-2 2 2 0 0 1-2 2Z"/></svg>
      </div>

      <button type="submit" class="neon-btn" :disabled="loading">
        {{ loading ? 'Signing in…' : 'Login' }}
      </button>

      <p v-if="message" class="auth-msg" :class="messageType" role="alert">{{ message }}</p>
      <p class="auth-switch">Don't have an account? <button type="button" @click="switchTo('register')">Register</button></p>
    </form>
  </AuthCard>

  <!-- ---------- Register (needs admin approval) ---------- -->
  <AuthCard v-else title="Register" headline="Join the team!" tagline="Request access. An admin will approve it.">
    <form @submit.prevent="handleRegister" novalidate>
      <div class="af">
        <input id="rg-name" v-model.trim="reg.full_name" placeholder=" " autocomplete="name" maxlength="80" />
        <label for="rg-name">Full name</label>
      </div>
      <div class="af">
        <input id="rg-user" v-model.trim="reg.username" placeholder=" " autocomplete="username" maxlength="32" required />
        <label for="rg-user">Username</label>
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 12a5 5 0 1 0-5-5 5 5 0 0 0 5 5Zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5Z"/></svg>
      </div>
      <div class="af">
        <input id="rg-pass" v-model="reg.password" type="password" placeholder=" " autocomplete="new-password" required />
        <label for="rg-pass">Password</label>
      </div>
      <div class="af">
        <input id="rg-pass2" v-model="reg.confirm" type="password" placeholder=" " autocomplete="new-password" required />
        <label for="rg-pass2">Confirm password</label>
      </div>
      <ul class="rules-mini">
        <li v-for="r in rules" :key="r.text" :class="{ ok: r.ok }">{{ r.ok ? '✓' : '•' }} {{ r.text }}</li>
      </ul>

      <button type="submit" class="neon-btn" :disabled="loading || !rules.every((r) => r.ok)">
        {{ loading ? 'Creating…' : 'Register' }}
      </button>

      <p v-if="message" class="auth-msg" :class="messageType" role="alert">{{ message }}</p>
      <p class="auth-switch">Already have an account? <button type="button" @click="switchTo('login')">Login</button></p>
    </form>
  </AuthCard>
</template>

<script setup>
import { computed, ref } from 'vue';
import api from '../api';
import AuthCard from './AuthCard.vue';
import { errorText, store } from '../store';

const mode = ref('login');
const username = ref('');
const password = ref('');
const show = ref(false);
const loading = ref(false);
const message = ref('');
const messageType = ref('error');
const reg = ref({ full_name: '', username: '', password: '', confirm: '' });

// Same rules the auth-service enforces (the server is the real check)
const rules = computed(() => {
  const r = reg.value;
  return [
    { text: '3+ char username', ok: /^[a-zA-Z0-9_.-]{3,32}$/.test(r.username) },
    { text: '8+ characters', ok: r.password.length >= 8 },
    { text: 'a letter', ok: /[A-Za-z]/.test(r.password) },
    { text: 'a number', ok: /\d/.test(r.password) },
    { text: 'not your username', ok: !!r.password && r.password.toLowerCase() !== r.username.toLowerCase() },
    { text: 'passwords match', ok: !!r.password && r.password === r.confirm },
  ];
});

function switchTo(m) {
  mode.value = m;
  message.value = '';
}

async function handleLogin() {
  if (!username.value || !password.value) {
    messageType.value = 'error';
    message.value = 'Enter your username and password.';
    return;
  }
  loading.value = true;
  message.value = '';
  try {
    const { data } = await api.post('/auth/login', { username: username.value, password: password.value });
    password.value = '';
    store.setToken(data.access_token);
  } catch (error) {
    const status = error.response?.status;
    // 401 wrong password, 403 disabled / awaiting approval, 423 locked
    messageType.value = 'error';
    message.value = [401, 403, 423].includes(status)
      ? error.response.data.detail
      : 'Auth service unavailable. Please try again.';
  } finally {
    loading.value = false;
  }
}

async function handleRegister() {
  loading.value = true;
  message.value = '';
  try {
    const { full_name, username: u, password: p } = reg.value;
    await api.post('/auth/register', { full_name, username: u, password: p });
    username.value = u;
    reg.value = { full_name: '', username: '', password: '', confirm: '' };
    mode.value = 'login';
    messageType.value = 'ok';
    message.value = 'Account created. An admin must approve it before you can sign in.';
  } catch (e) {
    messageType.value = 'error';
    message.value = errorText(e, 'Could not register. Is the auth service running?');
  } finally {
    loading.value = false;
  }
}
</script>
