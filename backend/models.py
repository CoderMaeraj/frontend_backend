from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class Role:
    STUDENT = "student"
    MENTOR = "mentor"
    ADMIN = "admin"
    FACULTY = "faculty"
    ALL = (STUDENT, MENTOR, ADMIN, FACULTY)
    SELF_SIGNUP = (STUDENT, MENTOR)  # admin / faculty accounts are created by an admin or the seed script


class AccountStatus:
    ACTIVE = "active"
    SUSPENDED = "suspended"


ACADEMIC_LEVELS = ("Foundation", "Diploma", "BSc", "BS")
DAYS_OF_WEEK = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class ApprovalStatus:
    """Mentor application state, derived from Mentor.approved + Mentor.reviewed_at."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RequestStatus:
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    CANCELLED = "Cancelled"


class MentorshipStatus:
    ACTIVE = "Active"
    COMPLETED = "Completed"
    ENDED = "Ended"


class SessionStatus:
    BOOKED = "BOOKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ConcernStatus:
    OPEN = "Open"
    UNDER_REVIEW = "Under review"
    RESOLVED = "Resolved"


class ActionItemStatus:
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)  # hashed
    role = db.Column(db.String(20), nullable=False)  # student / mentor / admin / faculty
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_photo = db.Column(db.String(255))  # relative path to the uploaded photo
    account_status = db.Column(db.String(20), nullable=False, default=AccountStatus.ACTIVE)

    student = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    mentor = db.relationship("Mentor", back_populates="user", uselist=False, cascade="all, delete-orphan")

    reports_made = db.relationship(
        "ConcernReport", foreign_keys="ConcernReport.reported_by", back_populates="reporter"
    )
    reports_received = db.relationship(
        "ConcernReport", foreign_keys="ConcernReport.reported_user_id", back_populates="reported_user"
    )

    def set_password(self, raw):
        self.password = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)

    @property
    def profile(self):
        return self.student if self.role == Role.STUDENT else self.mentor if self.role == Role.MENTOR else None

    def __repr__(self):
        return f"<User {self.user_id} {self.email} ({self.role})>"


class Student(db.Model):
    __tablename__ = "student"

    student_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    academic_level = db.Column(db.String(20))  # Foundation / Diploma / BSc / BS
    programme = db.Column(db.String(150))
    dual_degree = db.Column(db.Text)  # name of the second degree (NULL = single degree)
    bio = db.Column(db.Text)
    career_goal = db.Column(db.Integer, db.ForeignKey("career_goals.id"))
    linkedin = db.Column(db.String(255))

    user = db.relationship("User", back_populates="student")
    goal = db.relationship("CareerGoal")
    skills = db.relationship(
        "StudentSkill", back_populates="student", cascade="all, delete-orphan", order_by="StudentSkill.id"
    )
    requests = db.relationship("MentoringRequest", back_populates="student", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="student", cascade="all, delete-orphan")
    sessions = db.relationship("MentorshipSessionHistory", back_populates="student")

    @property
    def mentorships(self):  # Student 1 ── N Mentorship (through the accepted request)
        return [r.mentorship for r in self.requests if r.mentorship]



class Mentor(db.Model):
    __tablename__ = "mentor"

    mentor_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    work_role = db.Column(db.Text)
    company = db.Column(db.Text)
    bio = db.Column(db.Text)
    work_joining_year = db.Column(db.Integer)
    available = db.Column(db.Boolean, nullable=False, default=False)  # taking mentoring requests
    approved = db.Column(db.Boolean, nullable=False, default=False)  # approved by admin
    mentoring_areas = db.Column(db.Integer, db.ForeignKey("career_goals.id"))
    linkedin = db.Column(db.String(255))
    max_mentees = db.Column(db.Integer, nullable=False, default=3)  # capacity of active mentorships
    reviewed_at = db.Column(db.DateTime)  # when the admin approved/rejected; NULL = not reviewed yet

    user = db.relationship("User", back_populates="mentor")
    mentoring_area = db.relationship("CareerGoal")
    skills = db.relationship(
        "MentorSkill", back_populates="mentor", cascade="all, delete-orphan", order_by="MentorSkill.id"
    )
    availability = db.relationship("MentorAvailability", back_populates="mentor", cascade="all, delete-orphan")
    career_path = db.relationship(
        "MentorCareerPath", back_populates="mentor", cascade="all, delete-orphan",
        order_by="MentorCareerPath.step_number",
    )
    requests = db.relationship("MentoringRequest", back_populates="mentor", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="mentor", cascade="all, delete-orphan")
    sessions = db.relationship("MentorshipSessionHistory", back_populates="mentor")

    @property
    def approval_status(self):
        if self.approved:
            return ApprovalStatus.APPROVED
        return ApprovalStatus.REJECTED if self.reviewed_at else ApprovalStatus.PENDING

    @property
    def years_of_experience(self):
        return max(0, datetime.utcnow().year - self.work_joining_year) if self.work_joining_year else None

    @property
    def mentorships(self):  # Mentor 1 ── N Mentorship (through the accepted request)
        return [r.mentorship for r in self.requests if r.mentorship]


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    skill_name = db.Column(db.Text, unique=True, nullable=False)
    description = db.Column(db.Text)

    career_goals = db.relationship("SkillCareerGoal", back_populates="skill", cascade="all, delete-orphan")


class CareerGoal(db.Model):
    __tablename__ = "career_goals"

    id = db.Column(db.Integer, primary_key=True)
    goal_name = db.Column(db.Text, unique=True, nullable=False)
    description = db.Column(db.Text)

    skills = db.relationship("SkillCareerGoal", back_populates="goal", cascade="all, delete-orphan")


class SkillCareerGoal(db.Model):
    __tablename__ = "skill_career_goals"
    __table_args__ = (db.UniqueConstraint("skill_id", "goal_id"),)

    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    goal_id = db.Column(db.Integer, db.ForeignKey("career_goals.id", ondelete="CASCADE"), nullable=False)

    skill = db.relationship("Skill", back_populates="career_goals")
    goal = db.relationship("CareerGoal", back_populates="skills")



class StudentSkill(db.Model):
    __tablename__ = "student_skills"
    __table_args__ = (db.UniqueConstraint("student_id", "skill_id"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.student_id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)

    student = db.relationship("Student", back_populates="skills")
    skill = db.relationship("Skill")


class MentorSkill(db.Model):
    __tablename__ = "mentor_skills"
    __table_args__ = (db.UniqueConstraint("mentor_id", "skill_id"),)

    id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)

    mentor = db.relationship("Mentor", back_populates="skills")
    skill = db.relationship("Skill")


class MentorAvailability(db.Model):
    __tablename__ = "mentor_availability"

    id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id", ondelete="CASCADE"), nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)  # Monday ... Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    mentor = db.relationship("Mentor", back_populates="availability")



class MentoringRequest(db.Model):
    __tablename__ = "mentoring_request"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.student_id", ondelete="CASCADE"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id", ondelete="CASCADE"), nullable=False)
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.Text, nullable=False, default=RequestStatus.PENDING)
    career_goal = db.Column(db.Integer, db.ForeignKey("career_goals.id"))
    responded_at = db.Column(db.DateTime)
    # Slot the student picked from the mentor's weekly availability (optional)
    preferred_slot_id = db.Column(db.Integer, db.ForeignKey("mentor_availability.id", ondelete="SET NULL"))
    preferred_date = db.Column(db.Date)
    decline_reason = db.Column(db.Text)  # optional note from the mentor, visible to the student

    student = db.relationship("Student", back_populates="requests")
    mentor = db.relationship("Mentor", back_populates="requests")
    goal = db.relationship("CareerGoal")
    preferred_slot = db.relationship("MentorAvailability")
    mentorship = db.relationship("Mentorship", back_populates="request", uselist=False, cascade="all, delete-orphan")


class MentorshipSessionHistory(db.Model):
    __tablename__ = "mentorship_session_history"

    id = db.Column(db.Integer, primary_key=True)
    mentorship_id = db.Column(db.Integer, db.ForeignKey("mentorship.id", ondelete="CASCADE"))
    student_id = db.Column(db.Integer, db.ForeignKey("student.student_id"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id"), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)  # copied from MentorAvailability
    end_time = db.Column(db.Time, nullable=False)  # copied from MentorAvailability
    google_meet_link = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default=SessionStatus.BOOKED)

    mentorship = db.relationship("Mentorship", back_populates="sessions")
    student = db.relationship("Student", back_populates="sessions")
    mentor = db.relationship("Mentor", back_populates="sessions")
    action_items = db.relationship("ActionItem", back_populates="session", cascade="all, delete-orphan")
    summaries = db.relationship("SessionSummary", back_populates="session", cascade="all, delete-orphan")



class Mentorship(db.Model):
    __tablename__ = "mentorship"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("mentoring_request.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status = db.Column(db.Text, nullable=False, default=MentorshipStatus.ACTIVE)
    start_date = db.Column(db.Date, nullable=False, default=lambda: datetime.utcnow().date())
    end_date = db.Column(db.Date)
    mentor_time_slot = db.Column(db.Integer, db.ForeignKey("mentor_availability.id", ondelete="SET NULL"))

    request = db.relationship("MentoringRequest", back_populates="mentorship")
    time_slot = db.relationship("MentorAvailability")
    sessions = db.relationship("MentorshipSessionHistory", back_populates="mentorship", cascade="all, delete-orphan")
    concerns = db.relationship("ConcernReport", back_populates="mentorship")

    @property
    def student(self):
        return self.request.student

    @property
    def mentor(self):
        return self.request.mentor



class Message(db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.student_id", ondelete="CASCADE"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id", ondelete="CASCADE"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    sender = db.Column(db.String(10))  # "student" / "mentor"

    student = db.relationship("Student", back_populates="messages")
    mentor = db.relationship("Mentor", back_populates="messages")



class SessionSummary(db.Model):
    __tablename__ = "session_summary"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("mentorship_session_history.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)  # author (mentor) user
    session_date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(150))
    summary = db.Column(db.Text, nullable=False)

    session = db.relationship("MentorshipSessionHistory", back_populates="summaries")
    user = db.relationship("User")



class ConcernReport(db.Model):
    __tablename__ = "concern_report"

    id = db.Column(db.Integer, primary_key=True)
    reported_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    mentorship_id = db.Column(db.Integer, db.ForeignKey("mentorship.id", ondelete="SET NULL"))
    issue_summary = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default=ConcernStatus.OPEN)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    admin_notes = db.Column(db.Text)

    reporter = db.relationship("User", foreign_keys=[reported_by], back_populates="reports_made")
    reported_user = db.relationship("User", foreign_keys=[reported_user_id], back_populates="reports_received")
    mentorship = db.relationship("Mentorship", back_populates="concerns")



class MentorCareerPath(db.Model):
    __tablename__ = "mentor_career_path"

    id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentor.mentor_id", ondelete="CASCADE"), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    organization = db.Column(db.String(150))
    start_year = db.Column(db.Integer)
    end_year = db.Column(db.Integer)  # NULL = present

    mentor = db.relationship("Mentor", back_populates="career_path")



class ActionItem(db.Model):
    __tablename__ = "action_items"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("mentorship_session_history.id", ondelete="CASCADE"), nullable=False
    )
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=ActionItemStatus.PENDING)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    session = db.relationship("MentorshipSessionHistory", back_populates="action_items")
