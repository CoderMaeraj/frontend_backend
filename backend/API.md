# MentorConnect API — Student, Mentor and Admin (mentor approval)

All endpoints are under `/api`, take and return JSON, and need `Authorization: Bearer <token>`
from `/api/auth/login` or `/api/auth/register` (see the README for the auth API).
The current user is always taken from the token; ids in URLs/bodies only select resources,
which are then checked for ownership (someone else's resource answers **404**).

**Common responses**

| Status | When |
|--------|------|
| 400 | Invalid / missing fields, wrong types, body is not a JSON object |
| 401 | Missing, invalid or expired token; suspended account |
| 403 | Wrong role · profile below the completion threshold (`"Please complete your profile first"`) · mentor not approved |
| 404 | Unknown id, or a resource that belongs to someone else |
| 409 | Invalid state change (already decided, duplicate pending request, capacity full, …) |

Errors are `{ "message": "..." }`. Passwords, hashes and tokens are never returned.

**Access rules**

- *Profile gate*: until `profileCompletion` ≥ `PROFILE_COMPLETION_THRESHOLD` (80%) only the profile endpoints work.
- *Approval gate* (mentor): new mentors are `pending`. Pending and rejected mentors can use profile and
  availability only; all other mentor endpoints return 403. Only approved mentors appear to students or can receive requests.
- Mentor approval state is `approved` + `reviewed_at`: `approved=true` → approved; `false` with `reviewed_at` → rejected; otherwise pending.
  It is exposed as `approvalStatus` in `/auth/*` user payloads and the mentor profile.
- Times are shown in IST. Dates such as `sentOn` are display strings (`"28 Oct 2026"`); ISO fields (`sentAt`) are also returned.

---

## Shared student/mentor APIs  (role: `student` or `mentor`, no profile gate)

| API | Method & endpoint | Request | Response | DB operations | Frontend |
|---|---|---|---|---|---|
| Form options | `GET /options` | — | `{ careerGoals[{ name, description }], skills[], academicLevels[] }` | read `career_goals`, `skills` | StudentProfile, MentorProfile, FindMentors, SendRequest |
| Update account | `PATCH /account` | `{ name? ≤120, email? }` (email must be unique) | `{ user }` (same shape as `/auth/me`) | update `users` | SettingsView |
| Change password | `PUT /account/password` | `{ currentPassword, newPassword ≥6 }` | `{ message }` (403 if the current password is wrong) | update `users.password` (hashed) | SettingsView |

## Student APIs  (role: `student`)

| API | Method & endpoint | Gate | Request | Response | DB operations | Frontend |
|---|---|---|---|---|---|---|
| Get profile | `GET /student/profile` | — | — | `{ id, studentId, name, email, avatar, academicLevel, programme, dualDegree, bio, careerGoal, linkedin, skills[], profileCompletion, profileComplete }` | read `student`, `student_skills`, `career_goals` | StudentProfile, StudentHome |
| Update profile | `PUT /student/profile` | — | any of `{ academicLevel (Foundation/Diploma/BSc/BS), programme ≤150, dualDegree ≤150, bio ≤300, careerGoal (goal name), linkedin (linkedin.com URL or ""), skills[] ≤5 known names }`; only sent keys change | same as Get profile | update `student`; replace `student_skills` | StudentProfile |
| Browse / search mentors | `GET /mentors?q=&goal=&domain=&availability=available&sort=match\|experience` | profile | — | `[{ id, name, avatar, photo, title, company, location, domain, goals[], tags[], experience, match, available, rating, sessions, quote, about, linkedin }]` | read approved, active, complete mentors + skills, availability, mentorship counts | FindMentors, StudentHome, MentorCard |
| Mentor detail | `GET /mentors/:id` | profile | — | card fields + `careerPath[{ title, organization, org, startYear, endYear, period }]`, `slots[]` (next 14 days, ≤8) | read mentor, `mentor_career_path`, `mentor_availability` | MentorDetail, SendRequest |
| List my requests | `GET /student/requests` | profile | — | `[{ id, mentorId, mentor{ id,name,avatar,title,company }, goal, message, status, sentOn, sentAt, respondedAt, slot, reason }]` | read `mentoring_request` | MyRequests, StudentHome, MentorDetail |
| Send request | `POST /student/requests` | profile | `{ mentorId, goal, message? ≤500, slot? }` (`slot` = one of the mentor's `slots`) | 201 request | insert `mentoring_request` (+ `preferred_slot_id`, `preferred_date`) | SendRequest |
| Cancel request | `PATCH /student/requests/:id/cancel` | profile | — | request (`status: "cancelled"`) | update `mentoring_request` | MyRequests |
| Active mentorship | `GET /student/mentorship` | profile | — | `null`, or `{ id, status, startDate, goal, mentor{card}, session{ id,date,time,link,status }, messages[{ id,from,text,time,sentAt }], notes, actionItems[{ id,text,done }], completed }`; marks mentor messages read | read `mentorship`, `mentorship_session_history`, `message`, `session_summary`, `action_items` | SessionView (Messages), StudentHome |
| Send message | `POST /student/mentorship/messages` | profile | `{ text ≤2000 }` | 201 message | insert `message` (`sender=student`) | SessionView |
| Update mentorship | `PATCH /student/mentorship` | profile | `{ actionItems?: [{ id, done }], completed?: true }` | mentorship (as GET) | update `action_items`; set past booked session `COMPLETED` | SessionView |

Rules: one **pending** request at a time; no request to a mentor you are already matched with; the mentor
must be approved, available and below capacity; only pending requests can be cancelled; `completed`
needs a booked session dated today or earlier. `match` (0–100) = 50% same career goal as the mentor's
area + 30% of the student's skills the mentor has + 20% of the goal's key skills the mentor has.

## Mentor APIs  (role: `mentor`)

| API | Method & endpoint | Gate | Request | Response | DB operations | Frontend |
|---|---|---|---|---|---|---|
| Get profile | `GET /mentor/profile` | — | — | `{ id, mentorId, name, email, avatar, workRole, company, workJoiningYear, experience, bio, linkedin, skills[], mentoringArea, careerPath[], available, maxMentees, approved, approvalStatus, profileCompletion, profileComplete }` | read `mentor`, skills, career path | MentorProfile |
| Update profile | `PUT /mentor/profile` | — | any of `{ name, workRole, company, workJoiningYear (1950–now), bio ≤300, linkedin, skills[], mentoringArea, careerPath[{ title, organization?, startYear, endYear? }] }`; `avatar` is ignored | same as Get | update `users.name`, `mentor`; replace `mentor_skills`, `mentor_career_path` | MentorProfile |
| Get availability | `GET /mentor/availability` | profile | — | `{ available, maxMentees, filled, timezone:"IST", schedule[{ day, enabled, ranges[{ id,start,end }] }] }` | read `mentor_availability` | AvailabilityView, MenteeRequests |
| Update availability | `PUT /mentor/availability` | profile | `{ available?, maxMentees? (1–10, ≥ filled), timezone? ("IST"), schedule?[{ day, enabled, ranges[{ start:"HH:MM", end }] }] }` | same as Get | diff-update `mentor_availability` (unchanged rows keep ids; removed rows are deleted, bookings → NULL) | AvailabilityView |
| Dashboard | `GET /mentor/dashboard` | approved | — | `{ pending, mentees, capacity, sessions, rating:null, upcoming[{ id,name,avatar,when,goal }], recentRequests[≤3] }` | counts over requests/mentorships/sessions | MentorHome |
| Incoming requests | `GET /mentor/requests` | approved | — | `[{ id, studentId, name, avatar, course, institute, goal, topic, message, status, receivedAgo, sentOn, sentAt, slot, mode, reason }]` (cancelled excluded) | read `mentoring_request` | MenteeRequests, MentorHome |
| Accept / decline | `PATCH /mentor/requests/:id` | approved | `{ status: "accepted"\|"declined", reason? ≤200 }` | request | update request; on accept insert `mentorship` (+ booked `mentorship_session_history` for the chosen future slot) | MenteeRequests |
| Student profile | `GET /mentor/students/:id` | approved | — | `{ id, name, email (only after acceptance), avatar, academicLevel, programme, dualDegree, bio, careerGoal, linkedin, skills[], joinedOn, pastMentorships }` | read `student` (must have a non-cancelled request to this mentor) | StudentProfileModal |
| My mentees | `GET /mentor/mentees` | approved | — | `{ list[{ id (mentorship id), studentId, name, avatar, course, institute, goal, nextSession, lastNote, progress, startDate }], capacity }` | read active `mentorship` | MyMentees |
| Conversations | `GET /mentor/conversations` | approved | — | `[{ mentee, lastMessage, unread }]` | read `message` | MentorMessages |
| Conversation | `GET /mentor/conversations/:menteeId` | approved | — | `{ mentee, messages[] }`; marks student messages read | read/update `message` | MentorMessages |
| Send message | `POST /mentor/conversations/:menteeId/messages` | approved | `{ text ≤2000 }` | 201 message | insert `message` (`sender=mentor`) | MentorMessages |
| Session history | `GET /mentor/sessions` | approved | — | `{ list[{ id, menteeId, mentee, date, time, title, summary, status, actionItems[] }], mentees[names], menteeOptions[{ id,name }] }` | read sessions + summaries | SessionsView |
| Record session | `POST /mentor/sessions` | approved | `{ menteeId? \| mentee (name), date ("16 Oct 2026" or ISO, not future), title? ≤150, summary ≤500, actionItems?[{ text, done }] ≤20 }` | 201 session | complete the booked session on that date or insert a completed one; insert `session_summary`, `action_items` | SessionsView |

Rules: accept needs a pending request and free capacity; a request can be answered once; messages and
sessions only for the mentor's own **active** mentorships. `progress` = % of the mentorship's action items completed.

## Admin APIs — mentor approval only  (role: `admin`)

| API | Method & endpoint | Request | Response | DB operations | Frontend |
|---|---|---|---|---|---|
| List applications | `GET /admin/mentor-applications?status=pending\|approved\|rejected&page=&perPage=` | — | `[{ id (mentorId), userId, name, email, avatar, accountStatus, role, company, location, careerPath (mentoring area), careerPathSteps[], expertise[], topics[], experience, workJoiningYear, summary, bio, linkedin, submitted, submittedAt, reviewedAt, status, profileCompletion, checklist{} }]`; header `X-Total-Count` | read `mentor`, `users` | MentorApprovals, MentorReview |
| Approve / reject | `PATCH /admin/mentor-applications/:id` | `{ status: "approved"\|"rejected" }` | application | update `mentor.approved`, `mentor.reviewed_at` | MentorApprovals, MentorReview |

A mentor appears as a *pending application* once their profile is complete. Only pending applications
can be decided (repeat or reverse → 409); only complete profiles can be approved; `changes_requested` is not supported (400).
Without `status` all applications are listed (the admin page filters by tab). `checklist` is derived from the profile.

---

## Schema changes (`migrations.py`)

Applied automatically at start-up (or `flask --app app migrate`); each is a nullable/defaulted column add, no data is changed.

| Column | Why |
|---|---|
| `mentor.max_mentees` (default 3) | Capacity ("Maximum active mentees") |
| `mentor.reviewed_at` | Tells rejected apart from pending |
| `mentoring_request.preferred_slot_id`, `preferred_date` | Slot the student picked; booked as the first session on acceptance |
| `mentoring_request.decline_reason` | Optional reason shown to the student |
| `message.sender` | Who sent each chat message |
| `session_summary.title` | Session title shown in the history |

## Frontend wiring

`frontend/src/api/index.js` calls the backend directly (`http`) for every API above — no dummy data.
Only these still use dummy data from `frontend/src/mock/db.js`, because they need admin-managed content or
are admin pages outside this scope:

- `GET /resources` (Resources page), `GET /public/stats`, `GET /public/mentors` (landing page).
- Admin pages other than mentor approval: overview, all mentors, all mentees, participation, reports.

Not collected anywhere (returned as `null`, hidden in the UI): `rating`, `location`, `institute`, request `mode`.
Not built: photo upload (`avatar` is ignored) and notifications (the Settings toggles are disabled).
