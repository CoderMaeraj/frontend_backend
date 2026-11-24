import re

from flask import Blueprint, g, jsonify, request

from auth_utils import create_token, error, login_required, user_payload
from models import AccountStatus, Mentor, Role, Student, User, db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 6


def _json():
    return request.get_json(silent=True) or {}


@auth_bp.post("/register")
def register():
    """POST /api/auth/register  { name, email, password, role } -> 201 { token, user }"""
    data = _json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip().lower()

    if not name:
        return error("Name is required")
    if len(name) > 120:
        return error("Name is too long")
    if not EMAIL_RE.match(email):
        return error("Enter a valid email")
    if len(password) < MIN_PASSWORD:
        return error(f"Password must be at least {MIN_PASSWORD} characters")
    if role not in Role.SELF_SIGNUP:
        return error("Role must be student or mentor")
    if User.query.filter_by(email=email).first():
        return error("Email already registered", 409)

    user = User(name=name, email=email, role=role, account_status=AccountStatus.ACTIVE)
    user.set_password(password)
    # Every account gets its (empty) role profile; it is filled on the profile-completion page.
    if role == Role.STUDENT:
        user.student = Student()
    else:
        user.mentor = Mentor(available=False, approved=False)

    db.session.add(user)
    db.session.commit()
    return jsonify({"token": create_token(user), "user": user_payload(user)}), 201


@auth_bp.post("/login")
def login():
    """POST /api/auth/login  { email, password, remember? } -> { token, user }"""
    data = _json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return error("Please enter email and password")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return error("Invalid email or password", 401)
    if user.account_status == AccountStatus.SUSPENDED:
        return error("Your account has been suspended. Contact the administrator.", 403)

    return jsonify({"token": create_token(user, bool(data.get("remember"))), "user": user_payload(user)})


@auth_bp.get("/me")
@login_required
def me():
    """GET /api/auth/me -> { user }   (validates the stored token on app load)"""
    return jsonify({"user": user_payload(g.user)})
