import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "mentorconnect.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT access token lifetime (hours). "Remember me" uses the longer one.
    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "24"))
    JWT_REMEMBER_EXPIRES_HOURS = int(os.getenv("JWT_REMEMBER_EXPIRES_HOURS", str(24 * 7)))

    # Profile completion is mandatory: below this %, the user only gets the profile page.
    PROFILE_COMPLETION_THRESHOLD = int(os.getenv("PROFILE_COMPLETION_THRESHOLD", "80"))

    # Frontend origins allowed to call the API.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

    # Seeded admin account (created by `flask --app app seed`).
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mentorconnect.local")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")
