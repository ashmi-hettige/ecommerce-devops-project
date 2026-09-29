<!--
  Neon split-panel card used by Login, Register and the forced password change.
  Left: the form (slot). Right: a diagonal glowing panel with a headline.
-->
<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="form-side">
        <h2 class="title">{{ title }}</h2>
        <slot />
      </div>
      <div class="panel-side" aria-hidden="true"></div>
      <svg class="edge" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <line x1="38" y1="0" x2="84" y2="100" />
      </svg>
      <div class="panel-text">
        <h1>{{ headline }}</h1>
        <p>{{ tagline }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ title: String, headline: String, tagline: String });
</script>

<style>
/* Not scoped: the form fields inside the slot use these classes too */
.auth-page {
  /* same dark green palette as the rest of the app */
  --neon: var(--primary);        /* #3fae86 */
  --neon-2: #1f7a5c;
  --deep: var(--surface);        /* #17201d */
  --ink: var(--text);
  min-height: 100vh; display: grid; place-items: center; padding: 20px;
  background: radial-gradient(1200px 600px at 70% 20%, #16302a 0%, var(--bg) 60%);
  color: var(--ink);
}
.auth-card {
  position: relative; display: grid; grid-template-columns: 1fr 1fr;
  width: min(760px, 100%); min-height: 440px; overflow: hidden;
  border: 2px solid var(--neon); border-radius: 4px;
  background: var(--deep);
  box-shadow: 0 0 22px rgba(63, 174, 134, .45), inset 0 0 12px rgba(63, 174, 134, .06);
}
.form-side { position: relative; z-index: 2; padding: 44px 40px 36px; display: flex; flex-direction: column; justify-content: center; }
.title { color: var(--text); text-align: center; font-size: 26px; margin: 0 0 22px; }

.panel-side {
  position: absolute; inset: 0; z-index: 1;
  background: linear-gradient(135deg, var(--deep) 30%, #1f5e48 70%, var(--neon) 100%);
  clip-path: polygon(38% 0, 100% 0, 100% 100%, 84% 100%);
}
/* the glowing diagonal edge */
.edge { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none; }
.edge line { stroke: var(--neon); stroke-width: 2; vector-effect: non-scaling-stroke; filter: drop-shadow(0 0 3px var(--neon)); }
.panel-text { position: absolute; z-index: 3; right: 34px; top: 50%; transform: translateY(-50%); text-align: right; max-width: 38%; }
.panel-text h1 { margin: 0 0 8px; font-size: 38px; line-height: 1.15; font-weight: 800; color: var(--text); text-transform: uppercase; letter-spacing: .5px; }
.panel-text p { margin: 0; font-size: 15px; color: var(--ink); opacity: .9; }

/* Floating-label underline inputs */
.af { position: relative; margin: 0 0 26px; }
.af input {
  width: 100%; height: 44px; padding: 16px 28px 4px 0; border: 0; border-bottom: 2px solid var(--muted);
  background: transparent; color: var(--text); font: inherit; font-size: 15px; outline: none;
  transition: border-color .2s;
}
.af label {
  position: absolute; left: 0; top: 50%; transform: translateY(-40%);
  color: var(--text); font-size: 15px; pointer-events: none; transition: .2s;
}
.af input:focus, .af input:not(:placeholder-shown) { border-bottom-color: var(--neon); }
.af input:focus ~ label, .af input:not(:placeholder-shown) ~ label {
  top: 0; transform: none; font-size: 12px; color: var(--neon);
}
.af .icon { position: absolute; right: 0; top: 50%; transform: translateY(-35%); width: 18px; height: 18px; color: var(--text); }
.af .toggle {
  position: absolute; right: 0; top: 50%; transform: translateY(-35%);
  border: 0; background: none; color: var(--neon); font: inherit; font-size: 12px; cursor: pointer; padding: 0;
}

.neon-btn {
  width: 100%; height: 46px; border-radius: 40px; cursor: pointer;
  border: 2px solid var(--neon); color: #0b1210; font: inherit; font-size: 16px; font-weight: 700;
  background: linear-gradient(to bottom, #6fd4ae, var(--neon) 45%, var(--neon-2));
  box-shadow: 0 0 12px rgba(63, 174, 134, .45);
  transition: box-shadow .2s, transform .1s;
}
.neon-btn:hover:not(:disabled) { box-shadow: 0 0 20px rgba(63, 174, 134, .8); }
.neon-btn:active:not(:disabled) { transform: translateY(1px); }
.neon-btn:disabled { opacity: .55; cursor: not-allowed; }

.auth-switch { margin: 18px 0 0; text-align: center; font-size: 14px; color: var(--text); }
.auth-switch button { border: 0; background: none; padding: 0; color: var(--neon); font: inherit; font-weight: 700; cursor: pointer; }
.auth-switch button:hover { text-decoration: underline; }
.auth-msg { margin: 14px 0 0; text-align: center; font-size: 13.5px; font-weight: 600; }
.auth-msg.error { color: var(--danger); }
.auth-msg.ok { color: var(--primary); }
.auth-note { margin: 10px 0 0; text-align: center; font-size: 12px; color: var(--muted); }
.rules-mini { list-style: none; margin: -12px 0 18px; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--muted); }
.rules-mini li.ok { color: var(--neon); }

@media (max-width: 680px) {
  .auth-card { grid-template-columns: 1fr; min-height: 0; }
  .panel-side { position: relative; order: -1; height: 150px; clip-path: none; border-left: 0; border-bottom: 2px solid var(--neon);
    background: linear-gradient(120deg, var(--deep) 10%, #1f5e48 60%, var(--neon)); }
  .edge { display: none; }
  .panel-text { top: 75px; right: 24px; max-width: 80%; }
  .panel-text h1 { font-size: 28px; }
  .form-side { padding: 28px 24px; }
}
</style>
