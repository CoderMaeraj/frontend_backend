"""Helpers shared by the student, mentor and admin blueprints: request validation,
display formatting (the platform shows every time in IST) and JSON serializers."""
import re
from datetime import datetime, time, timedelta, timezone

from flask import jsonify, request
from sqlalchemy import func

from auth_utils import is_profile_complete
from models import (
    DAYS_OF_WEEK, AccountStatus, ActionItem, ActionItemStatus, CareerGoal, MentoringRequest, Mentorship,
    MentorshipSessionHistory, MentorshipStatus, SessionStatus, SessionSummary, Skill, db,
)

IST = timezone(timedelta(hours=5, minutes=30))
LINKEDIN_RE = re.compile(r"^https?://(www\.)?linkedin\.com/.+", re.I)
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SLOT_DAYS_AHEAD = 14  # how far ahead bookable slots are listed
MAX_SLOTS = 8


# ---------------------------------------------------------------- errors / input

class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def register_error_handler(bp):
    @bp.errorhandler(ApiError)
    def _handle(e):
        db.session.rollback()
        return jsonify({"message": e.message}), e.status


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


def opt_str(data, key, label, max_len, required=False):
    """Stripped string or None. Raises ApiError for wrong types / too long / missing."""
    v = data.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ApiError(f"{label} must be text")
    v = v.strip()
    if required and not v:
        raise ApiError(f"{label} is required")
    if len(v) > max_len:
        raise ApiError(f"{label} must be at most {max_len} characters")
    return v or None


def opt_int(data, key, label, lo, hi, required=False):
    v = data.get(key)
    if v in (None, ""):
        if required:
            raise ApiError(f"{label} is required")
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ApiError(f"{label} must be a whole number between {lo} and {hi}")
    return v


def linkedin_value(data):
    v = opt_str(data, "linkedin", "LinkedIn URL", 255)
    if v and not LINKEDIN_RE.match(v):
        raise ApiError("Enter a valid LinkedIn URL")
    return v


def career_goal_by_name(name, label="Career goal", required=False):
    if name in (None, ""):
        if required:
            raise ApiError(f"{label} is required")
        return None
    if not isinstance(name, str):
        raise ApiError(f"{label} must be text")
    goal = CareerGoal.query.filter_by(goal_name=name.strip()).first()
    if not goal:
        raise ApiError(f"Unknown {label.lower()}: {name}")
    return goal


def skills_by_name(names, max_count=None):
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ApiError("Skills must be a list of skill names")
    unique = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    if max_count and len(unique) > max_count:
        raise ApiError(f"Pick at most {max_count} skills")
    found = {s.skill_name: s for s in Skill.query.filter(Skill.skill_name.in_(unique)).all()} if unique else {}
    missing = [n for n in unique if n not in found]
    if missing:
        raise ApiError("Unknown skill(s): " + ", ".join(missing))
    return [found[n] for n in unique]


def get_or_404(model, ident, message):
    obj = db.session.get(model, ident)
    if obj is None:
        raise ApiError(message, 404)
    return obj


# ---------------------------------------------------------------- time / formatting

def utcnow():
    return datetime.utcnow()


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def to_ist(dt):
    """Stored datetimes are naive UTC."""
    return dt.replace(tzinfo=timezone.utc).astimezone(IST) if dt else None


def fmt_date(d):
    """28 Oct 2026"""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}" if d else None


def fmt_day_date(d):
    """Wed, 4 Nov 2026"""
    return f"{_DAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]} {d.year}" if d else None


def fmt_time(t):
    """4:30 PM"""
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def fmt_range(start, end):
    return f"{fmt_time(start)} – {fmt_time(end)}"


def fmt_month_year(dt):
    return f"{_MONTHS[dt.month - 1]} {dt.year}" if dt else None


def fmt_hhmm(t):
    return f"{t.hour:02d}:{t.minute:02d}"


def parse_hhmm(v, label):
    if not isinstance(v, str) or not re.fullmatch(r"\d{2}:\d{2}", v.strip()):
        raise ApiError(f"{label} must be a time in HH:MM format")
    h, m = map(int, v.strip().split(":"))
    if h > 23 or m > 59:
        raise ApiError(f"{label} must be a valid time")
    return time(h, m)


def parse_display_date(v, label="Date"):
    """Accepts '2026-10-16' or the frontend's en-GB format '16 Oct 2026' (also 'Sept')."""
    if not isinstance(v, str) or not v.strip():
        raise ApiError(f"{label} is required")
    s = v.strip().replace("Sept", "Sep")
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ApiError(f"{label} is not a valid date")


def slot_label(d, start, end):
    """Wed, 4 Nov 2026 · 4:00 PM – 4:30 PM"""
    return f"{fmt_day_date(d)} · {fmt_range(start, end)}"


def parse_slot_label(label):
    """Inverse of slot_label -> (date, start, end), or None if it does not parse."""
    try:
        day_part, time_part = label.split(" · ")
        start_s, end_s = time_part.split(" – ")
        d = datetime.strptime(day_part.split(", ", 1)[1], "%d %b %Y").date()
        start = datetime.strptime(start_s.strip(), "%I:%M %p").time()
        end = datetime.strptime(end_s.strip(), "%I:%M %p").time()
        return d, start, end
    except (ValueError, IndexError, AttributeError):
        return None


def ago(dt):
    if not dt:
        return None
    secs = (datetime.utcnow() - dt).total_seconds()
    if secs < 60:
        return "just now"
    for unit, size in (("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60)):
        n = int(secs // size)
        if n >= 1:
            if unit == "week" and n > 4:
                return fmt_date(to_ist(dt).date())
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"


def chat_time(dt):
    local = to_ist(dt)
    if local.date() == today_ist():
        return fmt_time(local.time())
    return f"{local.day} {_MONTHS[local.month - 1]}, {fmt_time(local.time())}"


# ---------------------------------------------------------------- queries

def mentor_is_discoverable(mentor):
    """Approved, active account and complete profile: the only mentors students may see."""
    return (
        mentor.approved
        and mentor.user.account_status == AccountStatus.ACTIVE
        and is_profile_complete(mentor.user)
    )


def active_mentorships_query(mentor_id=None, student_id=None):
    q = Mentorship.query.join(MentoringRequest, Mentorship.request_id == MentoringRequest.id).filter(
        Mentorship.status == MentorshipStatus.ACTIVE
    )
    if mentor_id is not None:
        q = q.filter(MentoringRequest.mentor_id == mentor_id)
    if student_id is not None:
        q = q.filter(MentoringRequest.student_id == student_id)
    return q


def active_mentee_count(mentor_id):
    return active_mentorships_query(mentor_id=mentor_id).count()


def accepting_requests(mentor):
    return bool(mentor.approved and mentor.available and active_mentee_count(mentor.mentor_id) < mentor.max_mentees)


def completed_session_count(mentor_id):
    return MentorshipSessionHistory.query.filter_by(mentor_id=mentor_id, status=SessionStatus.COMPLETED).count()


def upcoming_session(mentorship):
    return (
        MentorshipSessionHistory.query.filter(
            MentorshipSessionHistory.mentorship_id == mentorship.id,
            MentorshipSessionHistory.status == SessionStatus.BOOKED,
            MentorshipSessionHistory.session_date >= today_ist(),
        )
        .order_by(MentorshipSessionHistory.session_date, MentorshipSessionHistory.start_time)
        .first()
    )


def latest_summary(mentorship):
    return (
        SessionSummary.query.join(MentorshipSessionHistory)
        .filter(MentorshipSessionHistory.mentorship_id == mentorship.id)
        .order_by(SessionSummary.session_date.desc(), SessionSummary.id.desc())
        .first()
    )


def mentorship_progress(mentorship):
    """% of the mentorship's action items that are completed (0 when there are none)."""
    total, done = (
        db.session.query(
            func.count(ActionItem.id),
            func.coalesce(func.sum(db.case((ActionItem.status == ActionItemStatus.COMPLETED, 1), else_=0)), 0),
        )
        .join(MentorshipSessionHistory)
        .filter(MentorshipSessionHistory.mentorship_id == mentorship.id)
        .one()
    )
    return round(100 * done / total) if total else 0


def upcoming_slots(mentor):
    """Next concrete dates for the mentor's active weekly availability ranges."""
    now = now_ist()
    active = [a for a in mentor.availability if a.is_active]
    slots = []
    for offset in range(SLOT_DAYS_AHEAD):
        d = now.date() + timedelta(days=offset)
        weekday = DAYS_OF_WEEK[d.weekday()]
        for a in sorted((a for a in active if a.day_of_week == weekday), key=lambda a: a.start_time):
            if offset == 0 and a.start_time <= now.time().replace(tzinfo=None):
                continue  # already started today
            slots.append(slot_label(d, a.start_time, a.end_time))
            if len(slots) >= MAX_SLOTS:
                return slots
    return slots


# ---------------------------------------------------------------- serializers

def skill_names(rows):
    return [r.skill.skill_name for r in rows]


def career_path_payload(mentor):
    return [
        {
            "stepNumber": c.step_number,
            "title": c.title,
            "organization": c.organization,
            "org": c.organization,
            "startYear": c.start_year,
            "endYear": c.end_year,
            "period": f"{c.start_year or ''} – {c.end_year or 'Present'}".strip(),
        }
        for c in mentor.career_path
    ]


def match_score(mentor, student):
    """0-100: how well a mentor fits the student's career goal and skills.

    50% same career goal as the mentor's mentoring area, 30% share of the student's skills the
    mentor also has, 20% share of the skills linked to the student's goal that the mentor has.
    """
    if not student:
        return 0
    goal = 1.0 if student.career_goal and student.career_goal == mentor.mentoring_areas else 0.0
    mentor_skills = {s.skill_id for s in mentor.skills}
    student_skills = {s.skill_id for s in student.skills}
    overlap = len(mentor_skills & student_skills) / len(student_skills) if student_skills else 0.0
    goal_skills = {link.skill_id for link in student.goal.skills} if student.goal else set()
    relevance = len(mentor_skills & goal_skills) / len(goal_skills) if goal_skills else 0.0
    return round(100 * (0.5 * goal + 0.3 * overlap + 0.2 * relevance))


def mentor_card(mentor, student=None, detail=False):
    """Mentor as shown to students (cards, detail page, request pages)."""
    user = mentor.user
    area = mentor.mentoring_area.goal_name if mentor.mentoring_area else None
    bio = mentor.bio or ""
    first_sentence = re.split(r"(?<=[.!?])\s", bio, maxsplit=1)[0]
    data = {
        "id": mentor.mentor_id,
        "name": user.name,
        "avatar": user.user_photo,
        "photo": user.user_photo,
        "title": mentor.work_role,
        "company": mentor.company,
        "location": None,  # not collected by the mentor profile
        "domain": area,
        "goals": [area] if area else [],
        "tags": skill_names(mentor.skills),
        "experience": mentor.years_of_experience,
        "match": match_score(mentor, student),
        "available": accepting_requests(mentor),
        "rating": None,  # no feedback/rating data is collected yet
        "sessions": completed_session_count(mentor.mentor_id),
        "quote": first_sentence[:140] if first_sentence else None,
        "about": mentor.bio,
        "linkedin": mentor.linkedin,
    }
    if detail:
        data["careerPath"] = career_path_payload(mentor)
        data["slots"] = upcoming_slots(mentor)
    return data


def mentor_brief(mentor):
    return {
        "id": mentor.mentor_id,
        "name": mentor.user.name,
        "avatar": mentor.user.user_photo,
        "title": mentor.work_role,
        "company": mentor.company,
    }


def student_course(student):
    parts = [p for p in (student.programme, student.academic_level) if p]
    return ", ".join(parts) or None


def student_profile_payload(student, include_email=True):
    user = student.user
    past = sum(1 for m in student.mentorships if m.status in (MentorshipStatus.COMPLETED, MentorshipStatus.ENDED))
    return {
        "id": student.student_id,
        "name": user.name,
        "email": user.email if include_email else None,
        "avatar": user.user_photo,
        "academicLevel": student.academic_level,
        "programme": student.programme,
        "dualDegree": student.dual_degree or "",
        "bio": student.bio,
        "careerGoal": student.goal.goal_name if student.goal else None,
        "linkedin": student.linkedin,
        "skills": skill_names(student.skills),
        "joinedOn": fmt_month_year(user.created_at),
        "pastMentorships": past,
    }


def request_slot_label(req):
    if req.preferred_slot and req.preferred_date:
        return slot_label(req.preferred_date, req.preferred_slot.start_time, req.preferred_slot.end_time)
    return None


def message_payload(msg):
    return {
        "id": msg.id,
        "from": msg.sender,
        "text": msg.message,
        "time": chat_time(msg.sent_date),
        "sentAt": msg.sent_date.isoformat() + "Z",
    }


def session_when(session):
    return f"{fmt_day_date(session.session_date)} · {fmt_time(session.start_time)}" if session else None
