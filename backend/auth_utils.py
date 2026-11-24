from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from models import AccountStatus, ApprovalStatus, Role, User, db


def error(message, status=400):
    return jsonify({"message": message}), status



def create_token(user, remember=False):
    cfg = current_app.config
    hours = cfg["JWT_REMEMBER_EXPIRES_HOURS"] if remember else cfg["JWT_EXPIRES_HOURS"]
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.user_id), "role": user.role, "iat": now, "exp": now + timedelta(hours=hours)}
    return jwt.encode(payload, cfg["SECRET_KEY"], algorithm="HS256")


def _user_from_request():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, "Missing authorization token"
    try:
        payload = jwt.decode(header[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, "Session expired, please sign in again"
    except jwt.InvalidTokenError:
        return None, "Invalid authorization token"
    user = db.session.get(User, int(payload["sub"]))
    if not user:
        return None, "Account no longer exists"
    if user.account_status == AccountStatus.SUSPENDED:
        return None, "Your account has been suspended. Contact the administrator."
    return user, None


def login_required(fn):
    """Requires a valid token; the user is available as `g.user`."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, err = _user_from_request()
        if err:
            return error(err, 401)
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles, complete_profile=True):
    """Requires a logged-in user with one of `roles`.

    With complete_profile=True (default) students/mentors whose profile is below the
    completion threshold are blocked, so only the profile endpoints work for them.
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if roles and g.user.role not in roles:
                return error("You do not have access to this resource", 403)
            if complete_profile and not is_profile_complete(g.user):
                return error("Please complete your profile first", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


APPROVAL_ERRORS = {
    ApprovalStatus.PENDING: "Your mentor application is awaiting admin approval",
    ApprovalStatus.REJECTED: "Your mentor application was not approved",
}


def approved_mentor_required(fn):
    """Mentor with a complete profile whose application the admin has approved.

    Pending and rejected mentors get 403 (they can still use the profile and availability endpoints).
    """
    @wraps(fn)
    @roles_required(Role.MENTOR)
    def wrapper(*args, **kwargs):
        mentor = g.user.mentor
        if not mentor or not mentor.approved:
            status = mentor.approval_status if mentor else ApprovalStatus.PENDING
            return error(APPROVAL_ERRORS[status], 403)
        return fn(*args, **kwargs)
    return wrapper


def _filled(v):
    return v not in (None, "") and not (isinstance(v, (list, tuple)) and not v)


def profile_completion(user):
    """Percentage (0-100) of role profile fields that are filled in.

    Photo and dual degree are optional and not counted. With the default 80% threshold
    every field below is needed except LinkedIn.
    """
    if user.role == Role.STUDENT:
        s = user.student
        if not s:
            return 0
        fields = [s.academic_level, s.programme, s.bio, s.career_goal, s.skills, s.linkedin]
    elif user.role == Role.MENTOR:
        m = user.mentor
        if not m:
            return 0
        fields = [
            m.work_role, m.company, m.bio, m.work_joining_year,
            m.mentoring_areas, m.skills, m.career_path, m.linkedin,
        ]
    else:  # admin / faculty have no role profile
        return 100
    return round(100 * sum(_filled(f) for f in fields) / len(fields))


def is_profile_complete(user):
    return profile_completion(user) >= current_app.config["PROFILE_COMPLETION_THRESHOLD"]



def user_payload(user):
    completion = profile_completion(user)
    data = {
        "id": user.user_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar": user.user_photo,
        "accountStatus": user.account_status,
        "createdAt": user.created_at.isoformat() if user.created_at else None,
        "profileCompletion": completion,
        "profileComplete": completion >= current_app.config["PROFILE_COMPLETION_THRESHOLD"],
    }
    if user.role == Role.STUDENT and user.student:
        data["studentId"] = user.student.student_id
    if user.role == Role.MENTOR and user.mentor:
        data["mentorId"] = user.mentor.mentor_id
        data["approved"] = user.mentor.approved
        data["approvalStatus"] = user.mentor.approval_status
    return data
