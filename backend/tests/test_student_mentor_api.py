"""
Tests for the Student, Mentor and Admin (mentor approval) APIs.

Unlike test_auth.py these do not need a running server: every test gets its own app with a
fresh temporary SQLite database (seeded with career goals, skills and the admin account).

    cd backend
    pytest tests/test_student_mentor_api.py -v
"""
import json
from datetime import timedelta

import pytest

from app import create_app
from config import Config
from models import MentorshipSessionHistory, User, db
from routes.common import fmt_date, today_ist
from seed import seed

PASSWORD = "secret123"
STUDENT_PROFILE = {
    "academicLevel": "BSc",
    "programme": "B.S. – Data Science and Applications",
    "dualDegree": "",
    "bio": "Third-year student who loves data.",
    "careerGoal": "Jobs",
    "linkedin": "https://www.linkedin.com/in/test-student",
    "skills": ["Python", "SQL"],
}
MENTOR_PROFILE = {
    "name": "Rohit Mentor",
    "workRole": "Product Manager",
    "company": "FinTech Solutions",
    "workJoiningYear": 2018,
    "bio": "I build fintech products. Happy to help with careers.",
    "linkedin": "https://www.linkedin.com/in/test-mentor",
    "skills": ["Python", "Product Management", "SQL"],
    "mentoringArea": "Jobs",
    "careerPath": [
        {"title": "Software Engineer", "organization": "TechCorp", "startYear": 2018, "endYear": 2021},
        {"title": "Product Manager", "organization": "FinTech Solutions", "startYear": 2021, "endYear": None},
    ],
}
EVERY_DAY = [{"day": d, "enabled": True, "ranges": [{"start": "09:00", "end": "10:00"}]}
             for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]


# ---------------------------------------------------------------- fixtures / helpers

@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(tmp_path / "test.db")

    application = create_app(TestConfig)
    with application.app_context():
        seed()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


class Api:
    """Small wrapper so tests read like `api.get(url, token)`."""

    def __init__(self, client):
        self.c = client

    def _h(self, token):
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get(self, url, token=None):
        return self.c.get(url, headers=self._h(token))

    def send(self, method, url, token=None, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        return getattr(self.c, method)(url, data=data, headers=self._h(token), content_type="application/json")

    def post(self, url, token=None, body=None, **kw):
        return self.send("post", url, token, body, **kw)

    def put(self, url, token=None, body=None, **kw):
        return self.send("put", url, token, body, **kw)

    def patch(self, url, token=None, body=None, **kw):
        return self.send("patch", url, token, body, **kw)

    def register(self, role, name="Test User", email=None):
        email = email or f"{name.lower().replace(' ', '.')}.{role}@test.local"
        r = self.post("/api/auth/register", body={"name": name, "email": email, "password": PASSWORD, "role": role})
        assert r.status_code == 201, r.get_json()
        return r.get_json()["token"], r.get_json()["user"]

    def admin(self, app):
        r = self.post("/api/auth/login", body={"email": app.config["ADMIN_EMAIL"], "password": app.config["ADMIN_PASSWORD"]})
        return r.get_json()["token"]

    def student(self, name="Ananya Student", **overrides):
        token, user = self.register("student", name)
        r = self.put("/api/student/profile", token, {**STUDENT_PROFILE, **overrides})
        assert r.status_code == 200, r.get_json()
        return token, r.get_json()

    def mentor(self, app, name="Rohit Mentor", approve=True, availability=True, **overrides):
        token, user = self.register("mentor", name)
        r = self.put("/api/mentor/profile", token, {**MENTOR_PROFILE, "name": name, **overrides})
        assert r.status_code == 200, r.get_json()
        mentor_id = r.get_json()["mentorId"]
        if availability:
            r = self.put("/api/mentor/availability", token, {"available": True, "maxMentees": 3, "schedule": EVERY_DAY})
            assert r.status_code == 200, r.get_json()
        if approve:
            r = self.patch(f"/api/admin/mentor-applications/{mentor_id}", self.admin(app), {"status": "approved"})
            assert r.status_code == 200, r.get_json()
        return token, mentor_id


@pytest.fixture
def api(client):
    return Api(client)


def no_secrets(resp):
    text = resp.get_data(as_text=True).lower()
    return "password" not in text and "scrypt:" not in text and "pbkdf2:" not in text


def matched_pair(api, app, student_name="Ananya Student", mentor_name="Rohit Mentor"):
    """Student + approved mentor with an accepted request. Returns (s_token, m_token, mentor_id, mentee_id)."""
    s_token, _ = api.student(student_name)
    m_token, mentor_id = api.mentor(app, mentor_name)
    slot = api.get(f"/api/mentors/{mentor_id}", s_token).get_json()["slots"][0]
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs", "message": "Hi", "slot": slot})
    assert req.status_code == 201, req.get_json()
    r = api.patch(f"/api/mentor/requests/{req.get_json()['id']}", m_token, {"status": "accepted"})
    assert r.status_code == 200, r.get_json()
    mentee_id = api.get("/api/mentor/mentees", m_token).get_json()["list"][0]["id"]
    return s_token, m_token, mentor_id, mentee_id


# ---------------------------------------------------------------- authentication & authorization

PROTECTED = [
    ("get", "/api/student/profile"), ("put", "/api/student/profile"), ("get", "/api/mentors"), ("get", "/api/mentors/1"),
    ("get", "/api/student/requests"), ("post", "/api/student/requests"), ("patch", "/api/student/requests/1/cancel"),
    ("get", "/api/student/mentorship"), ("patch", "/api/student/mentorship"), ("post", "/api/student/mentorship/messages"),
    ("get", "/api/mentor/profile"), ("put", "/api/mentor/profile"), ("get", "/api/mentor/availability"),
    ("put", "/api/mentor/availability"), ("get", "/api/mentor/dashboard"), ("get", "/api/mentor/requests"),
    ("patch", "/api/mentor/requests/1"), ("get", "/api/mentor/students/1"), ("get", "/api/mentor/mentees"),
    ("get", "/api/mentor/conversations"), ("get", "/api/mentor/conversations/1"),
    ("post", "/api/mentor/conversations/1/messages"), ("get", "/api/mentor/sessions"), ("post", "/api/mentor/sessions"),
    ("get", "/api/admin/mentor-applications"), ("patch", "/api/admin/mentor-applications/1"),
]


@pytest.mark.parametrize("method,url", PROTECTED)
def test_unauthenticated_requests_are_rejected(api, method, url):
    r = api.get(url) if method == "get" else api.send(method, url, body={})
    assert r.status_code == 401


def test_invalid_token_is_rejected(api):
    assert api.get("/api/student/profile", "not-a-token").status_code == 401


def test_wrong_role_is_forbidden(api, app):
    s_token, _ = api.student()
    m_token, _ = api.mentor(app)
    admin = api.admin(app)
    assert api.get("/api/mentor/profile", s_token).status_code == 403
    assert api.get("/api/mentor/requests", s_token).status_code == 403
    assert api.get("/api/admin/mentor-applications", s_token).status_code == 403
    assert api.get("/api/student/profile", m_token).status_code == 403
    assert api.get("/api/mentors", m_token).status_code == 403
    assert api.patch("/api/admin/mentor-applications/1", m_token, {"status": "approved"}).status_code == 403
    assert api.get("/api/student/requests", admin).status_code == 403
    assert api.get("/api/mentor/dashboard", admin).status_code == 403


def test_suspended_account_is_rejected(api, app):
    s_token, profile = api.student()
    with app.app_context():
        db.session.get(User, profile["id"]).account_status = "suspended"
        db.session.commit()
    assert api.get("/api/student/profile", s_token).status_code == 401


# ---------------------------------------------------------------- profile completion

def test_incomplete_student_is_limited_to_profile(api):
    token, user = api.register("student", "New Student")
    assert user["profileComplete"] is False
    assert api.get("/api/student/profile", token).status_code == 200
    for url in ("/api/mentors", "/api/student/requests", "/api/student/mentorship"):
        r = api.get(url, token)
        assert r.status_code == 403 and r.get_json()["message"] == "Please complete your profile first"


def test_student_profile_update_unlocks_app(api):
    token, _ = api.register("student", "New Student")
    r = api.put("/api/student/profile", token, STUDENT_PROFILE)
    body = r.get_json()
    assert r.status_code == 200
    assert body["profileCompletion"] == 100 and body["profileComplete"] is True
    assert body["skills"] == ["Python", "SQL"] and body["careerGoal"] == "Jobs"
    me = api.get("/api/auth/me", token).get_json()["user"]
    assert me["profileComplete"] is True and me["profileCompletion"] == 100
    assert api.get("/api/mentors", token).status_code == 200
    assert no_secrets(r)


def test_student_profile_completion_matches_auth(api):
    token, _ = api.register("student", "Partial Student")
    r = api.put("/api/student/profile", token, {"bio": "Hello", "careerGoal": "Jobs"})
    assert r.get_json()["profileCompletion"] == 33 and r.get_json()["profileComplete"] is False
    assert api.get("/api/auth/me", token).get_json()["user"]["profileCompletion"] == 33
    # LinkedIn is optional: everything else filled is above the 80% threshold
    r = api.put("/api/student/profile", token, {**STUDENT_PROFILE, "linkedin": ""})
    assert r.get_json()["profileCompletion"] == 83 and r.get_json()["profileComplete"] is True


def test_student_profile_skills_can_be_replaced(api):
    token, _ = api.student()
    r = api.put("/api/student/profile", token, {"skills": ["SQL", "Java"]})
    assert r.status_code == 200 and r.get_json()["skills"] == ["SQL", "Java"]


@pytest.mark.parametrize("payload,fragment", [
    ({"academicLevel": "PhD"}, "Academic level"),
    ({"skills": ["Python", "Cooking"]}, "Unknown skill"),
    ({"skills": ["Python", "SQL", "Java", "Design", "Leadership", "Communication"]}, "at most 5"),
    ({"skills": "Python"}, "list"),
    ({"careerGoal": "Astronaut"}, "Unknown career goal"),
    ({"linkedin": "https://example.com/me"}, "LinkedIn"),
    ({"bio": "x" * 301}, "at most 300"),
    ({"bio": 42}, "must be text"),
])
def test_student_profile_validation(api, payload, fragment):
    token, _ = api.register("student", "Val Student")
    r = api.put("/api/student/profile", token, payload)
    assert r.status_code == 400 and fragment in r.get_json()["message"]


def test_profile_rejects_non_json_body(api):
    token, _ = api.register("student", "Val Student")
    assert api.put("/api/student/profile", token, raw="not json").status_code == 400
    assert api.put("/api/student/profile", token, body=[1, 2]).status_code == 400


def test_mentor_profile_update_and_completion(api):
    token, user = api.register("mentor", "New Mentor")
    assert user["approvalStatus"] == "pending" and user["approved"] is False
    assert api.get("/api/mentor/availability", token).status_code == 403  # profile incomplete
    r = api.put("/api/mentor/profile", token, MENTOR_PROFILE)
    body = r.get_json()
    assert r.status_code == 200 and body["profileComplete"] is True and body["profileCompletion"] == 100
    assert body["name"] == "Rohit Mentor" and [c["title"] for c in body["careerPath"]] == ["Software Engineer", "Product Manager"]
    assert body["careerPath"][1]["endYear"] is None
    assert api.get("/api/auth/me", token).get_json()["user"]["name"] == "Rohit Mentor"
    # replacing the career path and skills works (no unique-constraint clashes)
    r = api.put("/api/mentor/profile", token, {"skills": ["SQL"], "careerPath": MENTOR_PROFILE["careerPath"][:1]})
    assert r.get_json()["skills"] == ["SQL"] and len(r.get_json()["careerPath"]) == 1


@pytest.mark.parametrize("payload,fragment", [
    ({"name": ""}, "Name is required"),
    ({"workJoiningYear": 1900}, "between 1950"),
    ({"workJoiningYear": "2018"}, "whole number"),
    ({"careerPath": [{"title": "", "startYear": 2018}]}, "title is required"),
    ({"careerPath": [{"title": "Dev", "startYear": 2020, "endYear": 2019}]}, "end year cannot be before"),
    ({"careerPath": [{"title": "Dev"}]}, "start year is required"),
    ({"mentoringArea": "Astronaut"}, "Unknown mentoring area"),
    ({"skills": ["Juggling"]}, "Unknown skill"),
])
def test_mentor_profile_validation(api, payload, fragment):
    token, _ = api.register("mentor", "Val Mentor")
    r = api.put("/api/mentor/profile", token, payload)
    assert r.status_code == 400 and fragment in r.get_json()["message"]


# ---------------------------------------------------------------- mentor approval

def test_pending_mentor_restrictions(api, app):
    token, mentor_id = api.mentor(app, approve=False)
    assert api.get("/api/mentor/profile", token).status_code == 200
    assert api.get("/api/mentor/availability", token).status_code == 200
    for url in ("/api/mentor/dashboard", "/api/mentor/requests", "/api/mentor/mentees", "/api/mentor/sessions",
                "/api/mentor/conversations"):
        r = api.get(url, token)
        assert r.status_code == 403 and "awaiting admin approval" in r.get_json()["message"]
    s_token, _ = api.student()
    assert api.get("/api/mentors", s_token).get_json() == []
    assert api.get(f"/api/mentors/{mentor_id}", s_token).status_code == 404
    r = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"})
    assert r.status_code == 404


def test_admin_lists_only_submitted_applications(api, app):
    admin = api.admin(app)
    api.register("mentor", "Unfinished Mentor")  # profile not complete -> not an application yet
    _, mentor_id = api.mentor(app, "Complete Mentor", approve=False)
    r = api.get("/api/admin/mentor-applications", admin)
    apps = r.get_json()
    assert r.status_code == 200 and [a["id"] for a in apps] == [mentor_id]
    a = apps[0]
    assert a["status"] == "pending" and a["role"] == "Product Manager" and a["careerPath"] == "Jobs"
    assert a["expertise"] == ["Python", "Product Management", "SQL"] and a["checklist"]["LinkedIn profile"] is True
    assert r.headers["X-Total-Count"] == "1"
    assert no_secrets(r)


def test_admin_status_filter_and_pagination(api, app):
    admin = api.admin(app)
    ids = [api.mentor(app, f"Mentor {n}", approve=False)[1] for n in "ABC"]
    api.patch(f"/api/admin/mentor-applications/{ids[0]}", admin, {"status": "approved"})
    api.patch(f"/api/admin/mentor-applications/{ids[1]}", admin, {"status": "rejected"})
    status_of = lambda s: [a["id"] for a in api.get(f"/api/admin/mentor-applications?status={s}", admin).get_json()]
    assert status_of("pending") == [ids[2]] and status_of("approved") == [ids[0]] and status_of("rejected") == [ids[1]]
    page = api.get("/api/admin/mentor-applications?page=2&perPage=2", admin)
    assert len(page.get_json()) == 1 and page.headers["X-Total-Count"] == "3"
    assert api.get("/api/admin/mentor-applications?status=weird", admin).status_code == 400
    assert api.get("/api/admin/mentor-applications?page=0", admin).status_code == 400


def test_admin_approve_and_reject_transitions(api, app):
    admin = api.admin(app)
    m1_token, m1 = api.mentor(app, "Mentor One", approve=False)
    m2_token, m2 = api.mentor(app, "Mentor Two", approve=False)

    r = api.patch(f"/api/admin/mentor-applications/{m1}", admin, {"status": "approved"})
    assert r.status_code == 200 and r.get_json()["status"] == "approved"
    assert api.get("/api/auth/me", m1_token).get_json()["user"]["approvalStatus"] == "approved"
    assert api.get("/api/mentor/dashboard", m1_token).status_code == 200

    r = api.patch(f"/api/admin/mentor-applications/{m2}", admin, {"status": "Rejected"})
    assert r.status_code == 200 and r.get_json()["status"] == "rejected"
    r = api.get("/api/mentor/requests", m2_token)
    assert r.status_code == 403 and "not approved" in r.get_json()["message"]
    s_token, _ = api.student()
    assert [m["id"] for m in api.get("/api/mentors", s_token).get_json()] == [m1]
    assert api.get(f"/api/mentors/{m2}", s_token).status_code == 404

    # repeated / invalid transitions
    assert api.patch(f"/api/admin/mentor-applications/{m1}", admin, {"status": "approved"}).status_code == 409
    assert api.patch(f"/api/admin/mentor-applications/{m1}", admin, {"status": "rejected"}).status_code == 409
    assert api.patch(f"/api/admin/mentor-applications/{m2}", admin, {"status": "approved"}).status_code == 409
    assert api.patch(f"/api/admin/mentor-applications/{m1}", admin, {"status": "changes_requested"}).status_code == 400
    assert api.patch(f"/api/admin/mentor-applications/{m1}", admin, {}).status_code == 400
    assert api.patch("/api/admin/mentor-applications/9999", admin, {"status": "approved"}).status_code == 404


def test_admin_cannot_approve_incomplete_profile(api, app):
    _, user = api.register("mentor", "Unfinished Mentor")
    r = api.patch(f"/api/admin/mentor-applications/{user['mentorId']}", api.admin(app), {"status": "approved"})
    assert r.status_code == 409


# ---------------------------------------------------------------- discovery

def test_discovery_search_filters_and_sort(api, app):
    s_token, _ = api.student()  # goal Jobs, skills Python + SQL
    _, jobs = api.mentor(app, "Jobs Mentor")
    _, founder = api.mentor(app, "Founder Mentor", workRole="Founder", company="StartupX", workJoiningYear=2010,
                            mentoringArea="Entrepreneurship", skills=["Leadership"])
    m_token_busy, busy = api.mentor(app, "Busy Mentor", availability=False)

    cards = api.get("/api/mentors", s_token).get_json()
    assert [c["id"] for c in cards][0] == jobs  # best match first
    by_id = {c["id"]: c for c in cards}
    assert by_id[jobs]["match"] > by_id[founder]["match"]
    assert by_id[jobs]["title"] == "Product Manager" and by_id[jobs]["tags"] == ["Python", "Product Management", "SQL"]
    assert by_id[busy]["available"] is False and by_id[jobs]["available"] is True

    ids = lambda q: [c["id"] for c in api.get(f"/api/mentors?{q}", s_token).get_json()]
    assert ids("q=startupx") == [founder]
    assert ids("q=leadership") == [founder]
    assert set(ids("goal=Jobs")) == {jobs, busy}
    assert busy not in ids("availability=available")
    assert ids("sort=experience")[0] == founder
    assert api.get("/api/mentors?sort=rating", s_token).status_code == 400


def test_mentor_detail_has_career_path_and_slots(api, app):
    s_token, _ = api.student()
    _, mentor_id = api.mentor(app)
    m = api.get(f"/api/mentors/{mentor_id}", s_token).get_json()
    assert m["careerPath"][0]["org"] == "TechCorp" and m["careerPath"][1]["period"] == "2021 – Present"
    assert 1 <= len(m["slots"]) <= 8 and "9:00 AM – 10:00 AM" in m["slots"][0]
    assert m["goals"] == ["Jobs"]
    assert api.get("/api/mentors/9999", s_token).status_code == 404


# ---------------------------------------------------------------- request workflow

def test_send_and_cancel_request(api, app):
    s_token, _ = api.student()
    _, mentor_id = api.mentor(app)
    slot = api.get(f"/api/mentors/{mentor_id}", s_token).get_json()["slots"][0]
    r = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs", "message": "Hello", "slot": slot})
    req = r.get_json()
    assert r.status_code == 201 and req["status"] == "pending" and req["slot"] == slot
    assert req["mentor"]["name"] == "Rohit Mentor" and req["sentOn"]

    # only one pending request at a time
    _, other = api.mentor(app, "Other Mentor")
    r = api.post("/api/student/requests", s_token, {"mentorId": other, "goal": "Jobs"})
    assert r.status_code == 409 and "one active request" in r.get_json()["message"]

    assert [x["id"] for x in api.get("/api/student/requests", s_token).get_json()] == [req["id"]]
    r = api.patch(f"/api/student/requests/{req['id']}/cancel", s_token)
    assert r.status_code == 200 and r.get_json()["status"] == "cancelled"
    assert api.patch(f"/api/student/requests/{req['id']}/cancel", s_token).status_code == 409
    # after cancelling a new request may be sent
    assert api.post("/api/student/requests", s_token, {"mentorId": other, "goal": "Jobs"}).status_code == 201


@pytest.mark.parametrize("payload,status", [
    ({"goal": "Jobs"}, 400),                                   # missing mentorId
    ({"mentorId": "1", "goal": "Jobs"}, 400),                  # wrong type
    ({"mentorId": 9999, "goal": "Jobs"}, 404),                 # unknown mentor
    ({"mentorId": None, "goal": "Jobs"}, 400),
])
def test_send_request_validation_ids(api, app, payload, status):
    s_token, _ = api.student()
    api.mentor(app)
    assert api.post("/api/student/requests", s_token, payload).status_code == status


def test_send_request_validation_fields(api, app):
    s_token, _ = api.student()
    _, mentor_id = api.mentor(app)
    bad = [
        ({"mentorId": mentor_id}, "Goal is required"),
        ({"mentorId": mentor_id, "goal": "Astronaut"}, "Unknown goal"),
        ({"mentorId": mentor_id, "goal": "Jobs", "message": "x" * 501}, "at most 500"),
        ({"mentorId": mentor_id, "goal": "Jobs", "slot": "tomorrow-ish"}, "not valid"),
        ({"mentorId": mentor_id, "goal": "Jobs", "slot": "Mon, 3 Jan 2000 · 9:00 AM – 10:00 AM"}, "in the past"),
    ]
    for payload, fragment in bad:
        r = api.post("/api/student/requests", s_token, payload)
        assert r.status_code == 400 and fragment in r.get_json()["message"], (payload, r.get_json())


def test_unavailable_mentor_cannot_receive_requests(api, app):
    s_token, _ = api.student()
    _, mentor_id = api.mentor(app, availability=False)  # never switched on "available"
    r = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"})
    assert r.status_code == 409 and "not accepting" in r.get_json()["message"]


def test_students_cannot_touch_each_others_requests(api, app):
    s1, _ = api.student("Student One")
    s2, _ = api.student("Student Two")
    _, mentor_id = api.mentor(app)
    req = api.post("/api/student/requests", s1, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    assert api.get("/api/student/requests", s2).get_json() == []
    assert api.patch(f"/api/student/requests/{req['id']}/cancel", s2).status_code == 404
    assert api.patch("/api/student/requests/9999/cancel", s1).status_code == 404


def test_mentor_accepts_request_and_books_session(api, app):
    s_token, student = api.student()
    m_token, mentor_id = api.mentor(app)
    slot = api.get(f"/api/mentors/{mentor_id}", s_token).get_json()["slots"][0]
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs", "message": "Help!", "slot": slot}).get_json()

    incoming = api.get("/api/mentor/requests", m_token).get_json()
    assert len(incoming) == 1
    inc = incoming[0]
    assert inc["name"] == "Ananya Student" and inc["topic"] == "Jobs" and inc["status"] == "pending" and inc["slot"] == slot
    # email stays private until the mentor accepts
    prof = api.get(f"/api/mentor/students/{inc['studentId']}", m_token).get_json()
    assert prof["email"] is None and prof["skills"] == ["Python", "SQL"] and prof["academicLevel"] == "BSc"

    r = api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "accepted"})
    assert r.status_code == 200 and r.get_json()["status"] == "accepted"
    assert api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "declined"}).status_code == 409
    prof = api.get(f"/api/mentor/students/{inc['studentId']}", m_token).get_json()
    assert prof["email"] == student["email"]

    assert api.get("/api/student/requests", s_token).get_json()[0]["status"] == "accepted"
    ms = api.get("/api/student/mentorship", s_token).get_json()
    assert ms["mentor"]["id"] == mentor_id and ms["session"]["status"] == "booked"
    assert slot.startswith(ms["session"]["date"])
    mentees = api.get("/api/mentor/mentees", m_token).get_json()
    assert mentees["capacity"] == 3 and mentees["list"][0]["name"] == "Ananya Student"
    assert mentees["list"][0]["nextSession"] is not None
    dash = api.get("/api/mentor/dashboard", m_token).get_json()
    assert dash["mentees"] == 1 and dash["pending"] == 0 and len(dash["upcoming"]) == 1


def test_mentor_declines_with_reason(api, app):
    s_token, _ = api.student()
    m_token, mentor_id = api.mentor(app)
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    assert api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "maybe"}).status_code == 400
    assert api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "declined", "reason": "x" * 201}).status_code == 400
    r = api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "declined", "reason": "At capacity"})
    assert r.status_code == 200 and r.get_json()["reason"] == "At capacity"
    mine = api.get("/api/student/requests", s_token).get_json()[0]
    assert mine["status"] == "declined" and mine["reason"] == "At capacity"
    assert api.get("/api/student/mentorship", s_token).get_json() is None


def test_mentors_cannot_touch_other_mentors_requests(api, app):
    s_token, _ = api.student()
    _, mentor_id = api.mentor(app, "Mentor One")
    other_token, _ = api.mentor(app, "Mentor Two")
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    assert api.get("/api/mentor/requests", other_token).get_json() == []
    assert api.patch(f"/api/mentor/requests/{req['id']}", other_token, {"status": "accepted"}).status_code == 404
    assert api.get(f"/api/mentor/students/{req['mentorId']}", other_token).status_code == 404
    student_id = api.get("/api/student/profile", s_token).get_json()["studentId"]
    assert api.get(f"/api/mentor/students/{student_id}", other_token).status_code == 404


def test_cancelled_request_is_hidden_from_mentor(api, app):
    s_token, _ = api.student()
    m_token, mentor_id = api.mentor(app)
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    api.patch(f"/api/student/requests/{req['id']}/cancel", s_token)
    assert api.get("/api/mentor/requests", m_token).get_json() == []
    assert api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "accepted"}).status_code == 404


def test_capacity_limits_acceptance_and_new_requests(api, app):
    m_token, mentor_id = api.mentor(app)
    api.put("/api/mentor/availability", m_token, {"maxMentees": 1})
    s1, _ = api.student("Student One")
    s2, _ = api.student("Student Two")
    r1 = api.post("/api/student/requests", s1, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    r2 = api.post("/api/student/requests", s2, {"mentorId": mentor_id, "goal": "Jobs"}).get_json()
    assert api.patch(f"/api/mentor/requests/{r1['id']}", m_token, {"status": "accepted"}).status_code == 200
    r = api.patch(f"/api/mentor/requests/{r2['id']}", m_token, {"status": "accepted"})
    assert r.status_code == 409 and "full capacity" in r.get_json()["message"]
    # at capacity: shown as unavailable and new requests are refused
    s3, _ = api.student("Student Three")
    assert api.get(f"/api/mentors/{mentor_id}", s3).get_json()["available"] is False
    assert api.post("/api/student/requests", s3, {"mentorId": mentor_id, "goal": "Jobs"}).status_code == 409
    r = api.put("/api/mentor/availability", m_token, {"maxMentees": 0})
    assert r.status_code == 400


# ---------------------------------------------------------------- availability

def test_availability_round_trip(api, app):
    m_token, _ = api.mentor(app, approve=False, availability=False)
    a = api.get("/api/mentor/availability", m_token).get_json()
    assert a["available"] is False and a["timezone"] == "IST" and len(a["schedule"]) == 7
    assert all(not d["enabled"] for d in a["schedule"])

    schedule = [
        {"day": "Monday", "enabled": True, "ranges": [{"start": "14:00", "end": "17:00"}, {"start": "09:00", "end": "12:00"}]},
        {"day": "Thursday", "enabled": False, "ranges": [{"start": "09:00", "end": "17:00"}]},
    ]
    r = api.put("/api/mentor/availability", m_token, {"available": True, "maxMentees": 4, "timezone": "IST", "schedule": schedule})
    body = r.get_json()
    assert r.status_code == 200 and body["available"] is True and body["maxMentees"] == 4
    monday = next(d for d in body["schedule"] if d["day"] == "Monday")
    thursday = next(d for d in body["schedule"] if d["day"] == "Thursday")
    assert monday["enabled"] and [x["start"] for x in monday["ranges"]] == ["09:00", "14:00"]
    assert not thursday["enabled"] and thursday["ranges"][0]["end"] == "17:00"  # kept while switched off

    # unchanged ranges keep their ids (bookings that reference them survive)
    keep = monday["ranges"][0]["id"]
    body = api.put("/api/mentor/availability", m_token, {"schedule": schedule[:1]}).get_json()
    monday = next(d for d in body["schedule"] if d["day"] == "Monday")
    assert monday["ranges"][0]["id"] == keep
    assert not next(d for d in body["schedule"] if d["day"] == "Thursday")["ranges"]


@pytest.mark.parametrize("payload,fragment", [
    ({"schedule": [{"day": "Monday", "enabled": True, "ranges": [{"start": "09:00", "end": "11:00"}, {"start": "10:00", "end": "12:00"}]}]}, "overlap"),
    ({"schedule": [{"day": "Monday", "enabled": True, "ranges": [{"start": "11:00", "end": "10:00"}]}]}, "after start"),
    ({"schedule": [{"day": "Funday", "enabled": True, "ranges": []}]}, "Unknown day"),
    ({"schedule": [{"day": "Monday", "enabled": True, "ranges": [{"start": "9am", "end": "10:00"}]}]}, "HH:MM"),
    ({"schedule": [{"day": "Monday", "enabled": True, "ranges": []}]}, "at least one time range"),
    ({"schedule": [{"day": "Monday", "enabled": False}, {"day": "Monday", "enabled": False}]}, "more than once"),
    ({"maxMentees": 11}, "between 1 and 10"),
    ({"available": "yes"}, "true or false"),
    ({"timezone": "UTC"}, "IST"),
])
def test_availability_validation(api, app, payload, fragment):
    m_token, _ = api.mentor(app, approve=False, availability=False)
    r = api.put("/api/mentor/availability", m_token, payload)
    assert r.status_code == 400 and fragment in r.get_json()["message"]


# ---------------------------------------------------------------- messages, sessions, action items

def test_messaging_between_student_and_mentor(api, app):
    s_token, m_token, _, mentee_id = matched_pair(api, app)
    r = api.post("/api/student/mentorship/messages", s_token, {"text": "Hi mentor"})
    assert r.status_code == 201 and r.get_json()["from"] == "student"
    convos = api.get("/api/mentor/conversations", m_token).get_json()
    assert convos[0]["mentee"]["id"] == mentee_id and convos[0]["lastMessage"]["text"] == "Hi mentor"
    assert convos[0]["unread"] == 1

    r = api.post(f"/api/mentor/conversations/{mentee_id}/messages", m_token, {"text": "Hello student"})
    assert r.status_code == 201 and r.get_json()["from"] == "mentor"
    chat = api.get(f"/api/mentor/conversations/{mentee_id}", m_token).get_json()
    assert [m["text"] for m in chat["messages"]] == ["Hi mentor", "Hello student"]
    assert api.get("/api/mentor/conversations", m_token).get_json()[0]["unread"] == 0
    ms = api.get("/api/student/mentorship", s_token).get_json()
    assert [(m["from"], m["text"]) for m in ms["messages"]] == [("student", "Hi mentor"), ("mentor", "Hello student")]

    assert api.post("/api/student/mentorship/messages", s_token, {"text": "   "}).status_code == 400
    assert api.post(f"/api/mentor/conversations/{mentee_id}/messages", m_token, {}).status_code == 400


def test_messaging_requires_mentorship_and_ownership(api, app):
    s_token, m_token, _, mentee_id = matched_pair(api, app)
    lonely, _ = api.student("Lonely Student")
    assert api.post("/api/student/mentorship/messages", lonely, {"text": "Hi"}).status_code == 409
    other_token, _ = api.mentor(app, "Other Mentor")
    assert api.get(f"/api/mentor/conversations/{mentee_id}", other_token).status_code == 404
    assert api.post(f"/api/mentor/conversations/{mentee_id}/messages", other_token, {"text": "Hi"}).status_code == 404
    assert api.get("/api/mentor/conversations/9999", m_token).status_code == 404


def test_record_session_and_action_items(api, app):
    s_token, m_token, _, mentee_id = matched_pair(api, app)
    sessions = api.get("/api/mentor/sessions", m_token).get_json()
    assert sessions["mentees"] == ["Ananya Student"] and sessions["menteeOptions"][0]["id"] == mentee_id

    body = {
        "mentee": "Ananya Student", "date": fmt_date(today_ist()), "title": "Resume review",
        "summary": "Went through the resume.", "actionItems": [{"text": "Update resume", "done": True}, {"text": "Apply to 3 jobs", "done": False}, {"text": "", "done": False}],
    }
    r = api.post("/api/mentor/sessions", m_token, body)
    s = r.get_json()
    assert r.status_code == 201 and s["status"] == "Completed" and s["title"] == "Resume review"
    assert [a["text"] for a in s["actionItems"]] == ["Update resume", "Apply to 3 jobs"]
    hist = api.get("/api/mentor/sessions", m_token).get_json()["list"]
    assert any(x["id"] == s["id"] and x["summary"] == "Went through the resume." for x in hist)

    mentee = api.get("/api/mentor/mentees", m_token).get_json()["list"][0]
    assert mentee["progress"] == 50 and mentee["lastNote"] == "Went through the resume."
    assert api.get("/api/mentor/dashboard", m_token).get_json()["sessions"] == 1

    ms = api.get("/api/student/mentorship", s_token).get_json()
    items = ms["actionItems"]
    assert [(i["text"], i["done"]) for i in items] == [("Update resume", True), ("Apply to 3 jobs", False)]
    r = api.patch("/api/student/mentorship", s_token, {"actionItems": [{**items[1], "done": True}]})
    assert r.status_code == 200 and all(i["done"] for i in r.get_json()["actionItems"])
    assert api.get("/api/mentor/mentees", m_token).get_json()["list"][0]["progress"] == 100

    # another student cannot tick these items, and bad payloads are rejected
    other_s, _, _, _ = matched_pair(api, app, "Second Student", "Second Mentor")
    assert api.patch("/api/student/mentorship", other_s, {"actionItems": [{"id": items[0]["id"], "done": False}]}).status_code == 404
    assert api.patch("/api/student/mentorship", s_token, {"actionItems": [{"id": items[0]["id"], "done": "yes"}]}).status_code == 400
    assert api.patch("/api/student/mentorship", s_token, {}).status_code == 400


def test_record_session_validation(api, app):
    _, m_token, _, mentee_id = matched_pair(api, app)
    today = fmt_date(today_ist())
    future = fmt_date(today_ist() + timedelta(days=3))
    cases = [
        ({"mentee": "Nobody", "date": today, "summary": "x"}, 404),
        ({"menteeId": 9999, "date": today, "summary": "x"}, 404),
        ({"menteeId": mentee_id, "date": today, "summary": ""}, 400),
        ({"menteeId": mentee_id, "date": "someday", "summary": "x"}, 400),
        ({"menteeId": mentee_id, "date": future, "summary": "x"}, 400),
        ({"menteeId": mentee_id, "date": today, "summary": "x" * 501}, 400),
        ({"menteeId": mentee_id, "date": today, "summary": "x", "actionItems": "do it"}, 400),
    ]
    for payload, status in cases:
        assert api.post("/api/mentor/sessions", m_token, payload).status_code == status, payload
    # ISO dates (and the en-GB 'Sept' spelling) are accepted too
    assert api.post("/api/mentor/sessions", m_token, {"menteeId": mentee_id, "date": today_ist().isoformat(), "summary": "ok"}).status_code == 201


def test_student_marks_past_session_complete(api, app):
    s_token, m_token, _, mentee_id = matched_pair(api, app)
    r = api.patch("/api/student/mentorship", s_token, {"completed": True})
    assert r.status_code == 409  # the booked session is still in the future
    with app.app_context():
        session = MentorshipSessionHistory.query.filter_by(mentorship_id=mentee_id).one()
        session.session_date = today_ist() - timedelta(days=1)
        db.session.commit()
    r = api.patch("/api/student/mentorship", s_token, {"completed": True})
    assert r.status_code == 200 and r.get_json()["completed"] is True
    assert api.patch("/api/student/mentorship", s_token, {"completed": False}).status_code == 400


def test_no_mentorship_returns_null(api):
    s_token, _ = api.student()
    r = api.get("/api/student/mentorship", s_token)
    assert r.status_code == 200 and r.get_json() is None
    assert api.patch("/api/student/mentorship", s_token, {"completed": True}).status_code == 404


def test_cannot_request_current_mentor_again(api, app):
    s_token, _, mentor_id, _ = matched_pair(api, app)
    r = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs"})
    assert r.status_code == 409 and "already have an active mentorship" in r.get_json()["message"]


def test_deleted_availability_does_not_break_requests(api, app):
    s_token, _ = api.student()
    m_token, mentor_id = api.mentor(app)
    slot = api.get(f"/api/mentors/{mentor_id}", s_token).get_json()["slots"][0]
    req = api.post("/api/student/requests", s_token, {"mentorId": mentor_id, "goal": "Jobs", "slot": slot}).get_json()
    # mentor changes all their hours: the old slot row is deleted, the request keeps working
    new_days = [{**d, "ranges": [{"start": "18:00", "end": "19:00"}]} for d in EVERY_DAY]
    assert api.put("/api/mentor/availability", m_token, {"schedule": new_days}).status_code == 200
    assert api.get("/api/student/requests", s_token).get_json()[0]["slot"] is None
    r = api.patch(f"/api/mentor/requests/{req['id']}", m_token, {"status": "accepted"})
    assert r.status_code == 200
    with app.app_context():
        assert MentorshipSessionHistory.query.count() == 0  # no slot left to book


def test_responses_never_expose_secrets(api, app):
    s_token, m_token, mentor_id, mentee_id = matched_pair(api, app)
    admin = api.admin(app)
    for token, url in [
        (s_token, "/api/student/profile"), (s_token, "/api/mentors"), (s_token, f"/api/mentors/{mentor_id}"),
        (s_token, "/api/student/requests"), (s_token, "/api/student/mentorship"), (m_token, "/api/mentor/profile"),
        (m_token, "/api/mentor/requests"), (m_token, "/api/mentor/mentees"), (m_token, "/api/mentor/dashboard"),
        (m_token, f"/api/mentor/conversations/{mentee_id}"), (admin, "/api/admin/mentor-applications"),
    ]:
        r = api.get(url, token)
        assert r.status_code == 200 and no_secrets(r), url


# ---------------------------------------------------------------- form options & account settings

def test_options_come_from_database(api, app):
    s_token, _ = api.register("student", "Opt Student")  # works before the profile is complete
    r = api.get("/api/options", s_token)
    body = r.get_json()
    assert r.status_code == 200
    assert [g["name"] for g in body["careerGoals"]] == ["Internships", "Jobs", "Higher studies", "Freelancing", "Entrepreneurship"]
    assert "Python" in body["skills"] and len(body["skills"]) == 10
    assert body["academicLevels"] == ["Foundation", "Diploma", "BSc", "BS"]
    m_token, _ = api.register("mentor", "Opt Mentor")
    assert api.get("/api/options", m_token).status_code == 200
    assert api.get("/api/options", api.admin(app)).status_code == 403
    assert api.get("/api/options").status_code == 401


def test_update_account_name_and_email(api, app):
    token, user = api.register("student", "Old Name")
    r = api.patch("/api/account", token, {"name": "  New Name ", "email": "New.Email@Test.local"})
    body = r.get_json()["user"]
    assert r.status_code == 200 and body["name"] == "New Name" and body["email"] == "new.email@test.local"
    assert no_secrets(r)
    # the new email works for login, the old one does not
    assert api.post("/api/auth/login", body={"email": "new.email@test.local", "password": PASSWORD}).status_code == 200
    assert api.post("/api/auth/login", body={"email": user["email"], "password": PASSWORD}).status_code == 401
    # validation
    other_token, other = api.register("mentor", "Other Person")
    assert api.patch("/api/account", token, {"email": other["email"]}).status_code == 409
    assert api.patch("/api/account", token, {"email": "not-an-email"}).status_code == 400
    assert api.patch("/api/account", token, {"name": ""}).status_code == 400
    assert api.patch("/api/account", token, {"name": "x" * 121}).status_code == 400
    assert api.patch("/api/account", token, {"email": "new.email@test.local"}).status_code == 200  # own email
    assert api.patch("/api/account", api.admin(app), {"name": "Boss"}).status_code == 403


def test_change_password(api, app):
    token, user = api.register("mentor", "Pw Mentor")
    assert api.put("/api/account/password", token, {"currentPassword": "wrong", "newPassword": "brandnew1"}).status_code == 403
    assert api.put("/api/account/password", token, {"currentPassword": PASSWORD, "newPassword": "123"}).status_code == 400
    assert api.put("/api/account/password", token, {"currentPassword": PASSWORD, "newPassword": PASSWORD}).status_code == 400
    assert api.put("/api/account/password", token, {}).status_code == 400
    r = api.put("/api/account/password", token, {"currentPassword": PASSWORD, "newPassword": "brandnew1"})
    assert r.status_code == 200 and r.get_json() == {"message": "Password updated"}
    assert api.post("/api/auth/login", body={"email": user["email"], "password": PASSWORD}).status_code == 401
    assert api.post("/api/auth/login", body={"email": user["email"], "password": "brandnew1"}).status_code == 200
    assert api.put("/api/account/password", api.admin(app), {"currentPassword": "x", "newPassword": "yyyyyy"}).status_code == 403
