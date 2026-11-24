<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Record a mentoring session</h1>
        <p>Save a summary and action items from your session.</p>
      </div>
    </div>

    <div class="layout">
      <form class="card stack" @submit.prevent="save">
        <h3>Session details</h3>
        <div class="grid grid-2">
          <div class="field">
            <label class="label">Mentee</label>
            <select v-model="form.menteeId" class="select" :disabled="!mentees.length">
              <option v-if="!mentees.length" :value="null">No active mentees</option>
              <option v-for="m in mentees" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </div>
          <div class="field">
            <label class="label">Session date</label>
            <input v-model="form.date" type="date" class="input" :max="today()" />
          </div>
        </div>
        <div class="field">
          <label class="label">Title</label>
          <input v-model="form.title" class="input" placeholder="e.g. Resume review" />
        </div>
        <div class="field">
          <label class="label">Session summary</label>
          <textarea v-model="form.summary" class="textarea" maxlength="500" rows="4" placeholder="What did you discuss?" />
          <span class="tiny muted" style="text-align: right">{{ form.summary.length }}/500</span>
        </div>

        <div class="field">
          <span class="label">Action items / next steps</span>
          <TransitionGroup tag="div" name="list" class="stack-sm">
            <div v-for="(a, i) in form.items" :key="a.k" class="item">
              <input v-model="a.done" type="checkbox" />
              <input v-model="a.text" class="input sm" placeholder="Action item" />
              <button type="button" class="btn btn-ghost btn-icon btn-sm" aria-label="Remove" @click="form.items.splice(i, 1)"><Trash2 /></button>
            </div>
          </TransitionGroup>
          <button type="button" class="link-btn small" @click="addItem"><Plus /> Add action item</button>
        </div>

        <div class="flex justify-end">
          <button class="btn btn-primary" :disabled="!form.menteeId || !form.date || !form.summary.trim() || saving"><span v-if="saving" class="spinner" /><template v-else>Save session</template></button>
        </div>
      </form>

      <aside class="card">
        <div class="card-head"><h3>Session history</h3><span class="small muted">{{ history.length }}</span></div>
        <div v-if="loading" class="stack-sm"><div v-for="i in 3" :key="i" class="skeleton" style="height: 70px" /></div>
        <p v-else-if="!history.length" class="small muted">No sessions recorded yet.</p>
        <TransitionGroup v-else tag="ol" name="list" class="timeline">
          <li v-for="s in history" :key="s.id">
            <span class="node" />
            <div class="flex items-center justify-between gap-2">
              <b class="small">{{ s.date }}</b>
              <StatusBadge :status="s.status" />
            </div>
            <p class="tiny muted">{{ s.mentee }} · {{ s.time }}</p>
            <p v-if="s.title" class="small bold mt-1">{{ s.title }}</p>
            <p v-if="s.summary" class="small muted">{{ s.summary }}</p>
          </li>
        </TransitionGroup>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Plus, Trash2 } from '@lucide/vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { mentorApi } from '@/api'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const history = ref([])
const mentees = ref([]) // [{ id: mentorship id, name }]
const loading = ref(true)
const saving = ref(false)
let k = 0
// local date as YYYY-MM-DD (sessions can only be recorded once they have taken place)
const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10) }
const blank = () => ({ menteeId: mentees.value[0]?.id ?? null, date: today(), title: '', summary: '', items: [{ k: ++k, text: '', done: false }] })
const form = reactive(blank())

onMounted(async () => {
  try {
    const r = await mentorApi.getSessions()
    history.value = r.list
    mentees.value = r.menteeOptions
    form.menteeId = mentees.value[0]?.id ?? null
  } catch (e) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
})

function addItem() { form.items.push({ k: ++k, text: '', done: false }) }

async function save() {
  saving.value = true
  try {
    const s = await mentorApi.recordSession({
      menteeId: form.menteeId,
      date: form.date,
      title: form.title.trim() || 'Mentoring session',
      summary: form.summary.trim(),
      actionItems: form.items.filter((i) => i.text.trim()).map(({ text, done }) => ({ text: text.trim(), done }))
    })
    history.value = history.value.filter((h) => h.id !== s.id)
    history.value.unshift(s)
    Object.assign(form, blank())
    toast.success('Session saved')
  } catch (e) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.layout { display: grid; grid-template-columns: 1fr 360px; gap: 20px; align-items: start; }
.item { display: flex; align-items: center; gap: 10px; }
.input.sm { height: 36px; font-size: 13px; }
.timeline { list-style: none; margin: 0; padding: 0 0 0 22px; position: relative; display: flex; flex-direction: column; gap: 18px; }
.timeline::before { content: ''; position: absolute; left: 5px; top: 6px; bottom: 6px; width: 2px; background: var(--primary-100); }
.timeline li { position: relative; }
.node { position: absolute; left: -22px; top: 4px; width: 12px; height: 12px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 0 3px #fff; }
@media (max-width: 1024px) { .layout { grid-template-columns: 1fr; } }
</style>
