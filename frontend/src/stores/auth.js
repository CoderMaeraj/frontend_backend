import { defineStore } from 'pinia'
import { authApi } from '@/api'
import { storage } from '@/api/client'

const HOME = { student: '/student', mentor: '/mentor', admin: '/admin' }
// Profile-completion page per role. Until the backend says the profile is complete,
// students and mentors can only open this page.
const PROFILE = { student: '/student/profile', mentor: '/mentor/profile' }

function savedUser() {
  try { return JSON.parse(storage.get('mc_user') || 'null') } catch { return null }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: savedUser(), token: storage.get('mc_token'), verified: false }),
  getters: {
    isLoggedIn: (s) => !!s.token && !!s.user,
    role: (s) => s.user?.role,
    profilePage: (s) => PROFILE[s.user?.role] || null,
    needsProfile: (s) => !!PROFILE[s.user?.role] && !s.user?.profileComplete,
    // Mentors can only use the mentoring pages once an admin has approved them.
    approvalStatus: (s) => (s.user?.role === 'mentor' ? s.user.approvalStatus || (s.user.approved ? 'approved' : 'pending') : null),
    needsApproval() { return this.user?.role === 'mentor' && this.approvalStatus !== 'approved' },
    home() {
      if (!this.user) return '/login'
      return this.needsProfile || this.needsApproval ? this.profilePage : HOME[this.user.role] || '/login'
    }
  },
  actions: {
    setSession({ token, user }) {
      this.token = token
      this.user = user
      this.verified = true
      storage.set('mc_token', token)
      storage.set('mc_user', JSON.stringify(user))
    },
    async login(email, password, remember = false) {
      this.setSession(await authApi.login({ email, password, remember }))
    },
    async register(payload) {
      this.setSession(await authApi.register(payload))
    },
    // Re-check the stored token with the backend once per page load.
    async verify() {
      if (this.verified || !this.token) return
      try {
        const { user } = await authApi.me()
        this.updateUser(user)
      } catch (e) {
        if (e.status === 401 || e.status === 403) this.logout()
      } finally {
        this.verified = true
      }
    },
    updateUser(patch) {
      this.user = { ...this.user, ...patch }
      storage.set('mc_user', JSON.stringify(this.user))
    },
    logout() {
      this.token = null
      this.user = null
      storage.remove('mc_token')
      storage.remove('mc_user')
    }
  }
})
