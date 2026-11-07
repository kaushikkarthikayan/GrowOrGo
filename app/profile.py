"""Part 1 (second half): turn extracted text into a structured, evidence-backed profile.

Two layers:
1. Rule-based parser (always runs, no AI needed) - finds sections, skills, years.
2. AI parser (runs when a key is set) - understands messy resumes much better.
Every skill keeps the exact line it came from ("evidence"). Anything the AI says that
cannot be found in the candidate's own text is marked verified=False, so later steps
never use made-up skills."""
import re
from datetime import date

from rapidfuzz import fuzz

from . import llm
from .skills import normalize_skill, skills_in_line

SECTION_HEADINGS = {
    "education": r"education|academic|qualifications?",
    "experience": r"(work |professional |internship |relevant )?experience|employment|work history|internships?|career history",
    "projects": r"(academic |personal |key )?projects?",
    "skills": r"(technical |key |core |soft )?skills|tools|technologies|tech stack|competencies",
    "certifications": r"certifications?|certificates?|courses|licen[cs]es",
    "summary": r"(professional |career )?summary|profile|about( me)?|(career )?objective",
    "achievements": r"achievements?|awards?|honou?rs|accomplishments|extra[- ]?curricular( activities)?",
}
BULLET_RE = re.compile(r"^\s*[•\-\*·▪●◦–]\s+")
STRENGTH = {"used_at_work": 3, "used_in_project": 2, "mentioned": 1}
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def _section_of(line: str):
    clean = re.sub(r"[^a-zA-Z /]", "", line).strip().lower()
    if not clean or len(clean) > 40:
        return None
    for name, pat in SECTION_HEADINGS.items():
        if re.fullmatch(pat, clean):
            return name
    return None


def _combined_text(session: dict) -> str:
    return "\n\n".join(f"=== SOURCE: {s['source']} ===\n{s['text']}" for s in session["sources"])


def _experience_level(grad_year, today=None) -> str:
    today = today or date.today()
    if not grad_year:
        return "unknown"
    years = today.year - int(grad_year)
    if years < 0:
        return "student"
    if years <= 1:
        return "fresher"
    if years <= 3:
        return "junior"
    return "experienced"


# ---------------- rule-based layer ----------------

def rule_based_profile(session: dict) -> dict:
    skills: dict[str, dict] = {}
    sections: dict[str, list[str]] = {k: [] for k in SECTION_HEADINGS}
    # Projects and jobs: a heading line ("Smart Attendance System") followed by bullet points.
    groups: dict[str, list] = {"projects": [], "experience": []}
    name = None

    for src in session["sources"]:
        current = None
        for raw in src["text"].splitlines():
            is_bullet = bool(BULLET_RE.match(raw))
            line = raw.strip(" •-*·▪●◦\t")
            if not line:
                continue
            heading = _section_of(line)
            if heading:
                current = heading
                continue
            if current in groups:
                if not is_bullet or not groups[current]:
                    groups[current].append({"title": line if not is_bullet else None, "points": []})
                    if is_bullet:
                        groups[current][-1]["points"].append(line)
                else:
                    groups[current][-1]["points"].append(line)
            if name is None and src["type"] == "file" and current is None and len(line.split()) <= 4 \
                    and not any(ch.isdigit() for ch in line) and "@" not in line:
                name = line
            if current:
                sections[current].append(line)

            hint = {"experience": "used_at_work", "projects": "used_in_project"}.get(current, "mentioned")
            if src["type"] == "link" and line.lower().startswith("project:"):
                hint = "used_in_project"
            # Contact lines (email / links) are not proof of a skill.
            if src["type"] == "file" and ("@" in line or re.search(r"https?://|\w\.(com|io|dev|me)\b", line)):
                continue
            for s in skills_in_line(line, in_skills_section=(current == "skills")):
                old = skills.get(s)
                if not old or STRENGTH[hint] > STRENGTH[old["level_hint"]]:
                    skills[s] = {"name": s, "evidence": line[:300], "source": src["source"],
                                 "level_hint": hint, "verified": True}

    edu_years = [int(y) for l in sections["education"] for y in YEAR_RE.findall(l)]
    grad_year = max((y for y in edu_years if y <= date.today().year + 5), default=None)

    return {
        "name": name,
        "graduation_year": grad_year,
        "skills": sorted(skills.values(), key=lambda s: (-STRENGTH[s["level_hint"]], s["name"])),
        "education": [{"summary": l, "evidence": l} for l in sections["education"]][:10],
        "experience": _grouped(groups["experience"])[:20],
        "projects": _grouped(groups["projects"])[:20],
        "achievements": [{"summary": l, "evidence": l} for l in sections["achievements"]][:10],
        "contact": _contact(session),
        "certifications": [{"name": l, "evidence": l} for l in sections["certifications"]][:20],
        "conflicts": [],
    }


def _grouped(groups: list) -> list:
    """One entry per bullet point, labelled with its project / job heading."""
    out = []
    for g in groups:
        if g["points"]:
            for pt in g["points"]:
                out.append({"name": g["title"], "summary": pt, "evidence": pt})
        elif g["title"]:
            out.append({"name": g["title"], "summary": g["title"], "evidence": g["title"]})
    return out


def _contact(session: dict) -> dict:
    """Email / phone / links from the candidate's own documents (for the final application)."""
    text = "\n".join(s["text"] for s in session["sources"] if s["type"] == "file")
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    phone = re.search(r"\+?\d[\d ()-]{8,}\d", text)
    links = re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/|github\.com/)[\w./-]+", text)
    return {"email": email.group(0) if email else None, "phone": phone.group(0).strip() if phone else None,
            "links": list(dict.fromkeys(links))[:3]}


# ---------------- AI layer ----------------

SYSTEM_PROMPT = """You are a careful resume parser for GoOrGrow, a career tool for students and early-career job seekers.
Extract ONLY what is written in the candidate's documents. Never guess, never add skills, employers, dates or numbers that are not in the text.
For every item, copy the exact supporting sentence from the text into "evidence" (word for word, max 300 characters).
level_hint for a skill: "used_at_work" if used in a job/internship, "used_in_project" if used in a project, otherwise "mentioned".
If the resume and LinkedIn disagree (e.g. different dates or job titles), describe each disagreement in "conflicts".
Return JSON with exactly this shape:
{
 "name": string or null,
 "headline": string or null,
 "graduation_year": integer or null,
 "years_experience": number or null,
 "skills": [{"name": string, "evidence": string, "source": string, "level_hint": "used_at_work"|"used_in_project"|"mentioned"}],
 "education": [{"degree": string, "institution": string, "year": string or null, "evidence": string}],
 "experience": [{"title": string, "company": string, "start": string or null, "end": string or null, "summary": string, "evidence": string}],
 "projects": [{"name": string, "description": string, "skills": [string], "evidence": string}],
 "certifications": [{"name": string, "evidence": string}],
 "conflicts": [string]
}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def evidence_found(evidence: str, source_text_norm: str) -> bool:
    """True if the quoted evidence really appears in the candidate's documents."""
    ev = _norm(evidence)
    if len(ev) < 3:
        return False
    if ev in source_text_norm:
        return True
    return fuzz.partial_ratio(ev, source_text_norm) >= 88


def ai_profile(session: dict) -> dict:
    text = _combined_text(session)[:60000]
    data = llm.ask_json(SYSTEM_PROMPT, "Candidate documents:\n\n" + text)
    norm_text = _norm(text)

    for key in ("skills", "education", "experience", "projects", "certifications", "conflicts"):
        if not isinstance(data.get(key), list):
            data[key] = []

    clean_skills = []
    for s in data["skills"]:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        s["name"] = normalize_skill(s["name"])
        s["level_hint"] = s.get("level_hint") if s.get("level_hint") in STRENGTH else "mentioned"
        s["verified"] = evidence_found(s.get("evidence", ""), norm_text)
        clean_skills.append(s)
    data["skills"] = clean_skills

    for key in ("education", "experience", "projects", "certifications"):
        data[key] = [
            {**item, "verified": evidence_found(item.get("evidence", ""), norm_text)}
            for item in data[key] if isinstance(item, dict)
        ]
    for p in data["projects"]:
        p["skills"] = [normalize_skill(x) for x in p.get("skills", []) if isinstance(x, str)]
    return data


# ---------------- combine ----------------

def build_profile(session: dict, graduation_year: int | None = None) -> dict:
    if not session.get("sources"):
        raise ValueError("No uploaded text in this session yet. Upload a resume first.")

    base = rule_based_profile(session)
    warnings: list[str] = []
    built_with = "rules"

    try:
        prof = ai_profile(session)
        built_with = llm.provider()
        # Add any skills the rules found that the AI missed (they always have real evidence).
        have = {s["name"].lower() for s in prof["skills"]}
        prof["skills"].extend(s for s in base["skills"] if s["name"].lower() not in have)
        if not prof.get("graduation_year"):
            prof["graduation_year"] = base["graduation_year"]
        if not prof.get("name"):
            prof["name"] = base["name"]
        prof["contact"] = base["contact"]
    except llm.LLMError as e:
        prof = base
        warnings.append(f"AI parsing not used ({e}). Showing rule-based results - add an API key in .env for better accuracy.")

    # Merge duplicate skills, keep the strongest evidence.
    merged: dict[str, dict] = {}
    for s in prof["skills"]:
        k = s["name"].lower()
        old = merged.get(k)
        if not old or (s["verified"], STRENGTH[s["level_hint"]]) > (old["verified"], STRENGTH[old["level_hint"]]):
            merged[k] = s
    prof["skills"] = sorted(merged.values(), key=lambda s: (not s["verified"], -STRENGTH[s["level_hint"]], s["name"]))

    unverified = [s["name"] for s in prof["skills"] if not s["verified"]]
    if unverified:
        warnings.append("These skills could not be matched to a line in your documents, so they won't be used "
                        "unless you confirm them: " + ", ".join(unverified))

    found_year = prof.get("graduation_year")
    if graduation_year:
        if found_year and abs(int(graduation_year) - int(found_year)) > 1:
            warnings.append(f"You entered graduation year {graduation_year}, but your resume says {found_year}. "
                            f"We're using {graduation_year} - change it if that's a typo.")
        prof["graduation_year"] = int(graduation_year)
    prof["experience_level"] = _experience_level(prof.get("graduation_year"))
    if prof["experience_level"] == "unknown":
        warnings.append("Graduation year not found - please add it, it changes which jobs fit you.")

    prof["built_with"] = built_with
    prof["warnings"] = warnings
    prof["confirmed"] = False
    return prof
