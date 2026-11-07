"""Part 4 - GROW: turn red and white flags into an ordered learning plan.

Order: red skills needed by the most jobs first, then "prove it" skills (white, weak evidence),
then nice-to-have gaps. Each item gets a concrete project idea and a rough effort guide.
Course links are left empty for now - add them later in COURSE_LINKS."""
from . import llm

# Rough effort guide (weeks of part-time study) by kind of skill. Edit to taste.
EFFORT_WEEKS = {
    "tool": (1, 2),        # Excel, Power BI, Tableau, Git, Jira, Figma
    "language": (4, 8),    # Python, Java, JavaScript, SQL basics->solid
    "platform": (2, 4),    # AWS, Azure, Docker, Kubernetes, CI/CD
    "data_platform": (3, 5),  # Spark, Airflow, Snowflake, databases
    "ml_framework": (4, 8),   # PyTorch, TensorFlow, MLOps
    "concept": (3, 6),     # Machine Learning, Statistics, ETL, Data Warehousing
    "soft": (2, 4),        # Communication, Stakeholder Management
}
KIND = {
    **dict.fromkeys(["Excel", "Power BI", "Tableau", "Looker", "Git", "Jira", "Figma", "DAX", "HubSpot",
                     "Salesforce", "CRM", "dbt", "Pandas", "NumPy", "Scikit-learn"], "tool"),
    **dict.fromkeys(["Python", "R", "SQL", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go",
                     "Scala", "Bash", "VBA", "HTML", "CSS", "React", "Next.js", "Node.js", "Django",
                     "Flask", "FastAPI"], "language"),
    **dict.fromkeys(["AWS", "Azure", "Google Cloud", "Docker", "Kubernetes", "CI/CD", "Linux", "MLOps"], "platform"),
    **dict.fromkeys(["Apache Spark", "Airflow", "Snowflake", "BigQuery", "Hadoop", "PostgreSQL", "MySQL",
                     "MongoDB", "SQL Server", "Redis", "Oracle Database"], "data_platform"),
    **dict.fromkeys(["PyTorch", "TensorFlow", "Deep Learning", "Computer Vision", "LLMs", "NLP"], "ml_framework"),
    **dict.fromkeys(["Communication", "Stakeholder Management", "Leadership", "Teamwork",
                     "Problem Solving", "Customer Service", "Business Analysis", "Project Management",
                     "Agile"], "soft"),
}

PROJECT_IDEAS = {
    "tool": "Build a small dashboard or workbook with {skill} on a free public dataset, publish it (e.g. GitHub / public gallery) and add a screenshot to your portfolio.",
    "language": "Write a small end-to-end project in {skill} (e.g. clean a public dataset and answer 3 business questions), push it to GitHub with a clear README.",
    "platform": "Deploy one of your existing projects using {skill} (free tier), and document the setup steps in the README.",
    "data_platform": "Build a small data pipeline that uses {skill} (e.g. load a public dataset, transform it, store the result) and publish it on GitHub with a diagram.",
    "ml_framework": "Train and evaluate a small model with {skill} on a public dataset, then share the notebook and results on GitHub.",
    "concept": "Apply {skill} in a mini case study on a public dataset: problem, approach, result, what you'd do next. Publish it as a notebook or blog post.",
    "soft": "Get a real example of {skill}: lead a study group, volunteer project or hackathon role, then write it up as a STAR story (Situation, Task, Action, Result).",
}

# Add course links later, e.g. "SQL": [{"title": "...", "url": "...", "free": True}]
COURSE_LINKS: dict[str, list[dict]] = {}


def _item(entry: dict, priority: int, kind_of_gap: str) -> dict:
    skill = entry["skill"]
    kind = KIND.get(skill, "concept")
    lo, hi = EFFORT_WEEKS[kind]
    if kind_of_gap == "add_proof":
        action = (f"You already list {skill} - now prove it: " + PROJECT_IDEAS[kind].format(skill=skill)
                  + " Then add that project to your resume.")
        lo, hi = 1, 2
    else:
        action = PROJECT_IDEAS[kind].format(skill=skill)
    return {
        "priority": priority,
        "skill": skill,
        "flag": entry["flag"],
        "gap_type": kind_of_gap,
        "why": entry["reason"],
        "needed_by_jobs": entry.get("jobs", []),
        "action": action,
        "effort_estimate": f"about {lo}-{hi} weeks part-time (rough guide)",
        "courses": COURSE_LINKS.get(skill, []),
        "done": False,
    }


def build_plan(readiness: dict, max_items: int = 8) -> dict:
    flags = readiness["flags"]
    items: list[dict] = []
    for r in flags["red"]:
        items.append(_item(r, 0, "learn"))
    for w in flags["white"]:
        if w.get("code") == "weak_evidence" and (w.get("required_in") or w.get("nice_in")):
            items.append(_item(w, 0, "add_proof"))
    for w in flags["white"]:
        if w.get("code") == "nice_to_have_gap":
            items.append(_item(w, 0, "nice_to_have"))
    items = items[:max_items]
    for i, it in enumerate(items, 1):
        it["priority"] = i

    plan = {
        "headline": (f"Focus on {', '.join(i['skill'] for i in items[:3])} first."
                     if items else "No gaps found for these jobs - you could choose GO."),
        "items": items,
        "how_to_recheck": "When you finish an item, upload your updated resume or new project link, "
                          "then run the check again to see your flags and verdict change.",
        "ai_tips": None,
    }

    # Optional: let the AI add short, personal study tips (never changes the list itself).
    if items and llm.provider() != "demo":
        try:
            tips = llm.ask_json(
                "You are a friendly career coach for students. Given a ranked list of skills to learn, "
                "write 3 short practical study tips (max 25 words each). Do not invent course names or URLs. "
                'Return JSON: {"tips": [string, string, string]}',
                "Skills in priority order: " + ", ".join(i["skill"] for i in items),
            )
            plan["ai_tips"] = [t for t in tips.get("tips", []) if isinstance(t, str)][:3]
        except llm.LLMError:
            pass
    return plan
