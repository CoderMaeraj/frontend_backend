"""Admin APIs - limited to mentor application review (two endpoints)."""
from flask import Blueprint, jsonify, request

from auth_utils import is_profile_complete, profile_completion, roles_required
from models import ApprovalStatus, Mentor, Role, User, db
from routes.common import ApiError, career_path_payload, fmt_date, json_body, register_error_handler, utcnow

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")
register_error_handler(admin_bp)

DECISIONS = (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
MAX_PER_PAGE = 100


def _application_payload(m):
    user = m.user
    skills = [r.skill.skill_name for r in m.skills]
    years = m.years_of_experience
    return {
        "id": m.mentor_id,
        "userId": user.user_id,
        "name": user.name,
        "email": user.email,
        "avatar": user.user_photo,
        "accountStatus": user.account_status,
        "role": m.work_role,
        "company": m.company,
        "location": None,  # not collected by the mentor profile
        "careerPath": m.mentoring_area.goal_name if m.mentoring_area else None,  # mentoring area
        "careerPathSteps": career_path_payload(m),
        "expertise": skills,
        "topics": skills,
        "experience": f"{years} year{'s' if years != 1 else ''}" if years is not None else None,
        "workJoiningYear": m.work_joining_year,
        "summary": m.bio,
        "bio": m.bio,
        "linkedin": m.linkedin,
        "submitted": fmt_date(user.created_at),
        "submittedAt": user.created_at.isoformat() + "Z",
        "reviewedAt": m.reviewed_at.isoformat() + "Z" if m.reviewed_at else None,
        "status": m.approval_status,
        "profileCompletion": profile_completion(user),
        # Derived from the profile itself; the admin UI shows these as verification items.
        "checklist": {
            "Professional background": bool(m.work_role and m.company and m.work_joining_year),
            "Career path": bool(m.career_path),
            "Skills & expertise": bool(skills),
            "Mentoring area": bool(m.mentoring_areas),
            "Mentor statement": bool(m.bio),
            "LinkedIn profile": bool(m.linkedin),
        },
    }


@admin_bp.get("/mentor-applications")
@roles_required(Role.ADMIN)
def list_applications():
    """GET /api/admin/mentor-applications?status=pending|approved|rejected&page=&perPage=

    A pending application is a mentor who has completed their profile and not been reviewed yet
    (mentors still filling in their profile have not applied). Without `status` all are returned.
    Pagination is optional; the total is in the X-Total-Count header.
    """
    status = (request.args.get("status") or "").strip().lower()
    if status and status not in (ApprovalStatus.PENDING, *DECISIONS):
        raise ApiError("status must be pending, approved or rejected")

    mentors = Mentor.query.join(User).order_by(User.created_at.desc(), Mentor.mentor_id.desc()).all()
    apps = [
        m for m in mentors
        if (m.approval_status != ApprovalStatus.PENDING or is_profile_complete(m.user))
        and (not status or m.approval_status == status)
    ]
    total = len(apps)

    if "page" in request.args or "perPage" in request.args:
        try:
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("perPage", 20))
        except ValueError:
            raise ApiError("page and perPage must be numbers")
        if page < 1 or not 1 <= per_page <= MAX_PER_PAGE:
            raise ApiError(f"page must be >= 1 and perPage between 1 and {MAX_PER_PAGE}")
        apps = apps[(page - 1) * per_page: page * per_page]

    resp = jsonify([_application_payload(m) for m in apps])
    resp.headers["X-Total-Count"] = str(total)
    return resp


@admin_bp.patch("/mentor-applications/<int:mentor_id>")
@roles_required(Role.ADMIN)
def decide_application(mentor_id):
    """PATCH /api/admin/mentor-applications/:id { status: 'approved' | 'rejected' } -> application

    Only pending applications can be decided, and only complete profiles can be approved.
    """
    data = json_body()
    decision = data.get("status")
    if not isinstance(decision, str) or decision.lower() not in DECISIONS:
        raise ApiError("status must be 'approved' or 'rejected'")
    decision = decision.lower()

    mentor = db.session.get(Mentor, mentor_id)
    if not mentor:
        raise ApiError("Application not found", 404)
    if mentor.approval_status != ApprovalStatus.PENDING:
        raise ApiError(f"This application has already been {mentor.approval_status}", 409)
    if not is_profile_complete(mentor.user):
        raise ApiError("This mentor has not completed their profile yet", 409)

    mentor.approved = decision == ApprovalStatus.APPROVED
    mentor.reviewed_at = utcnow()
    db.session.commit()
    return jsonify(_application_payload(mentor))
