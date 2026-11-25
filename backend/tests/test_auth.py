"""
API tests for the auth endpoints:
    POST /api/auth/register
    POST /api/auth/login

The tests send real HTTP requests, so the backend must be running first:
    cd backend
    flask --app app seed        # creates the admin account used below
    python app.py               # serves on http://127.0.0.1:5000

Then, in another terminal:
    cd backend
    pytest tests/test_auth.py -v
"""

import json
import uuid
from datetime import datetime, timezone

import jwt
import pytest
import requests

from app import app
from models import AccountStatus, Role, User, db

BASE_URL = "http://127.0.0.1:5000"
url_register = f"{BASE_URL}/api/auth/register"
url_login = f"{BASE_URL}/api/auth/login"

HEADER = {"Content-Type": "application/json"}

TEST_EMAIL_DOMAIN = "pytest.mentorconnect.test"
TEST_PASSWORD = "secret123"


# helpers

def unique_email(prefix="user"):
    """A fresh email for each test, so reruns never hit 'Email already registered'."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@{TEST_EMAIL_DOMAIN}"


def register_user(name="Test User", email=None, password=TEST_PASSWORD, role="student"):
    input_dict = {
        "name": name,
        "email": email or unique_email(role),
        "password": password,
        "role": role,
    }
    request = requests.post(url_register, data=json.dumps(input_dict), headers=HEADER)
    return input_dict, request


def token_login_admin():
    input_dict = {
        "email": app.config["ADMIN_EMAIL"],
        "password": app.config["ADMIN_PASSWORD"],
    }
    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)
    return request.json()["token"]


def get_user(email):
    with app.app_context():
        user = User.query.filter_by(email=email.lower()).first()
        if user:
            # Load the relationships while the session is still open.
            _ = user.student, user.mentor
        return user


def decode_token(token):
    return jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_users():
    """Delete every user created by these tests once the module finishes."""
    yield
    with app.app_context():
        for user in User.query.filter(User.email.like(f"%@{TEST_EMAIL_DOMAIN}")).all():
            db.session.delete(user)
        db.session.commit()


# REGISTER

def test_register_student_valid_data():
    input_dict = {
        "name": "Student One",
        "email": unique_email("student"),
        "password": TEST_PASSWORD,
        "role": "student",
    }

    data = json.dumps(input_dict)

    request = requests.post(
        url_register,
        data=data,
        headers=HEADER
    )

    assert request.status_code == 201
    body = request.json()
    assert "token" in body
    assert body["user"]["name"] == input_dict["name"]
    assert body["user"]["email"] == input_dict["email"]
    assert body["user"]["role"] == Role.STUDENT
    assert body["user"]["accountStatus"] == AccountStatus.ACTIVE
    assert body["user"]["profileComplete"] is False
    assert "studentId" in body["user"]

    user = get_user(input_dict["email"])

    assert user is not None
    assert input_dict["name"] == user.name
    assert input_dict["role"] == user.role
    assert user.account_status == AccountStatus.ACTIVE
    assert user.password != input_dict["password"]  # stored hashed
    assert user.student is not None
    assert user.mentor is None
    assert body["user"]["studentId"] == user.student.student_id


def test_register_mentor_valid_data():
    input_dict = {
        "name": "Mentor One",
        "email": unique_email("mentor"),
        "password": TEST_PASSWORD,
        "role": "mentor",
    }

    data = json.dumps(input_dict)

    request = requests.post(
        url_register,
        data=data,
        headers=HEADER
    )

    assert request.status_code == 201
    body = request.json()
    assert "token" in body
    assert body["user"]["role"] == Role.MENTOR
    assert body["user"]["approved"] is False
    assert "mentorId" in body["user"]

    user = get_user(input_dict["email"])

    assert user is not None
    assert input_dict["role"] == user.role
    assert user.mentor is not None
    assert user.student is None
    assert user.mentor.approved is False
    assert user.mentor.available is False
    assert body["user"]["mentorId"] == user.mentor.mentor_id


def test_register_token_belongs_to_new_user():
    input_dict, request = register_user(role="student")

    assert request.status_code == 201

    payload = decode_token(request.json()["token"])
    user = get_user(input_dict["email"])

    assert payload["sub"] == str(user.user_id)
    assert payload["role"] == user.role


def test_register_email_is_normalised():
    raw_email = "  MixedCase_" + uuid.uuid4().hex[:8] + "@" + TEST_EMAIL_DOMAIN.upper() + "  "
    input_dict = {
        "name": "  Spaced Name  ",
        "email": raw_email,
        "password": TEST_PASSWORD,
        "role": "STUDENT",
    }

    data = json.dumps(input_dict)

    request = requests.post(
        url_register,
        data=data,
        headers=HEADER
    )

    assert request.status_code == 201
    assert request.json()["user"]["email"] == raw_email.strip().lower()
    assert request.json()["user"]["name"] == "Spaced Name"
    assert request.json()["user"]["role"] == Role.STUDENT

    user = get_user(raw_email.strip())
    assert user is not None
    assert user.email == raw_email.strip().lower()


def test_register_duplicate_email():
    email = unique_email("dup")
    _, first = register_user(email=email)
    assert first.status_code == 201

    # Same address in a different case must still be rejected.
    _, request = register_user(email=email.upper(), name="Another User")

    assert request.status_code == 409
    assert request.json()["message"] == "Email already registered"

    with app.app_context():
        assert User.query.filter_by(email=email).count() == 1


def test_register_missing_name():
    input_dict, request = register_user(name="")

    assert request.status_code == 400
    assert request.json()["message"] == "Name is required"
    assert get_user(input_dict["email"]) is None


def test_register_whitespace_only_name():
    input_dict, request = register_user(name="     ")

    assert request.status_code == 400
    assert request.json()["message"] == "Name is required"
    assert get_user(input_dict["email"]) is None


def test_register_name_too_long():
    input_dict, request = register_user(name="a" * 121)

    assert request.status_code == 400
    assert request.json()["message"] == "Name is too long"
    assert get_user(input_dict["email"]) is None


def test_register_name_max_length_allowed():
    input_dict, request = register_user(name="a" * 120)

    assert request.status_code == 201
    assert get_user(input_dict["email"]) is not None





def test_register_short_password():
    input_dict, request = register_user(password="12345")

    assert request.status_code == 400
    assert request.json()["message"] == "Password must be at least 6 characters"
    assert get_user(input_dict["email"]) is None


def test_register_password_min_length_allowed():
    input_dict, request = register_user(password="123456")

    assert request.status_code == 201
    assert get_user(input_dict["email"]) is not None


@pytest.mark.parametrize("bad_role", ["admin", "faculty", "", "teacher"])
def test_register_invalid_role(bad_role):
    input_dict, request = register_user(role=bad_role)

    assert request.status_code == 400
    assert request.json()["message"] == "Role must be student or mentor"
    assert get_user(input_dict["email"]) is None


def test_register_empty_body():
    request = requests.post(url_register, data=json.dumps({}), headers=HEADER)

    assert request.status_code == 400
    assert request.json()["message"] == "Name is required"


def test_register_non_json_body():
    request = requests.post(url_register, data="not json", headers={"Content-Type": "text/plain"})

    assert request.status_code == 400
    assert request.json()["message"] == "Name is required"


def test_register_wrong_method():
    request = requests.get(url_register)

    assert request.status_code == 405
    assert request.json()["message"] == "Method not allowed"


# LOGIN

def test_login_student_valid_data():
    registered, _ = register_user(name="Login Student", role="student")

    input_dict = {
        "email": registered["email"],
        "password": registered["password"],
    }

    data = json.dumps(input_dict)

    request = requests.post(
        url_login,
        data=data,
        headers=HEADER
    )

    assert request.status_code == 200
    body = request.json()
    assert "token" in body
    assert body["user"]["email"] == input_dict["email"]
    assert body["user"]["name"] == "Login Student"
    assert body["user"]["role"] == Role.STUDENT

    user = get_user(input_dict["email"])
    payload = decode_token(body["token"])

    assert body["user"]["id"] == user.user_id
    assert payload["sub"] == str(user.user_id)
    assert payload["role"] == user.role


def test_login_mentor_valid_data():
    registered, _ = register_user(name="Login Mentor", role="mentor")

    input_dict = {
        "email": registered["email"],
        "password": registered["password"],
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 200
    assert request.json()["user"]["role"] == Role.MENTOR
    assert request.json()["user"]["approved"] is False


def test_login_admin_valid_data():
    input_dict = {
        "email": app.config["ADMIN_EMAIL"],
        "password": app.config["ADMIN_PASSWORD"],
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 200
    body = request.json()
    assert body["user"]["role"] == Role.ADMIN
    assert body["user"]["profileComplete"] is True  # admins have no profile to fill

    payload = decode_token(token_login_admin())
    assert payload["role"] == Role.ADMIN


def test_login_email_case_insensitive():
    registered, _ = register_user()

    input_dict = {
        "email": "  " + registered["email"].upper() + "  ",
        "password": registered["password"],
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 200
    assert request.json()["user"]["email"] == registered["email"]


def test_login_token_expiry_default():
    registered, _ = register_user()

    input_dict = {"email": registered["email"], "password": registered["password"]}

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 200
    payload = decode_token(request.json()["token"])
    lifetime_hours = (payload["exp"] - payload["iat"]) / 3600
    assert lifetime_hours == app.config["JWT_EXPIRES_HOURS"]
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_login_token_expiry_remember_me():
    registered, _ = register_user()

    input_dict = {
        "email": registered["email"],
        "password": registered["password"],
        "remember": True,
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 200
    payload = decode_token(request.json()["token"])
    lifetime_hours = (payload["exp"] - payload["iat"]) / 3600
    assert lifetime_hours == app.config["JWT_REMEMBER_EXPIRES_HOURS"]


def test_login_wrong_password():
    registered, _ = register_user()

    input_dict = {
        "email": registered["email"],
        "password": "wrong-password",
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 401
    assert request.json()["message"] == "Invalid email or password"
    assert "token" not in request.json()


def test_login_unregistered_email():
    input_dict = {
        "email": unique_email("ghost"),
        "password": TEST_PASSWORD,
    }

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 401
    assert request.json()["message"] == "Invalid email or password"


@pytest.mark.parametrize("input_dict", [
    {"email": "", "password": TEST_PASSWORD},
    {"email": "someone@" + TEST_EMAIL_DOMAIN, "password": ""},
    {"email": "someone@" + TEST_EMAIL_DOMAIN},
    {"password": TEST_PASSWORD},
    {},
])
def test_login_missing_fields(input_dict):
    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 400
    assert request.json()["message"] == "Please enter email and password"


def test_login_suspended_account():
    registered, _ = register_user()

    with app.app_context():
        user = User.query.filter_by(email=registered["email"]).first()
        user.account_status = AccountStatus.SUSPENDED
        db.session.commit()

    input_dict = {"email": registered["email"], "password": registered["password"]}

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 403
    assert request.json()["message"] == "Your account has been suspended. Contact the administrator."
    assert "token" not in request.json()


def test_login_suspended_account_wrong_password():
    """A wrong password on a suspended account must still say 'invalid', not leak the suspension."""
    registered, _ = register_user()

    with app.app_context():
        user = User.query.filter_by(email=registered["email"]).first()
        user.account_status = AccountStatus.SUSPENDED
        db.session.commit()

    input_dict = {"email": registered["email"], "password": "wrong-password"}

    request = requests.post(url_login, data=json.dumps(input_dict), headers=HEADER)

    assert request.status_code == 401
    assert request.json()["message"] == "Invalid email or password"


def test_login_wrong_method():
    request = requests.get(url_login)

    assert request.status_code == 405
    assert request.json()["message"] == "Method not allowed"

@pytest.mark.parametrize("bad_email", [
    "",
    "plainaddress",
    "missing-at.com",
    "user@nodot",
    "user@@double.com",
    "user name@space.com",
])
def test_register_invalid_email(bad_email):
    input_dict, request = register_user(email=bad_email)

    assert request.status_code == 400
    assert request.json()["message"] == "Enter a valid email"