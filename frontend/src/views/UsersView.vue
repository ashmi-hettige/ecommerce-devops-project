<!-- Users & roles: admin only (the auth-service also rejects non-admins). -->
<template>
  <div class="users">
    <section class="card panel">
      <h2>Users</h2>
      <p class="muted">{{ store.users.length }} accounts · {{ activeCount }} active · {{ lockedCount }} locked
        <template v-if="pendingCount"> · <b class="warn">{{ pendingCount }} awaiting approval</b></template></p>

      <div class="toolbar">
        <input class="input search" v-model="query" placeholder="Search user, name, role" />
        <span class="spacer"></span>
        <button class="btn btn-primary" @click="openAdd">＋ Add User</button>
        <button class="btn" @click="refresh">
          <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" />
          </svg>
          Refresh
        </button>
      </div>

      <DataTable :rows="rows" :columns="columns" :query="query" :selectable="false"
                 :search-keys="['username', 'full_name', 'roleLabel']" :default-sort="{ key: 'username', dir: 'asc' }">
        <template #cell-username="{ row }">
          <strong>{{ row.username }}</strong>
          <span v-if="row.username === store.session.username" class="you">you</span>
          <div class="muted small">{{ row.full_name || '—' }}</div>
        </template>
        <template #cell-roleLabel="{ row }"><span class="pill" :class="`pill-role-${row.role}`">{{ row.roleLabel }}</span></template>
        <template #cell-state="{ row }">
          <span v-if="row.pending" class="pill pill-low">Awaiting approval</span>
          <span v-else-if="!row.active" class="pill pill-out">Disabled</span>
          <span v-else-if="row.locked" class="pill pill-low">Locked</span>
          <span v-else-if="row.must_change_password" class="pill pill-picked">Must change password</span>
          <span v-else class="pill pill-ok">Active</span>
        </template>
        <template #cell-last_login="{ row }">
          <span class="muted">{{ row.last_login ? fmtDateTime(row.last_login) : 'Never' }}</span>
        </template>
        <template #cell-actions="{ row }">
          <span class="row-actions">
            <button v-if="row.pending" class="btn btn-sm btn-primary" @click="openEdit(row)">Approve</button>
            <button v-if="row.locked" class="btn btn-sm" @click="unlock(row)">Unlock</button>
            <button v-if="!row.pending" class="btn btn-sm" @click="openEdit(row)">Edit</button>
            <button class="btn btn-sm" @click="openReset(row)">Reset password</button>
          </span>
        </template>
      </DataTable>
    </section>

    <section class="card panel">
      <h3>Roles &amp; permissions</h3>
      <div class="matrix-wrap">
        <table class="matrix">
          <thead>
            <tr><th>Permission</th><th v-for="(r, key) in roles" :key="key">{{ r.label }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(label, perm) in PERMISSION_LABELS" :key="perm">
              <td>{{ label }}</td>
              <td v-for="(r, key) in roles" :key="key" class="c">
                <span v-if="r.permissions.includes(perm)" class="yes" aria-label="yes">✓</span>
                <span v-else class="no" aria-label="no">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Add user -->
    <Modal v-if="adding" title="Add user" @close="adding = null">
      <form id="add-user" class="form" @submit.prevent="create">
        <div class="two">
          <label class="field">Username
            <input class="input" v-model.trim="adding.username" required minlength="3" maxlength="32" pattern="[a-zA-Z0-9_.\-]+" autocomplete="off" />
          </label>
          <label class="field">Full name <input class="input" v-model.trim="adding.full_name" maxlength="80" /></label>
        </div>
        <label class="field">Role
          <select class="input" v-model="adding.role" required>
            <option v-for="(r, key) in roles" :key="key" :value="key">{{ r.label }}</option>
          </select>
          <span class="hint">{{ roles[adding.role]?.description }}</span>
        </label>
        <label class="field">Temporary password
          <span class="pwrow">
            <input class="input" v-model="adding.password" required autocomplete="new-password" />
            <button type="button" class="btn btn-sm" @click="adding.password = generate()">Generate</button>
          </span>
          <span class="hint">At least 8 characters with a letter and a number. They must change it at first login.</span>
        </label>
      </form>
      <template #footer>
        <button class="btn" @click="adding = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="add-user" :disabled="saving">Create user</button>
      </template>
    </Modal>

    <!-- Edit user -->
    <Modal v-if="editing" :title="editing.pending ? `Approve ${editing.username}` : `Edit ${editing.username}`" @close="editing = null">
      <form id="edit-user" class="form" @submit.prevent="saveEdit">
        <label class="field">Full name <input class="input" v-model.trim="editing.full_name" maxlength="80" /></label>
        <p v-if="editing.pending" class="muted" style="margin:0">This person registered themselves. Choose the role they should have. They can sign in once you approve.</p>
        <label class="field">Role
          <select class="input" v-model="editing.role" required>
            <option v-if="!editing.role" :value="null" disabled>Choose a role…</option>
            <option v-for="(r, key) in roles" :key="key" :value="key">{{ r.label }}</option>
          </select>
          <span class="hint">{{ roles[editing.role]?.description }} Takes effect at their next sign-in.</span>
        </label>
        <label class="check"><input type="checkbox" v-model="editing.active" /> Account active (can sign in)</label>
      </form>
      <template #footer>
        <button class="btn" @click="editing = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="edit-user" :disabled="saving || !editing.role">{{ editing.pending ? 'Approve' : 'Save' }}</button>
      </template>
    </Modal>

    <!-- Reset password -->
    <Modal v-if="resetting" :title="`Reset password for ${resetting.username}`" @close="resetting = null">
      <form id="reset-pw" class="form" @submit.prevent="saveReset">
        <label class="field">New temporary password
          <span class="pwrow">
            <input class="input" v-model="resetting.password" required autocomplete="new-password" />
            <button type="button" class="btn btn-sm" @click="resetting.password = generate()">Generate</button>
          </span>
          <span class="hint">This also unlocks the account. They must choose a new password at next sign-in.</span>
        </label>
      </form>
      <template #footer>
        <button class="btn" @click="resetting = null">Cancel</button>
        <button class="btn btn-primary" type="submit" form="reset-pw" :disabled="saving">Reset password</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import api from '../api';
import DataTable from '../components/DataTable.vue';
import Modal from '../components/Modal.vue';
import { PERMISSION_LABELS, ROLE_LABELS, errorText, fmtDateTime, store } from '../store';

const query = ref('');
const roles = ref({});
const adding = ref(null);
const editing = ref(null);
const resetting = ref(null);
const saving = ref(false);

const columns = [
  { key: 'username', label: 'User', sortable: true, width: '22%' },
  { key: 'roleLabel', label: 'Role', sortable: true, width: '22%' },
  { key: 'state', label: 'Status', sortable: true, width: '18%', sortValue: (r) => (r.pending ? -1 : r.active ? (r.locked ? 1 : 0) : 2) },
  { key: 'last_login', label: 'Last sign-in', sortable: true, width: '18%', sortValue: (r) => r.last_login || '' },
  { key: 'actions', label: ''},
];

const rows = computed(() => store.users.map((u) => ({ ...u, id: u.username, roleLabel: u.pending ? '—' : ROLE_LABELS[u.role] || u.role })));
const pendingCount = computed(() => store.users.filter((u) => u.pending).length);
const activeCount = computed(() => store.users.filter((u) => u.active).length);
const lockedCount = computed(() => store.users.filter((u) => u.locked).length);

// Random password that satisfies the policy (uses the browser's secure random generator)
function generate() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  const bytes = crypto.getRandomValues(new Uint8Array(10));
  const body = Array.from(bytes, (b) => chars[b % chars.length]).join('');
  return body + (2 + (bytes[0] % 8)); // guarantees at least one digit
}

const openAdd = () => { adding.value = { username: '', full_name: '', role: 'warehouse', password: generate() }; };
const openEdit = (u) => { editing.value = { username: u.username, full_name: u.full_name, role: u.role, active: u.active, pending: u.pending }; };
const openReset = (u) => { resetting.value = { username: u.username, password: generate() }; };

async function run(action, ok, fail) {
  saving.value = true;
  try {
    await action();
    store.toast(ok);
    await store.loadUsers();
    return true;
  } catch (e) {
    store.toast(errorText(e, fail), 'error');
    return false;
  } finally {
    saving.value = false;
  }
}

async function create() {
  const u = adding.value;
  if (await run(() => api.post('/auth/users', u), `Created ${u.username}. Share the temporary password securely.`, 'Could not create user')) {
    adding.value = null;
  }
}

async function saveEdit() {
  const { username, pending, ...body } = editing.value;
  if (await run(() => api.patch(`/auth/users/${username}`, body), pending ? `Approved ${username}` : `Updated ${username}`, 'Could not update user')) {
    editing.value = null;
  }
}

async function saveReset() {
  const { username, password } = resetting.value;
  if (await run(() => api.post(`/auth/users/${username}/reset-password`, { password }), `Password reset for ${username}`, 'Could not reset password')) {
    resetting.value = null;
  }
}

const unlock = (u) => run(() => api.post(`/auth/users/${u.username}/unlock`), `${u.username} unlocked`, 'Could not unlock');
const refresh = () => run(() => Promise.resolve(), 'Users refreshed', '');

onMounted(async () => {
  roles.value = (await api.get('/auth/roles')).data;
  store.loadUsers();
});
</script>

<style scoped>
.users { display: grid; gap: 20px; }
.small { font-size: 13.5px; }
.warn { color: var(--warn); }
.you { margin-left: 6px; padding: 2px 7px; border-radius: 6px; background: var(--primary-soft); color: var(--primary); font-size: 12px; font-weight: 700; }
.row-actions { display: inline-flex; gap: 6px; }
.form { display: grid; gap: 14px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.pwrow { display: flex; gap: 6px; }
.pwrow .btn { height: 36px; }
.pwrow .input { font-family: ui-monospace, Consolas, monospace; }
.hint { font-weight: 500; font-size: 13px; }
.check { display: flex; gap: 8px; align-items: center; font-weight: 600; }
.matrix-wrap { overflow-x: auto; margin-top: 12px; border: 1px solid var(--border); border-radius: 8px; }
.matrix { width: 100%; border-collapse: collapse; }
.matrix th, .matrix td { padding: 9px 13px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.matrix th { background: var(--surface-2); font-size: 13px; color: var(--muted); text-align: center; }
/* permission names get a fixed share; the four role columns split the rest equally */
.matrix th:first-child { text-align: left; width: 32%; }
.matrix th:not(:first-child) { width: 17%; }
.matrix tbody tr:last-child td { border-bottom: 0; }
.c { text-align: center; }
.yes { color: var(--primary); font-weight: 800; }
.no { color: var(--border); }
@media (max-width: 520px) { .two { grid-template-columns: 1fr; } }
</style>
