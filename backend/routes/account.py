"""Shared student/mentor APIs: form options from the database and account settings.

These are new endpoints next to the auth API (which is unchanged); the admin account is not served here.
"""
import re

from flask import Blueprint, g, jsonify

from auth_utils import roles_required, user_payload
from models import ACADEMIC_LEVELS, CareerGoal, Role, Skill, User, db
from routes.auth import EMAIL_RE, MIN_PASSWORD
from routes.common import ApiError, json_body, opt_str, register_error_handler

account_bp = Blueprint("account", __name__, url_prefix="/api")
register_error_handler(account_bp)

STUDENT_OR_MENTOR = (Role.STUDENT, Role.MENTOR)


@account_bp.get("/options")
@roles_required(*STUDENT_OR_MENTOR, complete_profile=False)
def options():
    """GET /api/options -> { careerGoals[], skills[], academicLevels[] } (values for the profile/request forms)"""
    return jsonify({
        "careerGoals": [
            {"name": c.goal_name, "description": c.description} for c in CareerGoal.query.order_by(CareerGoal.id)
        ],
        "skills": [s.skill_name for s in Skill.query.order_by(Skill.id)],
        "academicLevels": list(ACADEMIC_LEVELS),
    })


@account_bp.patch("/account")
@roles_required(*STUDENT_OR_MENTOR, complete_profile=False)
def update_account():
    """PATCH /api/account { name?, email? } -> { user }"""
    data = json_body()
    user = g.user
    if "name" in data:
        user.name = opt_str(data, "name", "Name", 120, required=True)
    if "email" in data:
        email = (opt_str(data, "email", "Email", 255, required=True) or "").lower()
        if not EMAIL_RE.match(email):
            raise ApiError("Enter a valid email")
        if email != user.email and User.query.filter_by(email=email).first():
            raise ApiError("Email already registered", 409)
        user.email = email
    db.session.commit()
    return jsonify({"user": user_payload(user)})


@account_bp.put("/account/password")
@roles_required(*STUDENT_OR_MENTOR, complete_profile=False)
def change_password():
    """PUT /api/account/password { currentPassword, newPassword } -> { message }"""
    data = json_body()
    current, new = data.get("currentPassword"), data.get("newPassword")
    if not isinstance(current, str) or not isinstance(new, str) or not current:
        raise ApiError("Enter your current and new password")
    if not g.user.check_password(current):
        raise ApiError("Current password is incorrect", 403)
    if len(new) < MIN_PASSWORD:
        raise ApiError(f"Password must be at least {MIN_PASSWORD} characters")
    if re.fullmatch(r"\s*", new) or new == current:
        raise ApiError("Choose a new password that is different from the current one")
    g.user.set_password(new)
    db.session.commit()
    return jsonify({"message": "Password updated"})
