// All API calls used by the app. Each call shows the backend endpoint it expects.
//
// Auth, account, student, mentor and admin mentor-approval calls always use the real backend (http).
// The remaining calls (resources, public landing data and the other admin pages) are not built in the
// backend yet and still use dummy data through request(..., mockFn) until VITE_USE_MOCK=false.
import { request, http } from './client'
import db from '@/mock/db'

const byId = (list, id) => list.find((x) => x.id === id)
const fail = (msg) => { throw new Error(msg) }


/* ---------------- Auth (backend/routes/auth.py) ---------------- */
export const authApi = {
  // POST /auth/login  { email, password, remember } -> { token, user }
  login: (data) => http({ url: '/auth/login', method: 'POST', data }),

  // POST /auth/register  { name, email, password, role: 'student' | 'mentor' } -> { token, user }
  register: (data) => http({ url: '/auth/register', method: 'POST', data }),

  // GET /auth/me -> { user }
  me: () => http({ url: '/auth/me' })
}


/* ---------------- Account & form options, students and mentors (backend/routes/account.py) ---------------- */
export const accountApi = {
  // GET /options -> { careerGoals: [{ name, description }], skills: [name], academicLevels: [name] }
  getOptions: () => http({ url: '/options' }),

  // PATCH /account  { name?, email? } -> { user }
  update: (data) => http({ url: '/account', method: 'PATCH', data }),

  // PUT /account/password  { currentPassword, newPassword } -> { message }
  changePassword: (currentPassword, newPassword) =>
    http({ url: '/account/password', method: 'PUT', data: { currentPassword, newPassword } })
}


/* ---------------- Shared (not in the backend yet: dummy data) ---------------- */
export const commonApi = {
  // GET /resources?category=
  getResources: (params = {}) => request({ url: '/resources', params }, () =>
    db.resources.filter((r) => !params.category || params.category === 'All' || r.category === params.category)),

  // GET /public/stats
  getPublicStats: () => request({ url: '/public/stats' }, () => ({ mentors: 150, areas: 10, sessions: 500, feedback: 90 })),

  // GET /public/mentors (featured mentors on landing page)
  getFeaturedMentors: () => request({ url: '/public/mentors' }, () => db.mentors.filter((m) => m.id !== 'm1' && m.accountStatus !== 'suspended').slice(0, 4))
}


/* ---------------- Student (backend/routes/student.py) ---------------- */
export const studentApi = {
  // GET /student/profile
  getProfile: () => http({ url: '/student/profile' }),

  // PUT /student/profile  { academicLevel, programme, dualDegree, bio, careerGoal, linkedin, skills }
  //   -> updated profile incl. { profileCompletion, profileComplete }
  updateProfile: (data) => http({ url: '/student/profile', method: 'PUT', data }),

  // GET /mentors?q=&domain=&availability=&sort=&goal=   (approved mentors only)
  getMentors: (params = {}) => http({ url: '/mentors', params }),

  // GET /mentors/:id
  getMentor: (id) => http({ url: `/mentors/${id}` }),

  // GET /student/requests
  getRequests: () => http({ url: '/student/requests' }),

  // POST /student/requests  { mentorId, goal, message, slot }
  sendRequest: (data) => http({ url: '/student/requests', method: 'POST', data }),

  // PATCH /student/requests/:id/cancel
  cancelRequest: (id) => http({ url: `/student/requests/${id}/cancel`, method: 'PATCH' }),

  // GET /student/mentorship -> active mentorship (mentor, session, chat, action items) or null
  getMentorship: () => http({ url: '/student/mentorship' }),

  // POST /student/mentorship/messages  { text }
  sendMessage: (text) => http({ url: '/student/mentorship/messages', method: 'POST', data: { text } }),

  // PATCH /student/mentorship  { actionItems: [{ id, done }] } | { completed: true }
  updateMentorship: (data) => http({ url: '/student/mentorship', method: 'PATCH', data })
}


/* ---------------- Mentor (backend/routes/mentor.py) ---------------- */
export const mentorApi = {
  // GET /mentor/dashboard   (approved mentors)
  getDashboard: () => http({ url: '/mentor/dashboard' }),

  // GET /mentor/profile
  getProfile: () => http({ url: '/mentor/profile' }),

  // PUT /mentor/profile  { name, workRole, company, workJoiningYear, bio, linkedin, skills, mentoringArea,
  //                       careerPath: [{ title, organization, startYear, endYear }] }
  //   -> updated profile incl. { profileCompletion, profileComplete, approvalStatus }
  updateProfile: (data) => http({ url: '/mentor/profile', method: 'PUT', data }),

  // GET /mentor/availability
  getAvailability: () => http({ url: '/mentor/availability' }),

  // PUT /mentor/availability  { available, maxMentees, timezone, schedule }
  updateAvailability: (data) => http({ url: '/mentor/availability', method: 'PUT', data }),

  // GET /mentor/requests
  getRequests: () => http({ url: '/mentor/requests' }),

  // GET /mentor/students/:id  (profile of a student who sent a request / is a mentee)
  getStudentProfile: (id) => http({ url: `/mentor/students/${id}` }),

  // PATCH /mentor/requests/:id  { status: 'accepted' | 'declined', reason }
  respond: (id, status, reason = '') => http({ url: `/mentor/requests/${id}`, method: 'PATCH', data: { status, reason } }),

  // GET /mentor/mentees -> { list, capacity }
  getMentees: () => http({ url: '/mentor/mentees' }),

  // GET /mentor/conversations -> [{ mentee, lastMessage, unread }]
  getConversations: () => http({ url: '/mentor/conversations' }),

  // GET /mentor/conversations/:menteeId -> { mentee, messages }
  getConversation: (menteeId) => http({ url: `/mentor/conversations/${menteeId}` }),

  // POST /mentor/conversations/:menteeId/messages  { text }
  sendMessage: (menteeId, text) => http({ url: `/mentor/conversations/${menteeId}/messages`, method: 'POST', data: { text } }),

  // GET /mentor/sessions -> { list, mentees, menteeOptions: [{ id, name }] }
  getSessions: () => http({ url: '/mentor/sessions' }),

  // POST /mentor/sessions  { menteeId, date, title, summary, actionItems: [{ text, done }] }
  recordSession: (data) => http({ url: '/mentor/sessions', method: 'POST', data })
}


/* ---------------- Admin helpers (dummy data for the admin pages not in the backend yet) ---------------- */
const ROHIT = 'm1' // mentor whose mentees live in db.mentees / db.incomingRequests

// Every student with their mentorship state:
// active (has a mentor now) · completed (accepted earlier, not current) · pending (request waiting) · unmatched
function allMentees() {
  return db.studentProfiles.map((s) => {
    const mentee = db.mentees.find((m) => m.studentId === s.id)
    const req = db.incomingRequests.find((r) => r.studentId === s.id)
    let status = 'unmatched'
    let mentorId = null
    if (mentee) { status = 'active'; mentorId = ROHIT }
    else if (s.mentorId) { status = 'active'; mentorId = s.mentorId }
    else if (req?.status === 'pending') { status = 'pending'; mentorId = ROHIT }
    else if (req?.status === 'accepted') { status = 'completed'; mentorId = ROHIT }
    const mentor = mentorId ? byId(db.mentors, mentorId) : null
    return {
      ...s,
      accountStatus: s.accountStatus || 'active',
      status,
      mentor: mentor ? { id: mentor.id, name: mentor.name, avatar: mentor.avatar, title: mentor.title } : null,
      progress: mentee?.progress ?? null,
      nextSession: mentee?.nextSession || null
    }
  })
}

function allMentors() {
  const students = allMentees()
  return db.mentors.map((m) => {
    const mentees = students.filter((s) => s.mentor?.id === m.id && s.status === 'active')
    return {
      ...m,
      accountStatus: m.accountStatus || 'active',
      capacity: m.id === ROHIT ? db.availability.maxMentees : m.capacity ?? 3,
      activeMentees: mentees.length,
      menteeList: mentees.map((s) => ({ id: s.id, name: s.name, avatar: s.avatar, careerGoal: s.careerGoal })),
      pendingRequests: students.filter((s) => s.mentor?.id === m.id && s.status === 'pending').length
    }
  })
}

/* ---------------- Admin ---------------- */
export const adminApi = {
  // ---- Mentor approval (backend/routes/admin.py) ----

  // GET /admin/mentor-applications?status=   (all applications when status is empty)
  getApplications: (status) => http({ url: '/admin/mentor-applications', params: { status } }),

  // The backend has no single-application endpoint: the list carries the full details.
  getApplication: async (id) =>
    (await http({ url: '/admin/mentor-applications' })).find((a) => String(a.id) === String(id)) || fail('Application not found'),

  // PATCH /admin/mentor-applications/:id  { status: 'approved' | 'rejected' }
  decideApplication: (id, status) => http({ url: `/admin/mentor-applications/${id}`, method: 'PATCH', data: { status } }),

  // ---- Not in the backend yet (dummy data) ----

  // GET /admin/mentors-list   (approved mentors with their current load)
  getAllMentors: () => request({ url: '/admin/mentors-list' }, allMentors),

  // GET /admin/mentees   (all students with mentorship status)
  getAllMentees: () => request({ url: '/admin/mentees' }, allMentees),

  // GET /admin/students/:id
  getStudentProfile: (id) => request({ url: `/admin/students/${id}` }, () => byId(db.studentProfiles, id) || fail('Student profile not found')),

  // PATCH /admin/users/:id/status  { role: 'mentor' | 'student', accountStatus: 'active' | 'suspended' }
  setAccountStatus: (id, role, accountStatus) => request({ url: `/admin/users/${id}/status`, method: 'PATCH', data: { role, accountStatus } }, () => {
    const u = byId(role === 'mentor' ? db.mentors : db.studentProfiles, id) || fail('User not found')
    u.accountStatus = accountStatus
    return u
  }),

  // GET /admin/overview
  getOverview: () => request({ url: '/admin/overview' }, () => ({
    stats: {
      ...db.adminStats,
      pendingMentors: db.mentorApplications.filter((a) => a.status === 'pending').length,
      openConcerns: db.concerns.filter((c) => ['Open', 'Under review'].includes(c.status)).length
    },
    requestStatus: db.requestStatus,
    trend: db.participation,
    directory: (() => {
      const mentors = allMentors()
      const mentees = allMentees()
      return {
        mentors: mentors.length,
        availableMentors: mentors.filter((m) => m.available).length,
        mentorAvatars: mentors.slice(0, 4).map((m) => ({ name: m.name, avatar: m.avatar })),
        mentees: mentees.length,
        activeMentees: mentees.filter((s) => s.status === 'active').length,
        unmatchedMentees: mentees.filter((s) => s.status === 'unmatched').length,
        menteeAvatars: mentees.slice(0, 4).map((s) => ({ name: s.name, avatar: s.avatar }))
      }
    })()
  })),

  // GET /admin/participation
  getParticipation: () => request({ url: '/admin/participation' }, () => ({ ...db.participation, requestStatus: db.requestStatus })),

  // GET /admin/concerns
  getConcerns: () => request({ url: '/admin/concerns' }, () => db.concerns),

  // PATCH /admin/concerns/:id  { status, notes }
  updateConcern: (id, data) => request({ url: `/admin/concerns/${id}`, method: 'PATCH', data }, () => {
    const c = byId(db.concerns, id)
    if (data.status !== c.status) c.timeline.push({ at: new Date().toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }), text: `Status changed to ${data.status}` })
    Object.assign(c, data)
    return c
  })
}
