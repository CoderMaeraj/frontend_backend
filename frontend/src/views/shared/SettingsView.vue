<template>
  <div class="narrow">
    <div class="page-head">
      <div>
        <h1>Settings</h1>
        <p>Manage your account and notifications.</p>
      </div>
    </div>

    <div class="stack">
      <form class="card stack" @submit.prevent="saveAccount">
        <h3>Account</h3>
        <div class="flex items-center gap-4">
          <UiAvatar :src="auth.user?.avatar" :name="form.name" :size="60" />
          <div><b>{{ form.name }}</b><p class="small muted">{{ roleLabel }}</p></div>
        </div>
        <div class="grid grid-2">
          <div class="field"><label class="label">Full name</label><input v-model="form.name" class="input" :disabled="!canEdit" /></div>
          <div class="field"><label class="label">Email</label><input v-model="form.email" class="input" type="email" :disabled="!canEdit" /></div>
        </div>
        <p v-if="!canEdit" class="small muted">The administrator account is configured on the server.</p>
        <div v-else class="flex justify-end"><button class="btn btn-primary" :disabled="savingAccount"><span v-if="savingAccount" class="spinner" /><template v-else>Save changes</template></button></div>
      </form>

      <div class="card">
        <h3>Notifications</h3>
        <p class="small muted mt-1">Notifications are not available yet.</p>
        <div class="stack mt-4">
          <div v-for="n in notifs" :key="n.key" class="row">
            <div class="grow"><b class="small">{{ n.label }}</b><p class="tiny muted">{{ n.text }}</p></div>
            <UiToggle v-model="n.on" disabled />
          </div>
        </div>
      </div>

      <form v-if="canEdit" class="card stack" @submit.prevent="changePw">
        <h3>Change password</h3>
        <div class="grid grid-2">
          <div class="field"><label class="label">Current password</label><input v-model="pw.current" class="input" type="password" /></div>
          <div class="field"><label class="label">New password</label><input v-model="pw.next" class="input" type="password" /></div>
        </div>
        <div class="flex justify-end"><button class="btn btn-outline" :disabled="!pw.current || pw.next.length < 6 || savingPw">Update password</button></div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import UiAvatar from '@/components/ui/UiAvatar.vue'
import UiToggle from '@/components/ui/UiToggle.vue'
import { useAuthStore } from '@/stores/auth'
import { accountApi } from '@/api'
import { useToast } from '@/composables/useToast'

const auth = useAuthStore()
const toast = useToast()
const roleLabel = computed(() => ({ student: 'Student', mentor: 'Mentor', admin: 'Programme Admin' })[auth.role])
const form = reactive({ name: auth.user?.name || '', email: auth.user?.email || '' })
const pw = reactive({ current: '', next: '' })
const notifs = reactive([
  { key: 'email', label: 'Email updates', text: 'Request and session updates by email', on: false },
  { key: 'reminder', label: 'Session reminders', text: 'A reminder 1 hour before each session', on: false },
  { key: 'news', label: 'New resources', text: 'When new guides are published', on: false }
])

// Account changes are saved for students and mentors (PATCH /account, PUT /account/password)
const canEdit = computed(() => ['student', 'mentor'].includes(auth.role))
const savingAccount = ref(false)
const savingPw = ref(false)

async function saveAccount() {
  if (!canEdit.value) return
  savingAccount.value = true
  try {
    const { user } = await accountApi.update({ name: form.name, email: form.email })
    auth.updateUser(user)
    Object.assign(form, { name: user.name, email: user.email })
    toast.success('Account updated')
  } catch (e) {
    toast.error(e.message)
  } finally {
    savingAccount.value = false
  }
}
async function changePw() {
  savingPw.value = true
  try {
    await accountApi.changePassword(pw.current, pw.next)
    pw.current = ''
    pw.next = ''
    toast.success('Password updated')
  } catch (e) {
    toast.error(e.message)
  } finally {
    savingPw.value = false
  }
}
</script>

<style scoped>
.narrow { max-width: 820px; }
.row { display: flex; align-items: center; gap: 16px; }
</style>
