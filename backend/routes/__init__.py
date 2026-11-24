from routes.account import account_bp
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.mentor import mentor_bp
from routes.student import student_bp

BLUEPRINTS = [auth_bp, account_bp, student_bp, mentor_bp, admin_bp]
