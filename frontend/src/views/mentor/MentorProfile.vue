<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Build your mentor profile</h1>
        <p>Help students know your background and expertise.</p>
      </div>
      <span v-if="auth.needsProfile" class="notice small"><LockKeyhole /> Complete your profile to submit it for admin approval.</span>
      <span v-else-if="auth.approvalStatus === 'pending'" class="notice notice-warning small"><Hourglass /> Your profile is awaiting admin approval. Students will see you once you are approved.</span>
      <span v-else-if="auth.approvalStatus === 'rejected'" class="notice notice-warning small"><CircleX /> Your mentor application was not approved. Contact the administrator.</span>
      <span v-else class="notice small"><Sparkles /> A complete profile gets more relevant requests.</span>
    </div>

    <div v-if="!form" class="skeleton" style="height: 520px" />

    <form v-else class="card stack" novalidate @submit.prevent="save">
      <div class="top">
        <div class="photo-col">
          <UiAvatar :src="form.avatar" :name="form.name" :size="104" />
        </div>
        <div class="grid grid-2 grow">
          <div class="field">
            <label class="label" for="m-name">Full name</label>
            <input id="m-name" v-model.trim="form.name" class="input" :class="{ invalid: errors.name }" />
            <span v-if="errors.name" class="error-text">{{ errors.name }}</span>
          </div>
          <div class="field">
            <label class="label" for="m-role">Current role</label>
            <input id="m-role" v-model.trim="form.workRole" class="input" :class="{ invalid: errors.workRole }" placeholder="e.g. Product Manager" />
            <span v-if="errors.workRole" class="error-text">{{ errors.workRole }}</span>
          </div>
          <div class="field">
            <label class="label" for="m-company">College / company</label>
            <input id="m-company" v-model.trim="form.company" class="input" :class="{ invalid: errors.company }" />
            <span v-if="errors.company" class="error-text">{{ errors.company }}</span>
          </div>
          <div class="field">
            <label class="label" for="m-year">Started working in <span class="muted">(year)</span></label>
            <input id="m-year" v-model.number="form.workJoiningYear" class="input" :class="{ invalid: errors.workJoiningYear }" type="number" min="1950" :max="thisYear" placeholder="e.g. 2018" />
            <span v-if="errors.workJoiningYear" class="error-text">{{ errors.workJoiningYear }}</span>
            <span v-else-if="experience !== null" class="tiny muted">{{ experience }} year(s) of experience</span>
          </div>
        </div>
      </div>

      <div class="field">
        <span class="label">Career path</span>
        <div class="path">
          <TransitionGroup name="list">
            <div v-for="(c, i) in form.careerPath" :key="c._k" class="path-item">
              <span class="node" />
              <input v-model.trim="c.title" class="input sm" placeholder="Role / degree" aria-label="Title" />
              <input v-model.trim="c.organization" class="input sm" placeholder="Organisation" aria-label="Organisation" />
              <input v-model.number="c.startYear" class="input sm" type="number" placeholder="Start year" aria-label="Start year" />
              <input v-model.number="c.endYear" class="input sm" type="number" placeholder="End (blank = present)" aria-label="End year" />
              <button type="button" class="btn btn-ghost btn-icon btn-sm" aria-label="Remove" @click="form.careerPath.splice(i, 1)"><Trash2 /></button>
            </div>
          </TransitionGroup>
          <button type="button" class="link-btn small" @click="addStep"><Plus /> Add step</button>
        </div>
        <span v-if="errors.careerPath" class="error-text">{{ errors.careerPath }}</span>
      </div>

      <div class="field">
        <label class="label" for="m-bio">About you</label>
        <textarea id="m-bio" v-model="form.bio" class="textarea" :class="{ invalid: errors.bio }" maxlength="300" rows="4" />
        <span class="tiny muted" style="text-align: right">{{ form.bio.length }}/300</span>
        <span v-if="errors.bio" class="error-text">{{ errors.bio }}</span>
      </div>

      <div class="field">
        <label class="label" for="m-linkedin">LinkedIn profile <span class="muted">(optional)</span></label>
        <input id="m-linkedin" v-model.trim="form.linkedin" class="input" :class="{ invalid: errors.linkedin }" placeholder="https://www.linkedin.com/in/your-name" />
        <span v-if="errors.linkedin" class="error-text">{{ errors.linkedin }}</span>
      </div>

      <div class="field">
        <span class="label">Skills & expertise</span>
        <div class="flex wrap gap-2">
          <TransitionGroup name="list">
            <span v-for="(s, i) in form.skills" :key="s" class="chip active">{{ s }} <X class="x" @click="form.skills.splice(i, 1)" /></span>
          </TransitionGroup>
          <div class="add-skill">
            <div class="input-icon">
              <Search />
              <input
                v-model="skillQuery"
                class="input sm"
                placeholder="Search skills"
                role="combobox"
                aria-autocomplete="list"
                :aria-expanded="skillOpen"
                @focus="skillOpen = true"
                @input="skillOpen = true; activeIdx = 0"
                @blur="skillOpen = false"
                @keydown.down.prevent="moveActive(1)"
                @keydown.up.prevent="moveActive(-1)"
                @keydown.enter.prevent="addSkill(skillMatches[activeIdx])"
                @keydown.esc="skillOpen = false"
              />
            </div>
            <ul v-if="skillOpen" class="skill-menu" role="listbox">
              <li
                v-for="(s, i) in skillMatches"
                :key="s"
                role="option"
                :aria-selected="i === activeIdx"
                :class="{ active: i === activeIdx }"
                @mousedown.prevent="addSkill(s)"
                @mouseenter="activeIdx = i"
              >{{ s }}</li>
              <li v-if="!skillMatches.length" class="empty">{{ remainingSkills.length ? 'No matching skills' : 'All skills added' }}</li>
            </ul>
          </div>
        </div>
        <span v-if="errors.skills" class="error-text">{{ errors.skills }}</span>
      </div>

      <!-- Mentor.mentoring_areas: one row of CareerGoals -->
      <div class="field">
        <span class="label">Mentoring area <span class="muted">(select one)</span></span>
        <div class="flex wrap gap-2" role="radiogroup">
          <label v-for="t in topics" :key="t" class="chip" :class="{ active: form.mentoringArea === t }">
            <input v-model="form.mentoringArea" type="radio" name="mentoring-area" :value="t" hidden />
            <Check v-if="form.mentoringArea === t" /> {{ t }}
          </label>
        </div>
        <span v-if="errors.mentoringArea" class="error-text">{{ errors.mentoringArea }}</span>
      </div>

      <div class="flex justify-end">
        <button class="btn btn-primary btn-lg" :disabled="saving"><span v-if="saving" class="spinner" /><template v-else>Save profile</template></button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Sparkles, Trash2, Plus, X, Check, Search, LockKeyhole, Hourglass, CircleX } from '@lucide/vue'
import UiAvatar from '@/components/ui/UiAvatar.vue'
import { mentorApi } from '@/api'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const form = ref(null)
const saving = ref(false)
const errors = reactive({})
const thisYear = new Date().getFullYear()
const experience = computed(() => {
  const y = form.value?.workJoiningYear
  return y && y <= thisYear ? thisYear - y : null
})
const skillQuery = ref('')
const skillOpen = ref(false)
const activeIdx = ref(0)
// Rows of the Skills / CareerGoals tables (GET /api/options)
const { options, ready } = useOptions()
const SKILLS = computed(() => options.value.skills)
const topics = computed(() => options.value.careerGoals.map((g) => g.name))
const remainingSkills = computed(() => SKILLS.value.filter((s) => !form.value?.skills.includes(s)))
const skillMatches = computed(() => {
  const q = skillQuery.value.trim().toLowerCase()
  return q ? remainingSkills.value.filter((s) => s.toLowerCase().includes(q)) : remainingSkills.value
})
let k = 0

onMounted(async () => {
  let p
  try {
    ;[p] = await Promise.all([mentorApi.getProfile(), ready])
  } catch (e) {
    return toast.error(e.message)
  }
  // keep the stored session in step with the backend (e.g. the admin approved this mentor meanwhile)
  auth.updateUser({ name: p.name, approved: p.approved, approvalStatus: p.approvalStatus, profileCompletion: p.profileCompletion, profileComplete: p.profileComplete })
  form.value = {
    name: p.name || '',
    avatar: p.avatar || null,
    workRole: p.workRole || '',
    company: p.company || '',
    workJoiningYear: p.workJoiningYear || null,
    bio: p.bio || '',
    linkedin: p.linkedin || '',
    skills: [...(p.skills || [])],
    mentoringArea: p.mentoringArea || '',
    careerPath: (p.careerPath || []).map((c) => ({ ...c, _k: ++k }))
  }
  if (!form.value.careerPath.length) addStep()
})

function addStep() { form.value.careerPath.push({ title: '', organization: '', startYear: null, endYear: null, _k: ++k }) }
function moveActive(step) {
  skillOpen.value = true
  const n = skillMatches.value.length
  if (n) activeIdx.value = (activeIdx.value + step + n) % n
}
// Only skills defined in the SKILLS list can be added
function addSkill(s) {
  if (!s || !SKILLS.value.includes(s) || form.value.skills.includes(s)) return
  form.value.skills.push(s)
  skillQuery.value = ''
  activeIdx.value = 0
}

const isYear = (y) => Number.isInteger(y) && y >= 1950 && y <= thisYear
const LINKEDIN = /^https?:\/\/(www\.)?linkedin\.com\/.+/i

function validate() {
  const f = form.value
  Object.keys(errors).forEach((key) => delete errors[key])
  if (!f.name) errors.name = 'Name is required'
  if (!f.workRole) errors.workRole = 'Current role is required'
  if (!f.company) errors.company = 'College / company is required'
  if (!isYear(f.workJoiningYear)) errors.workJoiningYear = `Enter a year between 1950 and ${thisYear}`
  if (!f.bio.trim()) errors.bio = 'Write a short introduction'
  if (f.linkedin && !LINKEDIN.test(f.linkedin)) errors.linkedin = 'Enter a valid LinkedIn URL'
  if (!f.skills.length) errors.skills = 'Add at least one skill'
  if (!f.mentoringArea) errors.mentoringArea = 'Select your mentoring area'
  const steps = f.careerPath.filter((c) => c.title || c.organization || c.startYear || c.endYear)
  if (!steps.length) errors.careerPath = 'Add at least one career step'
  else if (steps.some((c) => !c.title || !isYear(c.startYear) || (c.endYear && (!isYear(c.endYear) || c.endYear < c.startYear))))
    errors.careerPath = 'Each step needs a title and a valid start year (leave end year blank if current)'
  return !Object.keys(errors).length
}

async function save() {
  if (!validate()) return toast.error('Please fill in the required details')
  const { avatar: _avatar, ...fields } = form.value // no photo upload in the backend yet
  const data = {
    ...fields,
    bio: form.value.bio.trim(),
    // MentorCareerPath rows; step_number follows the order on screen
    careerPath: form.value.careerPath
      .filter((c) => c.title)
      .map(({ _k, ...c }, i) => ({ ...c, stepNumber: i + 1, endYear: c.endYear || null }))
  }
  const wasLocked = auth.needsProfile
  saving.value = true
  try {
    const res = await mentorApi.updateProfile(data)
    auth.updateUser({ name: res.name, approved: res.approved, approvalStatus: res.approvalStatus, profileCompletion: res.profileCompletion, profileComplete: res.profileComplete })
    toast.success(wasLocked && auth.needsApproval ? 'Profile saved and submitted for admin approval' : 'Profile saved')
    if (wasLocked && !auth.needsProfile && !auth.needsApproval) router.push(auth.home)
  } catch (e) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.top { display: flex; gap: 28px; align-items: flex-start; }
.photo-col { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.path { display: flex; flex-direction: column; gap: 10px; padding-left: 22px; border-left: 2px solid var(--primary-100); margin-left: 6px; }
.path-item { position: relative; display: grid; grid-template-columns: 1.2fr 1.2fr 0.7fr 0.9fr auto; gap: 8px; align-items: center; }
.invalid { border-color: var(--danger); }
.node { position: absolute; left: -30px; width: 14px; height: 14px; border-radius: 50%; background: #fff; border: 3px solid var(--primary); }
.input.sm { height: 36px; font-size: 13px; }
.x { width: 14px; height: 14px; cursor: pointer; }
.add-skill { position: relative; }
.add-skill .input { width: 200px; }
.skill-menu {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 20;
  width: 220px; max-height: 220px; overflow-y: auto;
  margin: 0; padding: 4px; list-style: none;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow);
}
.skill-menu li { padding: 7px 10px; font-size: 13px; border-radius: 6px; cursor: pointer; }
.skill-menu li.active { background: var(--primary-50); color: var(--primary-text); }
.skill-menu li.empty { color: var(--muted); cursor: default; }
label.chip { cursor: pointer; }
@media (max-width: 760px) {
  .top { flex-direction: column; align-items: stretch; }
  .path-item { grid-template-columns: 1fr 1fr; }
}
</style>
