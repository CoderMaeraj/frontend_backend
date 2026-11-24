<template>
  <div class="profile-grid">
    <form class="card stack" novalidate @submit.prevent="save">
      <div class="hero-row">
        <div>
          <h1>Let's build your profile</h1>
          <p class="muted mt-1">Tell us about yourself to find the right mentors.</p>
          <p v-if="auth.needsProfile" class="lock"><LockKeyhole /> Complete your profile to unlock your dashboard.</p>
        </div>
      </div>

      <div v-if="!form" class="stack"><div v-for="i in 4" :key="i" class="skeleton" style="height: 60px" /></div>

      <template v-else>
        <!-- Degree type -->
        <div class="field">
          <span class="label">Are you pursuing a single or dual degree?</span>
          <div class="types">
            <button
              v-for="t in degreeTypes" :key="t.value" type="button"
              class="type" :class="{ active: form.degreeType === t.value }"
              @click="form.degreeType = t.value"
            >
              <component :is="t.icon" class="type-ic" />
              <b>{{ t.label }}</b>
              <span class="small muted">{{ t.text }}</span>
              <Check class="tick" />
            </button>
          </div>
        </div>

        <!-- Student.programme + Student.academic_level -->
        <div class="grid grid-3">
          <div class="field span-2">
            <label class="label" for="programme">Programme</label>
            <select id="programme" v-model="form.programme" class="select">
              <option v-for="d in programmeOptions" :key="d">{{ d }}</option>
            </select>
          </div>
          <div class="field">
            <label class="label" for="level">Academic level</label>
            <select id="level" v-model="form.academicLevel" class="select">
              <option v-for="l in ACADEMIC_LEVELS" :key="l">{{ l }}</option>
            </select>
          </div>
        </div>

        <!-- Student.dual_degree (dual degree only) -->
        <Transition name="fade">
          <div v-if="isDual" class="field second">
            <label class="label" for="dual">Other degree name</label>
            <input id="dual" v-model.trim="form.dualDegree" class="input" :class="{ invalid: errors.dualDegree }" placeholder="e.g. B.S. – Electronics and Communication" />
            <span v-if="errors.dualDegree" class="error-text">{{ errors.dualDegree }}</span>
          </div>
        </Transition>

        <!-- Student.bio -->
        <div class="field">
          <label class="label" for="bio">Short introduction</label>
          <textarea id="bio" v-model="form.bio" class="textarea" :class="{ invalid: errors.bio }" maxlength="300" rows="3" placeholder="A few lines about you and what you want to achieve" />
          <span class="tiny muted" style="text-align: right">{{ form.bio.length }}/300</span>
          <span v-if="errors.bio" class="error-text">{{ errors.bio }}</span>
        </div>

        <!-- Student.linkedin -->
        <div class="field">
          <label class="label" for="linkedin">LinkedIn profile <span class="muted">(optional)</span></label>
          <input id="linkedin" v-model.trim="form.linkedin" class="input" :class="{ invalid: errors.linkedin }" placeholder="https://www.linkedin.com/in/your-name" />
          <span v-if="errors.linkedin" class="error-text">{{ errors.linkedin }}</span>
        </div>

        <!-- StudentSkills -->
        <div class="field">
          <ChipPicker v-model="form.skills" label="Key skills" :options="SKILLS" :max="5" />
          <span v-if="errors.skills" class="error-text">{{ errors.skills }}</span>
        </div>

        <!-- Student.career_goal (one row of CareerGoals) -->
        <div class="field">
          <span class="label">What is your career goal? <span class="muted">(select one)</span></span>
          <div class="goals">
            <button
              v-for="g in goalOptions" :key="g.label" type="button"
              class="goal" :class="{ active: form.careerGoal === g.label }"
              role="radio" :aria-checked="form.careerGoal === g.label"
              @click="form.careerGoal = form.careerGoal === g.label ? '' : g.label"
            >
              <component :is="g.icon" />
              <span>{{ g.label }}</span>
              <Check class="tick" />
            </button>
          </div>
          <span v-if="errors.careerGoal" class="error-text">{{ errors.careerGoal }}</span>
        </div>

        <div class="flex justify-end">
          <button class="btn btn-primary btn-lg" :disabled="saving">
            <span v-if="saving" class="spinner" /><template v-else>Save & find mentors <ArrowRight /></template>
          </button>
        </div>
      </template>
    </form>

    <aside class="card side">
      <img :src="ill" alt="" />
      <h3 class="mt-3">Better profile, better matches</h3>
      <ul class="tips">
        <li><CircleCheck /> Pick skills you are confident in</li>
        <li><CircleCheck /> Write a short, honest introduction</li>
        <li><CircleCheck /> Choose one main career goal</li>
      </ul>
    </aside>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Check, Briefcase, Building2, GraduationCap, Laptop, Lightbulb, CircleCheck, Layers, LockKeyhole, Target } from '@lucide/vue'
import ChipPicker from '@/components/ChipPicker.vue'
import { studentApi } from '@/api'
import { DEGREES } from '@/constants'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import ill from '@/assets/img/signup-ill.jpg'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const form = ref(null)
const saving = ref(false)
const errors = reactive({})

const degreeTypes = [
  { value: 'single', label: 'Single degree', text: 'One programme', icon: GraduationCap },
  { value: 'dual', label: 'Dual degree', text: 'Two programmes together', icon: Layers }
]

// Rows of the CareerGoals / Skills tables and Student.academic_level values (GET /api/options)
const { options, ready } = useOptions()
const GOAL_ICONS = { Internships: Briefcase, Jobs: Building2, 'Higher studies': GraduationCap, Freelancing: Laptop, Entrepreneurship: Lightbulb }
const goalOptions = computed(() => options.value.careerGoals.map((g) => ({ label: g.name, icon: GOAL_ICONS[g.name] || Target })))
const SKILLS = computed(() => options.value.skills)
const ACADEMIC_LEVELS = computed(() => options.value.academicLevels)

const isDual = computed(() => form.value?.degreeType === 'dual')

// If a saved programme is not in the predefined list (older data), keep it selectable.
const programmeOptions = computed(() => {
  const cur = form.value?.programme
  return cur && !DEGREES.includes(cur) ? [cur, ...DEGREES] : DEGREES
})

onMounted(async () => {
  let p
  try {
    ;[p] = await Promise.all([studentApi.getProfile(), ready])
  } catch (e) {
    return toast.error(e.message)
  }
  form.value = {
    degreeType: p.dualDegree ? 'dual' : 'single',
    programme: p.programme || DEGREES[0],
    academicLevel: p.academicLevel || ACADEMIC_LEVELS.value[0],
    dualDegree: p.dualDegree || '',
    bio: p.bio || '',
    linkedin: p.linkedin || '',
    skills: [...(p.skills || [])],
    careerGoal: p.careerGoal || ''
  }
})

function validate() {
  const f = form.value
  Object.keys(errors).forEach((k) => delete errors[k])
  if (isDual.value && !f.dualDegree) errors.dualDegree = 'Enter the name of your other degree'
  if (!f.bio.trim()) errors.bio = 'Write a short introduction'
  if (f.linkedin && !/^https?:\/\/(www\.)?linkedin\.com\/.+/i.test(f.linkedin)) errors.linkedin = 'Enter a valid LinkedIn URL'
  if (!f.skills.length) errors.skills = 'Pick at least one skill'
  if (!f.careerGoal) errors.careerGoal = 'Select one career goal'
  return !Object.keys(errors).length
}

async function save() {
  if (!validate()) return toast.error('Please fill in the required details')

  const { degreeType, ...data } = form.value
  data.bio = data.bio.trim()
  if (degreeType !== 'dual') data.dualDegree = '' // single degree: no leftover dual-degree name

  saving.value = true
  try {
    const res = await studentApi.updateProfile(data)
    auth.updateUser({ profileCompletion: res.profileCompletion, profileComplete: res.profileComplete })
    toast.success('Profile saved')
    router.push({ path: '/student/mentors', query: { goal: data.careerGoal } })
  } catch (e) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-grid { display: grid; grid-template-columns: 1fr 300px; gap: 20px; align-items: start; }
.lock { display: inline-flex; align-items: center; gap: 8px; margin-top: 10px; padding: 8px 12px; border-radius: 10px; background: var(--primary-50); color: var(--primary-text); font-size: 13px; font-weight: 600; }
.lock svg { width: 16px; height: 16px; }

.types { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.type { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 18px 12px; border-radius: 14px; border: 1.5px solid var(--border-strong); background: var(--surface); transition: all 0.3s var(--ease); }
.type:hover { border-color: #e7cc92; transform: translateY(-2px); }
.type.active { border-color: var(--primary); background: var(--primary-50); box-shadow: 0 0 0 4px rgba(var(--primary-rgb), 0.14); }
.type-ic { width: 26px; height: 26px; color: var(--primary); margin-bottom: 2px; transition: transform 0.4s var(--ease); }
.type.active .type-ic { transform: scale(1.12) rotate(-6deg); }
.second { padding: 14px; border-radius: 12px; background: var(--surface-2); }
.invalid { border-color: var(--danger); }

.goals { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.goal { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 84px; padding: 12px; border-radius: 12px; border: 1.5px solid var(--border-strong); background: var(--surface); font-weight: 600; font-size: 13px; transition: all 0.25s var(--ease); }
.goal svg { width: 22px; height: 22px; color: var(--text-2); transition: transform 0.3s var(--ease), color 0.2s; }
.goal:hover { border-color: #e7cc92; transform: translateY(-2px); }
.goal.active { border-color: var(--primary); background: var(--primary-50); color: var(--primary-text); }
.goal.active svg { color: var(--primary); transform: scale(1.1); }
.tick { position: absolute; top: 8px; right: 8px; width: 16px !important; height: 16px !important; padding: 2px; border-radius: 50%; background: var(--primary); color: #fff !important; opacity: 0; transform: scale(0.5) !important; transition: all 0.25s var(--ease) !important; }
.goal.active .tick, .type.active .tick { opacity: 1; transform: scale(1) !important; }
.side { position: sticky; top: 88px; }
.side img { border-radius: 12px; }
.tips { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 10px; font-size: 13px; color: var(--text-2); }
.tips li { display: flex; gap: 8px; align-items: center; }
.tips svg { width: 16px; height: 16px; color: var(--primary); flex-shrink: 0; }
@media (max-width: 1024px) { .profile-grid { grid-template-columns: 1fr; } .side { display: none; } }
@media (max-width: 560px) { .goals { grid-template-columns: repeat(2, 1fr); } }
</style>
