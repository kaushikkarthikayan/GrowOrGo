"""Part 4 - GO: tailored, truthful application material for the jobs the candidate picks.

For each chosen job it prepares:
  - a short professional summary
  - resume bullet points, re-ordered so the most relevant real experience comes first
  - a cover note
  - portfolio highlights (which projects to show first, and how)
  - keywords from the job ad the candidate can honestly use, and ones they must NOT claim

TRUTHFULNESS GUARD: every sentence must point to evidence from the candidate's own documents.
A sentence that mentions a skill the candidate doesn't have, or a number/date that isn't in their
documents, is blocked and shown in "blocked_items" with the reason. Nothing is ever submitted -
the candidate reviews, edits and applies themselves.

Portfolio guidance follows common best practice: lead with the 2-3 most relevant projects, show
problem -> what you did -> result, link to the code or a live demo, use the job's own words only
where true, keep it short and scannable, and never inflate results."""
import re

from . import llm
from .skills import skills_in_line

NUM_RE = re.compile(r"\d[\d,.]*%?")


# ---------------- evidence ----------------

def evidence_items(profile: dict) -> list[dict]:
    items, seen = [], set()

    def add(kind, text, label=None):
        text = (text or "").strip()
        if len(text) < 3 or text.lower() in seen:
            return
        seen.add(text.lower())
        items.append({"id": f"e{len(items) + 1}", "kind": kind, "text": text, "label": label})

    for e in profile.get("experience", []):
        if e.get("verified", True):
            label = e.get("name") or " - ".join(x for x in [e.get("title"), e.get("company")] if x) or None
            add("experience", e.get("evidence") or e.get("summary"), label)
    for p in profile.get("projects", []):
        if p.get("verified", True):
            add("project", p.get("evidence") or p.get("description") or p.get("summary"), p.get("name"))
    for a in profile.get("achievements", []):
        add("achievement", a.get("evidence") or a.get("summary"))
    for c in profile.get("certifications", []):
        if c.get("verified", True):
            add("certification", c.get("evidence") or c.get("name"))
    for ed in profile.get("education", []):
        if ed.get("verified", True):
            add("education", ed.get("evidence") or ed.get("summary"))
    for s in profile.get("skills", []):
        if s.get("verified"):
            add("skill", s.get("evidence"), s["name"])
    return items


def _relevance(item: dict, wanted: set[str]) -> float:
    found = {s.lower() for s in skills_in_line(item["text"], in_skills_section=True)}
    bonus = {"experience": 0.5, "project": 0.4, "certification": 0.2}.get(item["kind"], 0)
    return len(found & wanted) + bonus


# ---------------- guard ----------------

def check_claim(text: str, ids: list[str], ev_map: dict, my_skills: set[str], ignore: tuple = ()) -> dict:
    """Return {"status": "ok"|"blocked", "reasons": [...]} for one sentence or paragraph.
    `ignore` = phrases that are allowed anyway (the job title and company name)."""
    reasons = []
    for phrase in ignore:
        if phrase:
            text = re.sub(re.escape(phrase), " ", text, flags=re.I)
    ids = [i for i in (ids or []) if i in ev_map]
    cited = " ".join(ev_map[i] for i in ids).lower()
    cited_digits = cited.replace(",", "")

    mentioned = {s.lower() for s in skills_in_line(text, in_skills_section=True)}
    cited_skills = {s.lower() for s in skills_in_line(cited, in_skills_section=True)}
    for s in sorted(mentioned - my_skills - cited_skills):
        reasons.append(f"Mentions '{s}', which isn't in your confirmed profile")

    for n in NUM_RE.findall(text):
        n_clean = n.replace(",", "").rstrip(".")
        if n_clean and n_clean not in cited_digits:
            reasons.append(f"The number '{n}' doesn't appear in the evidence it cites")

    if not ids and (mentioned or NUM_RE.search(text)):
        reasons.append("Makes a claim but cites no evidence from your documents")

    return {"status": "blocked" if reasons else "ok", "reasons": reasons, "evidence_ids": ids}


# ---------------- rule-based drafting (works without AI) ----------------

DEGREE_RE = re.compile(r"\b(B\.?\s?Tech|M\.?\s?Tech|B\.?\s?E\.?|M\.?\s?E\.?|B\.?\s?Sc|M\.?\s?Sc|BCA|MCA|MBA|B\.?\s?Com|M\.?\s?Com|"
                       r"BA|MA|Bachelor(?:'s)?|Master(?:'s)?|PhD|Diploma)\b[^|,\n]*", re.I)
ROLE_SPLIT_RE = re.compile(r"\s+(?:—|–|-|@|at)\s+|,\s+", re.I)


def _summary(profile, job, ev, top, skill_ev, strong, ranked, wanted):
    """A 3-4 sentence profile for the top of the resume. Every sentence cites lines from the
    candidate's own documents; the target role and city come from the job they chose."""
    parts, ids = [], []
    level = profile.get("experience_level")
    grad = profile.get("graduation_year")
    edu = [e for e in ev if e["kind"] == "education"]

    # 1. Who you are: degree + graduation year (only if both are in the documents).
    degree_ev = next((e for e in edu if DEGREE_RE.search(e["text"])), None)
    year_ev = next((e for e in edu if grad and str(grad) in e["text"]), None)
    who = {"student": "Final-year", "fresher": "Recent", "junior": "Early-career", "experienced": "Experienced"}.get(level, "")
    if degree_ev:
        degree = DEGREE_RE.search(degree_ev["text"]).group(0).strip(" .;:")
        if level == "student":
            s = f"{who} {degree} student" + (f", graduating in {grad}" if year_ev else "")
        elif level == "fresher":
            s = f"Recent {degree} graduate" + (f" ({grad})" if year_ev else "")
        else:
            # "an MSc", "an MBA", but "a Bachelor's", "a B.Tech"
            acronym = len(degree) > 1 and (degree[1].isupper() or degree[1] == ".")
            article = "an" if (acronym and degree[0] in "AEFHILMNORSX") or (not acronym and degree[0] in "AEIOU") else "a"
            s = f"{who} professional with {article} {degree}".strip()
        parts.append(s + ".")
        ids += [degree_ev["id"]] + ([year_ev["id"]] if year_ev else [])

    # 2. Skills this job wants that you have really used, topped up with your other proven skills.
    proven = list(top)
    for name in sorted(strong):
        if len(proven) >= 5:
            break
        if name not in proven and name.lower() in skill_ev:
            proven.append(name)
    if proven:
        lead = "Hands-on experience with" if parts else f"{(who + ' candidate') if who else 'Candidate'} with hands-on experience in"
        parts.append(f"{lead} {', '.join(proven[:-1]) + ' and ' + proven[-1] if len(proven) > 1 else proven[0]}.")
        ids += [skill_ev[p.lower()]["id"] for p in proven]

    # 3. Work experience / internship, taken from the job heading in the resume.
    exp = next((e for e in ranked if e["kind"] == "experience" and e.get("label")), None)
    if exp:
        head = exp["label"].split("|")[0].strip()
        bits = [b.strip() for b in ROLE_SPLIT_RE.split(head) if b.strip()]
        role = bits[0] if bits else head
        org = bits[1] if len(bits) > 1 else None
        parts.append(f"Experience as {role}" + (f" at {org}" if org else "") + f", where I {exp['text'][0].lower() + exp['text'][1:].rstrip('.')}.")
        ids.append(exp["id"])

    # 4. Projects most relevant to this job.
    projects, seen = [], set()
    for e in ranked:
        if e["kind"] == "project" and e.get("label") and e["label"].lower() not in seen:
            seen.add(e["label"].lower())
            projects.append(e)
        if len(projects) == 2:
            break
    if projects:
        names = " and ".join(p["label"] for p in projects)
        parts.append(f"Built projects including {names}.")
        ids += [p["id"] for p in projects]

    # 5. What you're looking for (from the job you chose and where it is).
    if parts:
        where = (job.get("location") or "").split(",")[0].strip()
        parts.append(f"Looking for a {job['title']} role" + (f" in {where}" if where else "") + ".")

    return " ".join(parts), list(dict.fromkeys(ids))



def _why(text: str, wanted: set[str]) -> str:
    used = sorted(s for s in skills_in_line(text, True) if s.lower() in wanted)[:4]
    return f"Uses {', '.join(used)}, which this job asks for" if used else "Shows relevant hands-on work"


def _rule_draft(profile: dict, job: dict, ev: list[dict], matched: list[str]) -> dict:
    wanted = {s.lower() for s in job.get("required_skills", []) + job.get("nice_skills", [])}
    ranked = sorted([e for e in ev if e["kind"] in ("experience", "project")],
                    key=lambda e: -_relevance(e, wanted))
    level = {"student": "Final-year student", "fresher": "Recent graduate", "junior": "Early-career professional",
             "experienced": "Professional"}.get(profile.get("experience_level"), "Candidate")

    # Map each verified skill to the evidence line that proves it (strongest proof first).
    by_text = {e["text"].lower(): e for e in ev}
    strength = {"used_at_work": 0, "used_in_project": 1, "mentioned": 2}
    skill_ev = {}
    for s in sorted([s for s in profile.get("skills", []) if s.get("verified")],
                    key=lambda s: strength.get(s.get("level_hint"), 3)):
        e = by_text.get((s.get("evidence") or "").strip().lower())
        if e:
            skill_ev.setdefault(s["name"].lower(), e)
    # Only skills with real proof (work or project) are described as "hands-on".
    strong = {s["name"] for s in profile.get("skills", []) if s.get("verified")
              and s.get("level_hint") in ("used_at_work", "used_in_project")}
    top = sorted([s for s in matched if s.lower() in skill_ev and s in strong],
                 key=lambda s: strength.get(next((x.get("level_hint") for x in profile["skills"] if x["name"] == s), ""), 3))[:4]
    summary_ids = list(dict.fromkeys(skill_ev[s.lower()]["id"] for s in top))
    summary = f"{level} with hands-on experience in {', '.join(top)}." if top else f"{level} keen to grow in this role."

    def group_of(e):
        lab = (e.get("label") or "").split("|")[0].strip()
        return lab if lab and lab.lower() != e["text"].lower() else None

    def cap(t):
        return t[0].upper() + t[1:]

    # Keep resume order: take the 6 most relevant points, then list them grouped under their heading.
    top6 = ranked[:6]
    order = list(dict.fromkeys(group_of(e) for e in top6))
    bullets = [{"text": cap(e["text"]), "group": group_of(e), "evidence_ids": [e["id"]]}
               for g in order for e in top6 if group_of(e) == g]

    def with_label(e):
        g = group_of(e)
        return f"{cap(e['text']).rstrip('.')} ({g})" if g else cap(e["text"])

    company = (job.get("company") or "your company").rstrip(".")
    best = ranked[:2]
    cover = [
        {"text": f"I'm applying for the {job['title']} role at {company}.", "evidence_ids": []},
    ]
    if top:
        cover.append({"text": f"The role asks for {', '.join(top)}, which I have used directly.",
                      "evidence_ids": summary_ids})
    for e, lead in zip(best, ["Most relevant to this role", "Another example"]):
        cover.append({"text": f"{lead}: {with_label(e).rstrip('.')}.", "evidence_ids": [e["id"]]})
    cover.append({"text": f"I'd welcome the chance to discuss how I could contribute to {company}.",
                  "evidence_ids": []})

    def short(t, n=70):
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."

    portfolio = [{"title": e.get("label") or short(e["text"]),
                  "why_relevant": _why(e["text"], wanted),
                  "evidence_ids": [e["id"]]}
                 for e in ranked if e["kind"] == "project"][:3]
    full_summary, full_ids = _summary(profile, job, ev, top, skill_ev, strong, ranked, wanted)
    return {"summary": {"text": full_summary or summary, "evidence_ids": full_ids or summary_ids}, "bullets": bullets,
            "cover_note": cover, "portfolio_highlights": portfolio}


# ---------------- AI drafting ----------------

AI_SYSTEM = """You write job application material for early-career candidates. You must be strictly truthful.
Use ONLY facts from the numbered evidence list. Every item you write must list the evidence ids it is based on.
Never add skills, tools, employers, job titles, numbers, percentages or dates that are not in the cited evidence.
You may reword and reorder, and use the job ad's wording only where the evidence supports it.
Portfolio best practice: lead with the 2-3 most relevant projects; for each say the problem, what the candidate did and the result (only if a result is in the evidence).
Cover note: 120-180 words, warm and specific, no cliches, split into 3-5 short paragraphs.
Return JSON:
{"summary": {"text": string, "evidence_ids": [string]},
 "bullets": [{"text": string, "evidence_ids": [string]}],
 "cover_note": [{"text": string, "evidence_ids": [string]}],
 "portfolio_highlights": [{"title": string, "why_relevant": string, "evidence_ids": [string]}]}"""


def _ai_draft(profile: dict, job: dict, ev: list[dict]) -> dict:
    ev_text = "\n".join(f"{e['id']} [{e['kind']}]: {e['text']}" for e in ev)
    user = (f"JOB: {job['title']} at {job.get('company')}\nRequired skills: {', '.join(job.get('required_skills', []))}\n"
            f"Nice to have: {', '.join(job.get('nice_skills', []))}\nJob ad: {job.get('description', '')[:2000]}\n\n"
            f"CANDIDATE EVIDENCE:\n{ev_text}\n\nCandidate level: {profile.get('experience_level')}")
    data = llm.ask_json(AI_SYSTEM, user)
    for key in ("bullets", "cover_note", "portfolio_highlights"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if not isinstance(data.get("summary"), dict):
        data["summary"] = {"text": "", "evidence_ids": []}
    return data


# ---------------- main entry ----------------

def tailor_application(profile: dict, job: dict, readiness_job: dict | None = None) -> dict:
    ev = evidence_items(profile)
    ev_map = {e["id"]: (f"{e['label']}: {e['text']}" if e.get("label") else e["text"]) for e in ev}
    my_skills = {s["name"].lower() for s in profile.get("skills", []) if s.get("verified")}
    matched = job.get("matched_skills", [])
    missing = job.get("missing_skills", [])

    draft, made_with, notes = None, "rules", []
    if llm.provider() != "demo":
        try:
            draft, made_with = _ai_draft(profile, job, ev), llm.provider()
        except llm.LLMError as e:
            notes.append(f"AI drafting not used ({e}); showing a rule-based draft.")
    if draft is None:
        draft = _rule_draft(profile, job, ev, matched)

    blocked = []
    allowed = (job.get("title"), job.get("company"))

    def guard(item: dict, where: str):
        if not isinstance(item, dict) or not item.get("text"):
            return None
        res = check_claim(item["text"], item.get("evidence_ids", []), ev_map, my_skills, allowed)
        if where in ("summary", "bullet") and not res["evidence_ids"]:
            res["status"] = "blocked"
            res["reasons"].append("Resume lines must be based on something in your documents")
        if res["status"] == "blocked":
            blocked.append({"where": where, "text": item["text"], "reasons": res["reasons"]})
            return None
        return {"text": item["text"], "group": item.get("group"), "evidence_ids": res["evidence_ids"]}

    summary = guard(draft["summary"], "summary")
    bullets = [b for b in (guard(b, "bullet") for b in draft["bullets"]) if b]
    cover = [c for c in (guard(c, "cover note") for c in draft["cover_note"]) if c]
    portfolio, seen_titles = [], set()
    for p in draft["portfolio_highlights"]:
        if isinstance(p, dict) and p.get("title") and p["title"].lower() not in seen_titles:
            seen_titles.add(p["title"].lower())
            res = check_claim(f"{p['title']} {p.get('why_relevant', '')}", p.get("evidence_ids", []), ev_map, my_skills, allowed)
            if res["status"] == "ok":
                portfolio.append({**p, "evidence_ids": res["evidence_ids"],
                                  "tip": "Add a GitHub or live-demo link and one screenshot; describe problem -> what you did -> result."})
            else:
                blocked.append({"where": "portfolio", "text": p["title"], "reasons": res["reasons"]})

    used_ids = {i for x in [summary or {}] + bullets + cover + portfolio for i in x.get("evidence_ids", [])}
    return {
        "job_id": job["job_id"],
        "candidate": {"name": profile.get("name"), **(profile.get("contact") or {})},
        "title": job["title"],
        "company": job.get("company"),
        "apply_link": job.get("url"),
        "readiness_percent": (readiness_job or {}).get("readiness_percent"),
        "made_with": made_with,
        "summary": summary["text"] if summary else None,
        "resume_bullets": bullets,
        "cover_note": "\n\n".join(c["text"] for c in cover),
        "cover_note_parts": cover,
        "portfolio_highlights": portfolio,
        "keywords_to_use": matched,
        "do_not_claim": missing,
        "blocked_items": blocked,
        "evidence_trail": [e for e in ev if e["id"] in used_ids],
        "review_checklist": [
            "Every line is true and you could talk about it in an interview",
            "Your contact details and links are correct",
            "The company name and job title are right",
            "You've added links/screenshots for the portfolio projects",
            "You're happy with the tone of the cover note",
        ],
        "notes": notes + ["GoOrGrow never submits applications for you. Review, edit, then apply yourself using the link."],
        "approved": False,
    }
