# SE-SEP2026-Team-082

# MentorConnect – Frontend

## Getting Started

Follow the steps below to run the frontend application locally.

### Prerequisites

Make sure you have the following installed:

- [Node.js](https://nodejs.org/)
- npm (comes bundled with Node.js)
- Git

### Installation & Setup

**1. Clone the repository**

```bash
git clone https://github.com/23f3001476/SE-SEP2026-Team-082.git
```

**2. Navigate to the frontend directory**

```bash
cd SE-SEP2026-Team-082/frontend
```

**3. Install dependencies**

```bash
npm install
```

**4. Start the development server**

```bash
npm run dev
```

Once the development server starts, open the local URL displayed in your terminal (usually `http://localhost:5173/`) in your browser.

## Tech Stack

- Vue 3
- Vite
- JavaScript
- CSS

## Note

Run all npm commands from inside the `frontend` directory.

# MentorConnect – Backend

Flask + Flask-SQLAlchemy. The full database is defined in `backend/models.py`.
Only the authentication API is implemented so far; the dashboards still show dummy data from `frontend/src/mock/db.js`.

### Setup (from the `backend` directory)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional: change SECRET_KEY, admin login, etc.
flask --app app seed          # creates tables + career goals, skills and the admin account
flask --app app run --debug   # http://localhost:5000
```

`flask --app app reset-db` drops all tables, recreates them and seeds again.

The default admin login is `admin@mentorconnect.local` / `Admin@123` (set `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`).
Students and mentors register from the signup page.

### Auth API

| Method | Endpoint             | Body                                   | Returns            |
|--------|----------------------|----------------------------------------|--------------------|
| POST   | `/api/auth/register` | `{ name, email, password, role }`      | `{ token, user }`  |
| POST   | `/api/auth/login`    | `{ email, password, remember? }`       | `{ token, user }`  |
| GET    | `/api/auth/me`       | header `Authorization: Bearer <token>` | `{ user }`         |

`role` is `student` or `mentor`. `user.profileComplete` is false until the profile reaches
`PROFILE_COMPLETION_THRESHOLD` (default 80%). Until then the frontend only opens the profile page,
and backend routes protected with `@roles_required(...)` return 403.

### Student, Mentor and Admin (mentor approval) APIs

Documented in [`backend/API.md`](backend/API.md). The frontend always uses the real backend for these
(start the backend before the frontend; set `VITE_API_BASE_URL` if it is not on `http://localhost:5000/api`).
Only resources, the landing page and the other admin pages still show dummy data.

Flow: students and mentors sign up and complete their profile → the admin approves the mentor on
**Mentor Approvals** → students find the mentor and send a request → the mentor accepts or declines it.
Pending mentors only see their profile, availability and settings until they are approved (refresh after approval).

Existing databases get the new columns automatically on start-up (`flask --app app migrate` does the same by hand).

Tests (no running server needed): `pytest tests/test_student_mentor_api.py -v`