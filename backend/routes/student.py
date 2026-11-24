"""Student APIs. Every route derives the student from the token (g.user); ids in the body
or URL only ever select resources that are then checked for ownership."""
from flask import Blueprint, current_app, g, jsonify, request

from auth_utils import profile_completion, roles_required
from models import (
    ACADEMIC_LEVELS, DAYS_OF_WEEK, AccountStatus, ActionItem, ActionItemStatus, Mentor, MentorAvailability,
    MentoringRequest, Mentorship, MentorshipSessionHistory, Message, RequestStatus, Role, SessionStatus,
    StudentSkill, User, db,
)
from routes.common import (
    ApiError, accepting_requests, active_mentorships_query, career_goal_by_name, fmt_date, fmt_day_date,
    fmt_range, json_body, latest_summary, linkedin_value, mentor_brief, mentor_card,
    mentor_is_discoverable, message_payload, opt_str, parse_slot_label, register_error_handler,
    request_slot_label, skills_by_name, today_ist, upcoming_session, utcnow,
)

student_bp = Blueprint("student", __name__, url_prefix="/api")
register_error_handler(student_bp)

MAX_STUDENT_SKILLS = 5
MAX_MESSAGE = 2000


def _me():
    return g.user.student


def _profile_payload(user):
    s = user.student
    completion = profile_completion(user)
    return {
        "id": user.user_id,
        "studentId": s.student_id,
        "name": user.name,
        "email": user.email,
        "avatar": user.user_photo,
        "academicLevel": s.academic_level,
        "programme": s.programme,
        "dualDegree": s.dual_degree or "",
        "bio": s.bio,
        "careerGoal": s.goal.goal_name if s.goal else None,
        "linkedin": s.linkedin,
        "skills": [r.skill.skill_name for r in s.skills],
        "profileCompletion": completion,
        "profileComplete": completion >= current_app.config["PROFILE_COMPLETION_THRESHOLD"],
    }


# ---------------------------------------------------------------- profile

@student_bp.get("/student/profile")
@roles_required(Role.STUDENT, complete_profile=False)
def get_profile():
    """GET /api/student/profile -> profile incl. profileCompletion / profileComplete"""
    return jsonify(_profile_payload(g.user))


@student_bp.put("/student/profile")
@roles_required(Role.STUDENT, complete_profile=False)
def update_profile():
    """PUT /api/student/profile { academicLevel, programme, dualDegree, bio, careerGoal, linkedin, skills }

    Only the keys that are sent are changed.
    """
    data = json_body()
    s = _me()
    if "academicLevel" in data:
        level = opt_str(data, "academicLevel", "Academic level", 20)
        if level and level not in ACADEMIC_LEVELS:
            raise ApiError("Academic level must be one of: " + ", ".join(ACADEMIC_LEVELS))
        s.academic_level = level
    if "programme" in data:
        s.programme = opt_str(data, "programme", "Programme", 150)
    if "dualDegree" in data:
        s.dual_degree = opt_str(data, "dualDegree", "Dual degree", 150)
    if "bio" in data:
        s.bio = opt_str(data, "bio", "Introduction", 300)
    if "linkedin" in data:
        s.linkedin = linkedin_value(data)
    if "careerGoal" in data:
        goal = career_goal_by_name(data.get("careerGoal"))
        s.career_goal = goal.id if goal else None
    if "skills" in data:
        skills = skills_by_name(data["skills"], MAX_STUDENT_SKILLS)
        s.skills.clear()
        db.session.flush()  # delete old rows first so the (student, skill) unique constraint holds
        s.skills.extend(StudentSkill(skill_id=sk.id) for sk in skills)
    db.session.commit()
    return jsonify(_profile_payload(g.user))


# ---------------------------------------------------------------- mentor discovery

@student_bp.get("/mentors")
@roles_required(Role.STUDENT)
def list_mentors():
    """GET /api/mentors?q=&goal=&domain=&availability=available&sort=match|experience

    Only approved mentors with an active account and a complete profile are returned.
    """
    q = (request.args.get("q") or "").strip().lower()
    goal = (request.args.get("goal") or "").strip()
    domain = (request.args.get("domain") or "").strip()
    only_available = request.args.get("availability") == "available"
    sort = request.args.get("sort") or "match"
    if sort not in ("match", "experience"):
        raise ApiError("sort must be 'match' or 'experience'")

    mentors = (
        Mentor.query.join(User)
        .filter(Mentor.approved.is_(True), User.account_status == AccountStatus.ACTIVE)
        .all()
    )
    student = _me()
    cards = []
    for m in mentors:
        if not mentor_is_discoverable(m):
            continue
        card = mentor_card(m, student)
        if goal and goal not in card["goals"]:
            continue
        if domain and card["domain"] != domain:
            continue
        if only_available and not card["available"]:
            continue
        if q:
            haystack = " ".join(
                str(x) for x in [card["name"], card["title"], card["company"], card["domain"], card["about"], *card["tags"]] if x
            ).lower()
            if q not in haystack:
                continue
        cards.append(card)

    if sort == "experience":
        cards.sort(key=lambda c: (c["experience"] or 0, c["match"]), reverse=True)
    else:
        cards.sort(key=lambda c: (c["match"], c["experience"] or 0), reverse=True)
    return jsonify(cards)


@student_bp.get("/mentors/<int:mentor_id>")
@roles_required(Role.STUDENT)
def get_mentor(mentor_id):
    """GET /api/mentors/:id -> mentor profile with career path and bookable slots"""
    mentor = db.session.get(Mentor, mentor_id)
    if not mentor or not mentor_is_discoverable(mentor):
        raise ApiError("Mentor not found", 404)
    return jsonify(mentor_card(mentor, _me(), detail=True))


# ---------------------------------------------------------------- mentorship requests

def _request_payload(req):
    return {
        "id": req.id,
        "mentorId": req.mentor_id,
        "mentor": mentor_brief(req.mentor),
        "goal": req.goal.goal_name if req.goal else None,
        "message": req.message or "",
        "status": req.status.lower(),
        "sentOn": fmt_date(req.sent_at),
        "sentAt": req.sent_at.isoformat() + "Z",
        "respondedAt": req.responded_at.isoformat() + "Z" if req.responded_at else None,
        "slot": request_slot_label(req),
        "reason": req.decline_reason,
    }


@student_bp.get("/student/requests")
@roles_required(Role.STUDENT)
def list_requests():
    """GET /api/student/requests -> the student's own requests, newest first"""
    reqs = (
        MentoringRequest.query.filter_by(student_id=_me().student_id)
        .order_by(MentoringRequest.sent_at.desc(), MentoringRequest.id.desc())
        .all()
    )
    return jsonify([_request_payload(r) for r in reqs])


def _resolve_slot(mentor, label):
    """Turn a slot label from GET /mentors/:id into (availability row, date)."""
    if label in (None, ""):
        return None, None
    if not isinstance(label, str):
        raise ApiError("Slot must be text")
    parsed = parse_slot_label(label.strip())
    if not parsed:
        raise ApiError("Selected slot is not valid")
    day, start, end = parsed
    if day < today_ist():
        raise ApiError("Selected slot is in the past")
    row = MentorAvailability.query.filter_by(
        mentor_id=mentor.mentor_id, day_of_week=DAYS_OF_WEEK[day.weekday()],
        start_time=start, end_time=end, is_active=True,
    ).first()
    if not row:
        raise ApiError("Selected slot is no longer available")
    return row, day


@student_bp.post("/student/requests")
@roles_required(Role.STUDENT)
def send_request():
    """POST /api/student/requests { mentorId, goal, message?, slot? } -> 201 request"""
    data = json_body()
    student = _me()
    mentor_id = data.get("mentorId")
    if isinstance(mentor_id, bool) or not isinstance(mentor_id, int):
        raise ApiError("mentorId is required")
    mentor = db.session.get(Mentor, mentor_id)
    if not mentor or not mentor_is_discoverable(mentor):
        raise ApiError("Mentor not found", 404)

    goal = career_goal_by_name(data.get("goal"), "Goal", required=True)
    message = opt_str(data, "message", "Message", 500)

    if MentoringRequest.query.filter_by(student_id=student.student_id, status=RequestStatus.PENDING).first():
        raise ApiError("You can have only one active request at a time", 409)
    if active_mentorships_query(mentor_id=mentor.mentor_id, student_id=student.student_id).first():
        raise ApiError("You already have an active mentorship with this mentor", 409)
    if not accepting_requests(mentor):
        raise ApiError("This mentor is not accepting requests right now", 409)
    slot, slot_date = _resolve_slot(mentor, data.get("slot"))

    req = MentoringRequest(
        student_id=student.student_id, mentor_id=mentor.mentor_id, message=message,
        status=RequestStatus.PENDING, career_goal=goal.id,
        preferred_slot_id=slot.id if slot else None, preferred_date=slot_date,
    )
    db.session.add(req)
    db.session.commit()
    return jsonify(_request_payload(req)), 201


@student_bp.patch("/student/requests/<int:request_id>/cancel")
@roles_required(Role.STUDENT)
def cancel_request(request_id):
    """PATCH /api/student/requests/:id/cancel -> request (only pending requests can be cancelled)"""
    req = db.session.get(MentoringRequest, request_id)
    if not req or req.student_id != _me().student_id:
        raise ApiError("Request not found", 404)
    if req.status != RequestStatus.PENDING:
        raise ApiError(f"Only pending requests can be cancelled (this one is {req.status.lower()})", 409)
    req.status = RequestStatus.CANCELLED
    req.responded_at = utcnow()
    db.session.commit()
    return jsonify(_request_payload(req))


# ---------------------------------------------------------------- active mentorship

def _current_mentorship():
    return (
        active_mentorships_query(student_id=_me().student_id)
        .order_by(Mentorship.start_date.desc(), Mentorship.id.desc())
        .first()
    )


def _display_session(ms):
    """The next booked session, otherwise the most recent session of any status."""
    return upcoming_session(ms) or (
        MentorshipSessionHistory.query.filter_by(mentorship_id=ms.id)
        .order_by(MentorshipSessionHistory.session_date.desc(), MentorshipSessionHistory.start_time.desc())
        .first()
    )


def _action_items(ms):
    return (
        ActionItem.query.join(MentorshipSessionHistory)
        .filter(MentorshipSessionHistory.mentorship_id == ms.id)
        .order_by(ActionItem.created_at, ActionItem.id)
        .all()
    )


def _mentorship_payload(ms):
    mentor = ms.mentor
    student = ms.student
    session = _display_session(ms)
    messages = (
        Message.query.filter_by(student_id=student.student_id, mentor_id=mentor.mentor_id)
        .order_by(Message.sent_date, Message.id)
        .all()
    )
    summary = latest_summary(ms)
    return {
        "id": ms.id,
        "status": ms.status.lower(),
        "startDate": ms.start_date.isoformat(),
        "goal": ms.request.goal.goal_name if ms.request.goal else None,
        "mentor": mentor_card(mentor, student),
        "session": {
            "id": session.id if session else None,
            "date": fmt_day_date(session.session_date) if session else None,
            "time": f"{fmt_range(session.start_time, session.end_time)} (IST)" if session else None,
            "link": session.google_meet_link if session else None,
            "status": session.status.lower() if session else None,
        },
        "messages": [message_payload(m) for m in messages],
        "notes": summary.summary if summary else None,
        "actionItems": [
            {"id": a.id, "text": a.description, "done": a.status == ActionItemStatus.COMPLETED} for a in _action_items(ms)
        ],
        "completed": bool(session and session.status == SessionStatus.COMPLETED),
    }


@student_bp.get("/student/mentorship")
@roles_required(Role.STUDENT)
def get_mentorship():
    """GET /api/student/mentorship -> active mentorship (mentor, session, chat, action items) or null"""
    ms = _current_mentorship()
    if ms:
        # Opening the conversation marks the mentor's messages as read.
        Message.query.filter_by(
            student_id=ms.student.student_id, mentor_id=ms.mentor.mentor_id, sender=Role.MENTOR, is_read=False
        ).update({"is_read": True})
        db.session.commit()
    return jsonify(_mentorship_payload(ms) if ms else None)


@student_bp.post("/student/mentorship/messages")
@roles_required(Role.STUDENT)
def send_message():
    """POST /api/student/mentorship/messages { text } -> 201 message"""
    data = json_body()
    text = opt_str(data, "text", "Message", MAX_MESSAGE, required=True)
    ms = _current_mentorship()
    if not ms:
        raise ApiError("Messaging is enabled once a mentor accepts your request", 409)
    msg = Message(
        student_id=ms.student.student_id, mentor_id=ms.mentor.mentor_id, message=text, sender=Role.STUDENT
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify(message_payload(msg)), 201


@student_bp.patch("/student/mentorship")
@roles_required(Role.STUDENT)
def update_mentorship():
    """PATCH /api/student/mentorship { actionItems?: [{ id, done }], completed?: true }

    actionItems ticks/unticks the mentor's action items; completed marks the latest booked
    session that has already taken place as completed.
    """
    data = json_body()
    if "actionItems" not in data and "completed" not in data:
        raise ApiError("Nothing to update: send actionItems and/or completed")
    ms = _current_mentorship()
    if not ms:
        raise ApiError("You do not have an active mentorship", 404)

    if "actionItems" in data:
        items = data["actionItems"]
        if not isinstance(items, list):
            raise ApiError("actionItems must be a list")
        own = {a.id: a for a in _action_items(ms)}
        for it in items:
            if not isinstance(it, dict) or isinstance(it.get("id"), bool) or not isinstance(it.get("id"), int):
                raise ApiError("Each action item needs a numeric id")
            if not isinstance(it.get("done"), bool):
                raise ApiError("Each action item needs done: true/false")
            item = own.get(it["id"])
            if not item:
                raise ApiError(f"Action item {it['id']} not found", 404)
            if it["done"] and item.status != ActionItemStatus.COMPLETED:
                item.status, item.completed_at = ActionItemStatus.COMPLETED, utcnow()
            elif not it["done"] and item.status == ActionItemStatus.COMPLETED:
                item.status, item.completed_at = ActionItemStatus.PENDING, None

    if "completed" in data:
        if data["completed"] is not True:
            raise ApiError("completed can only be set to true")
        session = (
            MentorshipSessionHistory.query.filter(
                MentorshipSessionHistory.mentorship_id == ms.id,
                MentorshipSessionHistory.status == SessionStatus.BOOKED,
                MentorshipSessionHistory.session_date <= today_ist(),
            )
            .order_by(MentorshipSessionHistory.session_date.desc())
            .first()
        )
        if not session:
            raise ApiError("There is no booked session that has already taken place", 409)
        session.status = SessionStatus.COMPLETED

    db.session.commit()
    return jsonify(_mentorship_payload(ms))
