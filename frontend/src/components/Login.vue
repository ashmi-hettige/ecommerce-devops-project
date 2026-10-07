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
      <p v-if="reg.username && !check.username" class="field-hint error">Use 3+ letters, numbers, _ . or -</p>
      <div class="af">
        <input id="rg-pass" v-model="reg.password" type="password" placeholder=" " autocomplete="new-password" required
               @focus="pwFocus = true" @blur="pwFocus = false" />
        <label for="rg-pass">Password</label>
      </div>
      <!-- Shown while typing the password; each part turns green once it's met -->
      <p v-if="pwFocus || (reg.password && !passwordOk)" class="field-hint">
        Use <span :class="{ ok: check.length }">8+ characters</span>,
        <span :class="{ ok: check.letter }">a letter</span>,
        <span :class="{ ok: check.number }">a number</span>
      </p>
      <p v-if="reg.password && reg.username && !check.notUsername" class="field-hint error">Password can't be your username</p>
      <div class="af">
        <input id="rg-pass2" v-model="reg.confirm" type="password" placeholder=" " autocomplete="new-password" required />
        <label for="rg-pass2">Confirm password</label>
      </div>
      <p v-if="reg.confirm && !check.match" class="field-hint error">Passwords don't match</p>

      <button type="submit" class="neon-btn" :disabled="loading || !Object.values(check).every(Boolean)">
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
const pwFocus = ref(false);

// Same rules the auth-service enforces (the server is the real check)
const check = computed(() => {
  const r = reg.value;
  return {
    username: /^[a-zA-Z0-9_.-]{3,32}$/.test(r.username),
    length: r.password.length >= 8,
    letter: /[A-Za-z]/.test(r.password),
    number: /\d/.test(r.password),
    notUsername: !!r.password && r.password.toLowerCase() !== r.username.toLowerCase(),
    match: !!r.password && r.password === r.confirm,
  };
});
const passwordOk = computed(() => check.value.length && check.value.letter && check.value.number);

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
