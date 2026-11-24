"""Mentor APIs.

- Profile and availability: any mentor (pending/approved/rejected). Availability needs a complete profile.
- Everything else (requests, mentees, messages, sessions, dashboard): approved mentors only.
"""
from datetime import datetime

from flask import Blueprint, current_app, g, jsonify

from auth_utils import approved_mentor_required, profile_completion, roles_required
from models import (
    DAYS_OF_WEEK, ActionItem, ActionItemStatus, MentorAvailability, MentorCareerPath, MentoringRequest,
    MentorSkill, Mentorship, MentorshipSessionHistory, MentorshipStatus, Message, RequestStatus, Role,
    SessionStatus, SessionSummary, Student, db,
)
from routes.common import (
    ApiError, active_mentee_count, active_mentorships_query, ago, career_goal_by_name, career_path_payload,
    completed_session_count, fmt_date, fmt_range, json_body, latest_summary, linkedin_value, mentorship_progress,
    message_payload, opt_int, opt_str, parse_display_date, parse_hhmm, fmt_hhmm, register_error_handler,
    request_slot_label, session_when, skills_by_name, student_course, student_profile_payload, today_ist,
    upcoming_session, utcnow,
)

mentor_bp = Blueprint("mentor", __name__, url_prefix="/api/mentor")
register_error_handler(mentor_bp)

PLATFORM_TIMEZONE = "IST"
MAX_CAPACITY = 10
MAX_CAREER_STEPS = 20
MAX_RANGES_PER_DAY = 10
MAX_ACTION_ITEMS = 20
MAX_MESSAGE = 2000


def _me():
    return g.user.mentor


# ---------------------------------------------------------------- profile

def _profile_payload(user):
    m = user.mentor
    completion = profile_completion(user)
    return {
        "id": user.user_id,
        "mentorId": m.mentor_id,
        "name": user.name,
        "email": user.email,
        "avatar": user.user_photo,
        "workRole": m.work_role,
        "company": m.company,
        "workJoiningYear": m.work_joining_year,
        "experience": m.years_of_experience,
        "bio": m.bio,
        "linkedin": m.linkedin,
        "skills": [r.skill.skill_name for r in m.skills],
        "mentoringArea": m.mentoring_area.goal_name if m.mentoring_area else None,
        "careerPath": career_path_payload(m),
        "available": m.available,
        "maxMentees": m.max_mentees,
        "approved": m.approved,
        "approvalStatus": m.approval_status,
        "profileCompletion": completion,
        "profileComplete": completion >= current_app.config["PROFILE_COMPLETION_THRESHOLD"],
    }


def _career_steps(raw):
    if not isinstance(raw, list):
        raise ApiError("careerPath must be a list")
    if len(raw) > MAX_CAREER_STEPS:
        raise ApiError(f"At most {MAX_CAREER_STEPS} career steps are allowed")
    this_year = datetime.utcnow().year
    steps = []
    for i, c in enumerate(raw, 1):
        if not isinstance(c, dict):
            raise ApiError("Each career step must be an object")
        label = f"Career step {i}"
        title = opt_str(c, "title", f"{label} title", 150, required=True)
        org = opt_str(c, "organization", f"{label} organisation", 150)
        start = opt_int(c, "startYear", f"{label} start year", 1950, this_year, required=True)
        end = opt_int(c, "endYear", f"{label} end year", 1950, this_year)
        if end is not None and end < start:
            raise ApiError(f"{label}: end year cannot be before the start year")
        steps.append((title, org, start, end))
    return steps


@mentor_bp.get("/profile")
@roles_required(Role.MENTOR, complete_profile=False)
def get_profile():
    """GET /api/mentor/profile"""
    return jsonify(_profile_payload(g.user))


@mentor_bp.put("/profile")
@roles_required(Role.MENTOR, complete_profile=False)
def update_profile():
    """PUT /api/mentor/profile { name, workRole, company, workJoiningYear, bio, linkedin, skills,
    mentoringArea, careerPath: [{ title, organization, startYear, endYear }] }  (only sent keys change)

    `avatar` is ignored: there is no photo upload endpoint yet.
    """
    data = json_body()
    m = _me()
    if "name" in data:
        g.user.name = opt_str(data, "name", "Name", 120, required=True)
    if "workRole" in data:
        m.work_role = opt_str(data, "workRole", "Current role", 150)
    if "company" in data:
        m.company = opt_str(data, "company", "College / company", 150)
    if "workJoiningYear" in data:
        m.work_joining_year = opt_int(data, "workJoiningYear", "Year you started working", 1950, datetime.utcnow().year)
    if "bio" in data:
        m.bio = opt_str(data, "bio", "About you", 300)
    if "linkedin" in data:
        m.linkedin = linkedin_value(data)
    if "mentoringArea" in data:
        goal = career_goal_by_name(data.get("mentoringArea"), "Mentoring area")
        m.mentoring_areas = goal.id if goal else None
    if "skills" in data:
        skills = skills_by_name(data["skills"])
        m.skills.clear()
        db.session.flush()  # delete old rows first so the (mentor, skill) unique constraint holds
        m.skills.extend(MentorSkill(skill_id=s.id) for s in skills)
    if "careerPath" in data:
        steps = _career_steps(data["careerPath"])
        m.career_path.clear()
        db.session.flush()
        m.career_path.extend(
            MentorCareerPath(step_number=i, title=t, organization=o, start_year=s, end_year=e)
            for i, (t, o, s, e) in enumerate(steps, 1)
        )
    db.session.commit()
    return jsonify(_profile_payload(g.user))


# ---------------------------------------------------------------- availability

def _availability_payload(m):
    schedule = []
    for day in DAYS_OF_WEEK:
        rows = sorted((a for a in m.availability if a.day_of_week == day), key=lambda a: a.start_time)
        enabled = any(a.is_active for a in rows)
        shown = [a for a in rows if a.is_active] if enabled else rows
        schedule.append({
            "day": day,
            "enabled": enabled,
            "ranges": [{"id": a.id, "start": fmt_hhmm(a.start_time), "end": fmt_hhmm(a.end_time)} for a in shown],
        })
    return {
        "available": m.available,
        "maxMentees": m.max_mentees,
        "filled": active_mentee_count(m.mentor_id),
        "timezone": PLATFORM_TIMEZONE,
        "schedule": schedule,
    }


def _parse_schedule(raw):
    """-> {(day, start, end): is_active}"""
    if not isinstance(raw, list):
        raise ApiError("schedule must be a list of days")
    seen, wanted = set(), {}
    for d in raw:
        if not isinstance(d, dict):
            raise ApiError("Each schedule entry must be an object")
        day = d.get("day")
        if day not in DAYS_OF_WEEK:
            raise ApiError(f"Unknown day: {day}")
        if day in seen:
            raise ApiError(f"{day} appears more than once")
        seen.add(day)
        enabled = d.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ApiError(f"{day}: enabled must be true or false")
        ranges = d.get("ranges") or []
        if not isinstance(ranges, list) or len(ranges) > MAX_RANGES_PER_DAY:
            raise ApiError(f"{day}: ranges must be a list of at most {MAX_RANGES_PER_DAY} time ranges")
        parsed = []
        for r in ranges:
            if not isinstance(r, dict):
                raise ApiError(f"{day}: each range needs start and end")
            start, end = parse_hhmm(r.get("start"), f"{day} start time"), parse_hhmm(r.get("end"), f"{day} end time")
            if end <= start:
                raise ApiError(f"{day}: end time must be after start time")
            parsed.append((start, end))
        parsed.sort()
        for (s1, e1), (s2, _) in zip(parsed, parsed[1:]):
            if s2 < e1:
                raise ApiError(f"{day}: time ranges overlap ({fmt_hhmm(s1)}–{fmt_hhmm(e1)})")
        if enabled and not parsed:
            raise ApiError(f"{day}: add at least one time range or switch the day off")
        for start, end in parsed:
            wanted[(day, start, end)] = enabled
    return wanted


@mentor_bp.get("/availability")
@roles_required(Role.MENTOR)
def get_availability():
    """GET /api/mentor/availability -> { available, maxMentees, filled, timezone, schedule }"""
    return jsonify(_availability_payload(_me()))


@mentor_bp.put("/availability")
@roles_required(Role.MENTOR)
def update_availability():
    """PUT /api/mentor/availability { available, maxMentees, timezone, schedule: [{ day, enabled, ranges }] }

    Rows matching an existing (day, start, end) are kept so bookings that point at them survive.
    """
    data = json_body()
    m = _me()
    if "timezone" in data and data["timezone"] not in (None, "", PLATFORM_TIMEZONE):
        raise ApiError(f"Only the platform timezone ({PLATFORM_TIMEZONE}) is supported")
    if "available" in data:
        if not isinstance(data["available"], bool):
            raise ApiError("available must be true or false")
        m.available = data["available"]
    if "maxMentees" in data:
        cap = opt_int(data, "maxMentees", "Maximum active mentees", 1, MAX_CAPACITY, required=True)
        filled = active_mentee_count(m.mentor_id)
        if cap < filled:
            raise ApiError(f"You already have {filled} active mentees; capacity cannot be lower than that")
        m.max_mentees = cap
    if "schedule" in data:
        wanted = _parse_schedule(data["schedule"])
        existing = {(a.day_of_week, a.start_time, a.end_time): a for a in m.availability}
        for key, row in existing.items():
            if key in wanted:
                row.is_active = wanted[key]
            else:
                m.availability.remove(row)  # delete-orphan; bookings pointing here are SET NULL
        for key, active in wanted.items():
            if key not in existing:
                day, start, end = key
                m.availability.append(MentorAvailability(day_of_week=day, start_time=start, end_time=end, is_active=active))
    db.session.commit()
    return jsonify(_availability_payload(m))


# ---------------------------------------------------------------- requests

def _request_payload(req):
    s = req.student
    return {
        "id": req.id,
        "studentId": s.student_id,
        "name": s.user.name,
        "avatar": s.user.user_photo,
        "course": student_course(s),
        "institute": None,  # not collected by the student profile
        "goal": s.goal.goal_name if s.goal else None,  # student's overall career goal
        "topic": req.goal.goal_name if req.goal else None,  # goal chosen for this request
        "message": req.message or "",
        "status": req.status.lower(),
        "receivedAgo": ago(req.sent_at),
        "sentOn": fmt_date(req.sent_at),
        "sentAt": req.sent_at.isoformat() + "Z",
        "slot": request_slot_label(req),
        "mode": None,  # not collected when sending a request
        "reason": req.decline_reason,
    }


def _own_request(request_id):
    req = db.session.get(MentoringRequest, request_id)
    if not req or req.mentor_id != _me().mentor_id or req.status == RequestStatus.CANCELLED:
        raise ApiError("Request not found", 404)
    return req


@mentor_bp.get("/requests")
@approved_mentor_required
def list_requests():
    """GET /api/mentor/requests -> incoming requests (pending / accepted / declined), newest first"""
    reqs = (
        MentoringRequest.query.filter(
            MentoringRequest.mentor_id == _me().mentor_id, MentoringRequest.status != RequestStatus.CANCELLED
        )
        .order_by(MentoringRequest.sent_at.desc(), MentoringRequest.id.desc())
        .all()
    )
    return jsonify([_request_payload(r) for r in reqs])


@mentor_bp.patch("/requests/<int:request_id>")
@approved_mentor_required
def respond_request(request_id):
    """PATCH /api/mentor/requests/:id { status: 'accepted' | 'declined', reason? }

    Accepting creates the Mentorship and, if the student picked a slot that is still ahead,
    books that session.
    """
    data = json_body()
    status = data.get("status")
    if not isinstance(status, str) or status.lower() not in ("accepted", "declined"):
        raise ApiError("status must be 'accepted' or 'declined'")
    status = status.lower()
    reason = opt_str(data, "reason", "Reason", 200)
    m = _me()
    req = _own_request(request_id)
    if req.status != RequestStatus.PENDING:
        raise ApiError(f"This request has already been {req.status.lower()}", 409)

    if status == "declined":
        req.status, req.decline_reason, req.responded_at = RequestStatus.DECLINED, reason, utcnow()
        db.session.commit()
        return jsonify(_request_payload(req))

    if active_mentee_count(m.mentor_id) >= m.max_mentees:
        raise ApiError("You are at full capacity. Increase capacity in Availability.", 409)
    if active_mentorships_query(mentor_id=m.mentor_id, student_id=req.student_id).first():
        raise ApiError("You are already mentoring this student", 409)

    req.status, req.responded_at = RequestStatus.ACCEPTED, utcnow()
    slot = req.preferred_slot if req.preferred_slot and req.preferred_slot.is_active else None
    ms = Mentorship(request=req, status=MentorshipStatus.ACTIVE, start_date=today_ist(), time_slot=slot)
    db.session.add(ms)
    if slot and req.preferred_date and req.preferred_date >= today_ist():
        db.session.add(MentorshipSessionHistory(
            mentorship=ms, student_id=req.student_id, mentor_id=m.mentor_id, session_date=req.preferred_date,
            start_time=slot.start_time, end_time=slot.end_time, status=SessionStatus.BOOKED,
        ))
    db.session.commit()
    return jsonify(_request_payload(req))


@mentor_bp.get("/students/<int:student_id>")
@approved_mentor_required
def student_profile(student_id):
    """GET /api/mentor/students/:id -> profile of a student who sent this mentor a request.

    The email is only shared once the mentor has accepted the student.
    """
    student = db.session.get(Student, student_id)
    reqs = MentoringRequest.query.filter(
        MentoringRequest.mentor_id == _me().mentor_id,
        MentoringRequest.student_id == student_id,
        MentoringRequest.status != RequestStatus.CANCELLED,
    ).all() if student else []
    if not reqs:
        raise ApiError("Student profile not found", 404)
    accepted = any(r.status == RequestStatus.ACCEPTED for r in reqs)
    return jsonify(student_profile_payload(student, include_email=accepted))


# ---------------------------------------------------------------- mentees & dashboard

def _mentee_payload(ms):
    s = ms.student
    nxt = upcoming_session(ms)
    note = latest_summary(ms)
    return {
        "id": ms.id,  # mentorship id; used in /conversations/:menteeId
        "studentId": s.student_id,
        "name": s.user.name,
        "avatar": s.user.user_photo,
        "course": student_course(s),
        "institute": None,
        "goal": ms.request.goal.goal_name if ms.request.goal else (s.goal.goal_name if s.goal else None),
        "nextSession": session_when(nxt),
        "lastNote": note.summary if note else None,
        "progress": mentorship_progress(ms),
        "startDate": ms.start_date.isoformat(),
    }


def _active_mentorships():
    return active_mentorships_query(mentor_id=_me().mentor_id).order_by(Mentorship.start_date, Mentorship.id).all()


def _own_mentorship(mentorship_id):
    ms = db.session.get(Mentorship, mentorship_id)
    if not ms or ms.mentor.mentor_id != _me().mentor_id or ms.status != MentorshipStatus.ACTIVE:
        raise ApiError("Mentee not found", 404)
    return ms


@mentor_bp.get("/mentees")
@approved_mentor_required
def list_mentees():
    """GET /api/mentor/mentees -> { list, capacity }"""
    return jsonify({"list": [_mentee_payload(ms) for ms in _active_mentorships()], "capacity": _me().max_mentees})


@mentor_bp.get("/dashboard")
@approved_mentor_required
def dashboard():
    """GET /api/mentor/dashboard -> counts, upcoming sessions and the latest pending requests"""
    m = _me()
    pending = (
        MentoringRequest.query.filter_by(mentor_id=m.mentor_id, status=RequestStatus.PENDING)
        .order_by(MentoringRequest.sent_at.desc())
        .all()
    )
    upcoming = (
        MentorshipSessionHistory.query.filter(
            MentorshipSessionHistory.mentor_id == m.mentor_id,
            MentorshipSessionHistory.status == SessionStatus.BOOKED,
            MentorshipSessionHistory.session_date >= today_ist(),
        )
        .order_by(MentorshipSessionHistory.session_date, MentorshipSessionHistory.start_time)
        .limit(5)
        .all()
    )
    return jsonify({
        "pending": len(pending),
        "mentees": active_mentee_count(m.mentor_id),
        "capacity": m.max_mentees,
        "sessions": completed_session_count(m.mentor_id),
        "rating": None,  # no rating/feedback data is collected yet
        "upcoming": [
            {
                "id": s.id,
                "name": s.student.user.name,
                "avatar": s.student.user.user_photo,
                "when": session_when(s),
                "goal": s.mentorship.request.goal.goal_name if s.mentorship and s.mentorship.request.goal else None,
            }
            for s in upcoming
        ],
        "recentRequests": [_request_payload(r) for r in pending[:3]],
    })


# ---------------------------------------------------------------- messages

def _thread(ms):
    """All messages between the mentor and this mentee (unordered, so it can also be updated)."""
    return Message.query.filter_by(student_id=ms.student.student_id, mentor_id=ms.mentor.mentor_id)


@mentor_bp.get("/conversations")
@approved_mentor_required
def conversations():
    """GET /api/mentor/conversations -> [{ mentee, lastMessage, unread }] for active mentees"""
    out = []
    for ms in _active_mentorships():
        last = _thread(ms).order_by(Message.sent_date.desc(), Message.id.desc()).first()
        unread = _thread(ms).filter_by(sender=Role.STUDENT, is_read=False).count()
        out.append({"mentee": _mentee_payload(ms), "lastMessage": message_payload(last) if last else None, "unread": unread})
    return jsonify(out)


@mentor_bp.get("/conversations/<int:mentee_id>")
@approved_mentor_required
def conversation(mentee_id):
    """GET /api/mentor/conversations/:menteeId -> { mentee, messages } (marks the student's messages read)"""
    ms = _own_mentorship(mentee_id)
    _thread(ms).filter_by(sender=Role.STUDENT, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"mentee": _mentee_payload(ms), "messages": [message_payload(x) for x in _thread(ms).order_by(Message.sent_date, Message.id)]})


@mentor_bp.post("/conversations/<int:mentee_id>/messages")
@approved_mentor_required
def send_message(mentee_id):
    """POST /api/mentor/conversations/:menteeId/messages { text } -> 201 message"""
    data = json_body()
    text = opt_str(data, "text", "Message", MAX_MESSAGE, required=True)
    ms = _own_mentorship(mentee_id)
    msg = Message(student_id=ms.student.student_id, mentor_id=ms.mentor.mentor_id, message=text, sender=Role.MENTOR)
    db.session.add(msg)
    db.session.commit()
    return jsonify(message_payload(msg)), 201


# ---------------------------------------------------------------- sessions

def _session_payload(s):
    summary = max(s.summaries, key=lambda x: x.id) if s.summaries else None
    return {
        "id": s.id,
        "menteeId": s.mentorship_id,
        "mentee": s.student.user.name,
        "date": fmt_date(s.session_date),
        "time": fmt_range(s.start_time, s.end_time),
        "title": summary.title if summary else None,
        "summary": summary.summary if summary else None,
        "status": s.status.capitalize(),
        "actionItems": [
            {"id": a.id, "text": a.description, "done": a.status == ActionItemStatus.COMPLETED} for a in s.action_items
        ],
    }


@mentor_bp.get("/sessions")
@approved_mentor_required
def list_sessions():
    """GET /api/mentor/sessions -> { list, mentees: [names], menteeOptions: [{ id, name }] }"""
    m = _me()
    sessions = (
        MentorshipSessionHistory.query.filter_by(mentor_id=m.mentor_id)
        .order_by(MentorshipSessionHistory.session_date.desc(), MentorshipSessionHistory.start_time.desc())
        .all()
    )
    active = _active_mentorships()
    return jsonify({
        "list": [_session_payload(s) for s in sessions],
        "mentees": [ms.student.user.name for ms in active],
        "menteeOptions": [{"id": ms.id, "name": ms.student.user.name} for ms in active],
    })


def _resolve_mentee(data):
    """Pick the mentorship from menteeId (preferred) or the mentee's name (what the form sends)."""
    if data.get("menteeId") is not None:
        mid = data["menteeId"]
        if isinstance(mid, bool) or not isinstance(mid, int):
            raise ApiError("menteeId must be a number")
        return _own_mentorship(mid)
    name = opt_str(data, "mentee", "Mentee", 120, required=True)
    matches = [ms for ms in _active_mentorships() if ms.student.user.name.strip().lower() == name.lower()]
    if not matches:
        raise ApiError("Mentee not found", 404)
    if len(matches) > 1:
        raise ApiError("More than one mentee has this name; send menteeId instead")
    return matches[0]


def _session_times(ms, day):
    """Times for a session recorded without a booking: the mentorship's slot, else the mentor's
    availability on that weekday, else any of the mentor's availability."""
    if ms.time_slot:
        return ms.time_slot.start_time, ms.time_slot.end_time
    rows = sorted(_me().availability, key=lambda a: (not a.is_active, a.start_time))
    for row in [a for a in rows if a.day_of_week == DAYS_OF_WEEK[day.weekday()]] or rows:
        return row.start_time, row.end_time
    raise ApiError("Set your weekly availability before recording a session", 409)


@mentor_bp.post("/sessions")
@approved_mentor_required
def record_session():
    """POST /api/mentor/sessions { mentee | menteeId, date, title?, summary, actionItems?: [{ text, done }] }

    Completes the booked session on that date if there is one, otherwise records a new completed session.
    """
    data = json_body()
    ms = _resolve_mentee(data)
    day = parse_display_date(data.get("date"), "Session date")
    if day > today_ist():
        raise ApiError("You can only record sessions that have already taken place")
    title = opt_str(data, "title", "Title", 150)
    summary = opt_str(data, "summary", "Session summary", 500, required=True)
    raw_items = data.get("actionItems") or []
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ACTION_ITEMS:
        raise ApiError(f"actionItems must be a list of at most {MAX_ACTION_ITEMS} items")
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            raise ApiError("Each action item must be an object")
        text = opt_str(it, "text", "Action item", 300)
        done = it.get("done", False)
        if not isinstance(done, bool):
            raise ApiError("Action item done must be true or false")
        if text:
            items.append((text, done))

    session = (
        MentorshipSessionHistory.query.filter_by(mentorship_id=ms.id, session_date=day, status=SessionStatus.BOOKED)
        .order_by(MentorshipSessionHistory.start_time)
        .first()
    )
    if session:
        session.status = SessionStatus.COMPLETED
    else:
        start, end = _session_times(ms, day)
        session = MentorshipSessionHistory(
            mentorship=ms, student_id=ms.student.student_id, mentor_id=ms.mentor.mentor_id, session_date=day,
            start_time=start, end_time=end, status=SessionStatus.COMPLETED,
        )
        db.session.add(session)
    session.summaries.append(SessionSummary(user_id=g.user.user_id, session_date=day, title=title, summary=summary))
    now = utcnow()
    for text, done in items:
        session.action_items.append(ActionItem(
            description=text,
            status=ActionItemStatus.COMPLETED if done else ActionItemStatus.PENDING,
            completed_at=now if done else None,
        ))
    db.session.commit()
    return jsonify(_session_payload(session)), 201
