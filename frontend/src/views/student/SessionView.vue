<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Mentorship session</h1>
        <p>Have a great conversation and track your takeaways.</p>
      </div>
    </div>

    <div v-if="loading" class="layout"><div class="skeleton" style="height: 520px" /><div class="skeleton" style="height: 520px" /></div>

    <div v-else-if="!s" class="card">
      <EmptyState title="No active mentorship yet" text="Messaging opens once a mentor accepts your request.">
        <RouterLink to="/student/mentors" class="btn btn-primary btn-sm">Find mentors</RouterLink>
      </EmptyState>
    </div>

    <div v-else class="layout">
      <div class="stack">
        <div class="card mentor-head fade-up">
          <UiAvatar :src="s.mentor.avatar" :name="s.mentor.name" :size="52" online />
          <div class="grow">
            <b>{{ s.mentor.name }}</b>
            <p class="small muted">{{ s.mentor.title }} at {{ s.mentor.company }}</p>
          </div>
          <StatusBadge status="accepted" />
          <RouterLink :to="`/student/mentors/${s.mentor.id}`" class="btn btn-outline btn-sm">View profile</RouterLink>
        </div>

        <div class="card fade-up" style="animation-delay: 0.06s">
          <div class="card-head"><h4>{{ s.session.status === 'booked' ? 'Upcoming session' : 'Latest session' }}</h4></div>
          <p v-if="!s.session.date" class="small muted">No session booked yet. Your mentor will record sessions here.</p>
          <div v-else class="session-row">
            <div class="flex items-center gap-3"><span class="icon-box"><CalendarDays /></span><div><b>{{ s.session.date }}</b><p class="small muted">{{ s.session.time }}</p></div></div>
            <div class="flex items-center gap-3"><span class="icon-box teal"><Video /></span><div class="grow"><b>Google Meet</b><p class="small muted truncate">{{ s.session.link || 'Link not shared yet' }}</p></div></div>
            <a v-if="s.session.link" :href="s.session.link" target="_blank" rel="noopener" class="btn btn-primary btn-sm">Join meeting <ExternalLink /></a>
          </div>
        </div>

        <div class="card chat-card fade-up" style="animation-delay: 0.12s">
          <h4>Conversation</h4>
          <div class="chat">
            <div ref="scroller" class="messages">
              <p v-if="!s.messages.length" class="small muted center">Say hello to {{ s.mentor.name.split(' ')[0] }} 👋</p>
              <TransitionGroup name="msg">
                <div v-for="(msg, i) in s.messages" :key="msg.id || i" class="msg" :class="msg.from">
                  <UiAvatar v-if="msg.from === 'mentor'" :src="s.mentor.avatar" :name="s.mentor.name" :size="30" />
                  <div class="bubble">{{ msg.text }}<span>{{ msg.time }}</span></div>
                </div>
              </TransitionGroup>
            </div>
            <form class="composer" @submit.prevent="send">
              <input v-model="text" class="input" placeholder="Type a message..." :disabled="sending" />
              <button class="btn btn-primary btn-icon" :disabled="!text.trim() || sending" aria-label="Send"><SendHorizontal /></button>
            </form>
          </div>
        </div>
      </div>

      <aside class="stack">
        <div class="card fade-up" style="animation-delay: 0.08s">
          <div class="card-head"><h4>Recommended resources</h4><RouterLink to="/student/resources" class="link-btn small">View all</RouterLink></div>
          <div class="stack-sm">
            <div v-for="r in recs" :key="r.title" class="res">
              <span class="icon-box" :class="r.cls"><component :is="r.icon" /></span>
              <div><b class="small">{{ r.title }}</b><p class="tiny muted">{{ r.meta }}</p></div>
            </div>
          </div>
        </div>

        <div class="card fade-up" style="animation-delay: 0.14s">
          <div class="card-head"><h4>Post-session action items</h4><span class="small muted">{{ doneCount }}/{{ s.actionItems.length }}</span></div>
          <div class="progress"><span :style="{ width: (s.actionItems.length ? (doneCount / s.actionItems.length) * 100 : 0) + '%' }" /></div>
          <p v-if="!s.actionItems.length" class="small muted mt-3">Your mentor adds action items after each session.</p>
          <div class="stack-sm mt-3">
            <label v-for="a in s.actionItems" :key="a.id" class="todo" :class="{ done: a.done }">
              <input v-model="a.done" type="checkbox" @change="saveItems" />
              <span>{{ a.text }}</span>
            </label>
          </div>
          <button v-if="s.session.date" class="btn btn-block mt-4" :class="s.completed ? 'btn-soft' : 'btn-success'" :disabled="s.completed" @click="complete">
            <CircleCheck /> {{ s.completed ? 'Session completed' : 'Mark session complete' }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { CalendarDays, Video, ExternalLink, SendHorizontal, FileText, PlayCircle, CircleCheck } from '@lucide/vue'
import UiAvatar from '@/components/ui/UiAvatar.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { studentApi } from '@/api'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const s = ref(null)
const text = ref('')
const loading = ref(true)
const sending = ref(false)
const scroller = ref(null)

const recs = [
  { title: 'A guide to product internships', meta: 'Article · 5 min read', icon: FileText, cls: '' },
  { title: 'Product management roadmap', meta: 'Video · 8 min', icon: PlayCircle, cls: 'teal' }
]
const doneCount = computed(() => s.value.actionItems.filter((a) => a.done).length)

onMounted(async () => {
  try {
    s.value = await studentApi.getMentorship()
  } catch (e) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
  scrollDown()
})

function scrollDown() {
  nextTick(() => { if (scroller.value) scroller.value.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' }) })
}

async function send() {
  const t = text.value.trim()
  if (!t) return
  sending.value = true
  try {
    const msg = await studentApi.sendMessage(t)
    text.value = ''
    s.value.messages.push(msg)
    scrollDown()
  } catch (e) {
    toast.error(e.message)
  } finally {
    sending.value = false
  }
}

async function saveItems() {
  try {
    const res = await studentApi.updateMentorship({ actionItems: s.value.actionItems.map(({ id, done }) => ({ id, done })) })
    s.value.actionItems = res.actionItems
  } catch (e) {
    toast.error(e.message)
  }
}
async function complete() {
  try {
    const res = await studentApi.updateMentorship({ completed: true })
    s.value.completed = res.completed
    s.value.session = res.session
    toast.success('Session marked as complete')
  } catch (e) {
    toast.error(e.message)
  }
}
</script>

<style scoped>
.layout { display: grid; grid-template-columns: 1fr 340px; gap: 20px; align-items: start; }
.mentor-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.session-row { display: grid; grid-template-columns: auto 1fr auto; gap: 18px; align-items: center; }
.icon-box.teal { background: var(--info-bg); color: var(--info); }
.chat { display: flex; flex-direction: column; margin-top: 14px; }
.messages { height: 300px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding: 4px 4px 12px; }
.msg { display: flex; gap: 8px; align-items: flex-end; max-width: 80%; }
.msg.student { align-self: flex-end; }
.bubble { padding: 10px 14px; border-radius: 16px; font-size: 13.5px; background: var(--surface-2); border-bottom-left-radius: 4px; }
.bubble span { display: block; font-size: 10.5px; color: var(--muted); margin-top: 4px; }
.student .bubble { background: var(--primary-600); color: #fff; border-radius: 16px 16px 4px 16px; }
.student .bubble span { color: rgba(255, 255, 255, 0.82); text-align: right; }
.typing { display: flex; gap: 4px; padding: 14px; }
.typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); animation: blink 1.2s infinite; }
.typing i:nth-child(2) { animation-delay: 0.15s; }
.typing i:nth-child(3) { animation-delay: 0.3s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.3; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
.msg-enter-active { transition: all 0.35s var(--ease); }
.msg-enter-from { opacity: 0; transform: translateY(10px) scale(0.97); }
.composer { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border); }
.res { display: flex; gap: 12px; align-items: center; padding: 10px; border-radius: 10px; transition: background 0.2s; cursor: pointer; }
.res:hover { background: var(--surface-2); }
.todo { display: flex; align-items: center; gap: 10px; font-size: 13px; cursor: pointer; padding: 6px 0; }
.todo span { transition: color 0.2s; position: relative; }
.todo.done span { color: var(--muted); text-decoration: line-through; }
@media (max-width: 1024px) { .layout { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .session-row { grid-template-columns: 1fr; } .msg { max-width: 92%; } }
</style>
