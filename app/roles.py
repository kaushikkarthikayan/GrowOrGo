"""Common early-career roles and the skills they usually ask for.
Used to (1) suggest job fields on the preferences screen and (2) as a fallback
when a job listing doesn't spell out its skills. Edit freely."""

ROLES: dict[str, dict[str, list[str]]] = {
    "Data Analyst": {
        "core": ["SQL", "Excel", "Data Analysis", "Data Visualization", "Power BI", "Python"],
        "nice": ["Tableau", "Statistics", "Data Cleaning", "Pandas", "R", "Communication"],
    },
    "Business Intelligence Analyst": {
        "core": ["SQL", "Power BI", "Data Visualization", "Data Warehousing", "Excel"],
        "nice": ["DAX", "Tableau", "ETL", "Stakeholder Management", "Looker"],
    },
    "Data Scientist": {
        "core": ["Python", "Machine Learning", "Statistics", "SQL", "Pandas", "Scikit-learn"],
        "nice": ["Deep Learning", "NLP", "Data Visualization", "Time Series", "R"],
    },
    "Data Engineer": {
        "core": ["Python", "SQL", "ETL", "Data Warehousing", "Apache Spark"],
        "nice": ["Airflow", "dbt", "AWS", "Azure", "Snowflake", "Docker", "Git"],
    },
    "Machine Learning Engineer": {
        "core": ["Python", "Machine Learning", "PyTorch", "MLOps", "Docker"],
        "nice": ["TensorFlow", "Deep Learning", "AWS", "Kubernetes", "LLMs", "Git"],
    },
    "AI / LLM Engineer": {
        "core": ["Python", "LLMs", "NLP", "REST APIs"],
        "nice": ["FastAPI", "PyTorch", "Docker", "Machine Learning", "Git"],
    },
    "Backend Developer": {
        "core": ["Python", "REST APIs", "SQL", "Git"],
        "nice": ["FastAPI", "Django", "Node.js", "Java", "Docker", "PostgreSQL", "AWS"],
    },
    "Frontend Developer": {
        "core": ["JavaScript", "HTML", "CSS", "React"],
        "nice": ["TypeScript", "Next.js", "Git", "UI/UX Design", "Figma"],
    },
    "Full Stack Developer": {
        "core": ["JavaScript", "React", "Node.js", "SQL", "REST APIs", "Git"],
        "nice": ["TypeScript", "Next.js", "Python", "Docker", "AWS", "MongoDB"],
    },
    "QA / Test Automation Engineer": {
        "core": ["Test Automation", "Testing", "Java", "Python"],
        "nice": ["CI/CD", "SQL", "Agile", "Jira", "Git", "REST APIs"],
    },
    "DevOps / Cloud Engineer": {
        "core": ["Linux", "Docker", "CI/CD", "AWS"],
        "nice": ["Kubernetes", "Azure", "Google Cloud", "Bash", "Python", "Git"],
    },
    "Business Analyst": {
        "core": ["Business Analysis", "Excel", "Stakeholder Management", "Communication"],
        "nice": ["SQL", "Power BI", "Agile", "Jira", "Data Analysis"],
    },
    "CRM Analyst": {
        "core": ["CRM", "Excel", "Data Analysis", "SQL"],
        "nice": ["Salesforce", "HubSpot", "Power BI", "Communication", "Customer Service"],
    },
    "Project Coordinator": {
        "core": ["Project Management", "Communication", "Stakeholder Management", "Agile"],
        "nice": ["Jira", "Excel", "Leadership", "Problem Solving"],
    },
    "UI/UX Designer": {
        "core": ["UI/UX Design", "Figma"],
        "nice": ["HTML", "CSS", "Communication", "Problem Solving"],
    },
}

STRENGTH_WEIGHT = {"used_at_work": 1.0, "used_in_project": 0.8, "mentioned": 0.5}


def role_fit(role: str, skill_strength: dict[str, str]) -> dict:
    """How well a candidate's skills cover a role. skill_strength = {skill: level_hint}."""
    spec = ROLES[role]
    core, nice = spec["core"], spec["nice"]
    have = {k.lower(): v for k, v in skill_strength.items()}

    def score(skills, weight):
        return sum(weight * STRENGTH_WEIGHT.get(have.get(s.lower(), ""), 0) for s in skills)

    total = 2 * len(core) + len(nice)
    got = score(core, 2) + score(nice, 1)
    return {
        "role": role,
        "match_percent": round(100 * got / total) if total else 0,
        "matched_skills": [s for s in core + nice if s.lower() in have],
        "missing_core_skills": [s for s in core if s.lower() not in have],
    }


def suggest_roles(skill_strength: dict[str, str], top: int = 6) -> list[dict]:
    fits = [role_fit(r, skill_strength) for r in ROLES]
    fits.sort(key=lambda f: -f["match_percent"])
    return [f for f in fits if f["match_percent"] > 0][:top]
