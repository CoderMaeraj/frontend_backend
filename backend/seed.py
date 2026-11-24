from flask import current_app

from models import AccountStatus, CareerGoal, Role, Skill, SkillCareerGoal, User, db

CAREER_GOALS = {
    "Internships": "Land an internship to gain industry experience",
    "Jobs": "Get a full-time job after graduation",
    "Higher studies": "Pursue a master's, PhD or other higher studies",
    "Freelancing": "Work independently with clients",
    "Entrepreneurship": "Start and grow your own venture",
}

SKILLS = {
    "Python": "General-purpose programming language",
    "Data Analysis": "Cleaning, exploring and interpreting data",
    "Machine Learning": "Building models that learn from data",
    "Communication": "Clear written and spoken communication",
    "Leadership": "Leading people and projects",
    "Design": "UI/UX and visual design",
    "Product Management": "Defining and shipping products",
    "Java": "Object-oriented programming language",
    "SQL": "Querying relational databases",
    "Public Speaking": "Presenting confidently to an audience",
}

# Which skills matter for which career goal
SKILL_GOALS = {
    "Internships": ["Python", "Java", "SQL", "Data Analysis", "Communication"],
    "Jobs": ["Python", "Java", "SQL", "Data Analysis", "Machine Learning", "Communication", "Product Management"],
    "Higher studies": ["Python", "Machine Learning", "Data Analysis", "Public Speaking"],
    "Freelancing": ["Design", "Python", "Communication"],
    "Entrepreneurship": ["Leadership", "Product Management", "Public Speaking", "Communication"],
}


def seed():
    goals = {}
    for name, desc in CAREER_GOALS.items():
        goals[name] = CareerGoal.query.filter_by(goal_name=name).first() or CareerGoal(goal_name=name, description=desc)
        db.session.add(goals[name])

    skills = {}
    for name, desc in SKILLS.items():
        skills[name] = Skill.query.filter_by(skill_name=name).first() or Skill(skill_name=name, description=desc)
        db.session.add(skills[name])
    db.session.flush()

    for goal, names in SKILL_GOALS.items():
        for s in names:
            g_id, s_id = goals[goal].id, skills[s].id
            if not SkillCareerGoal.query.filter_by(goal_id=g_id, skill_id=s_id).first():
                db.session.add(SkillCareerGoal(goal_id=g_id, skill_id=s_id))

    email = current_app.config["ADMIN_EMAIL"].lower()
    if not User.query.filter_by(email=email).first():
        admin = User(name="Admin", email=email, role=Role.ADMIN, account_status=AccountStatus.ACTIVE)
        admin.set_password(current_app.config["ADMIN_PASSWORD"])
        db.session.add(admin)

    db.session.commit()
