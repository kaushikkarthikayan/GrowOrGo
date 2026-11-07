"""Part 3b: narrow many listings down to the best 5-10 for this candidate, with reasons.

Score (0-100) =
  50%  skill match   - required skills count double, stronger evidence (work > project > mentioned) counts more
  25%  meaning match - how similar the profile and the job description are (sentence embeddings,
                       or a simple word-overlap fallback if the model isn't available)
  15%  salary fit    - job pay versus the candidate's target
  10%  level fit     - entry / mid / senior versus the candidate's graduation year
"""
import math
import os
import re
from collections import Counter

from .jobs import collect_jobs, extract_requirements
from .roles import ROLES, STRENGTH_WEIGHT, suggest_roles

LEVEL_OK = {
    "student": {"entry"},
    "fresher": {"entry"},
    "junior": {"entry", "mid"},
    "experienced": {"entry", "mid", "senior"},
    "unknown": {"entry", "mid"},
}

# ---------------- meaning similarity ----------------

_model = None
_model_failed = False


def _embedder():
    global _model, _model_failed
    if _model is not None or _model_failed or os.getenv("USE_EMBEDDINGS", "true").lower() == "false":
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        # Small, fast model (~90 MB, downloaded once on first use).
        _model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    except Exception:
        _model_failed = True
    return _model


_WORD = re.compile(r"[a-z][a-z+#.]{1,}")
_STOP = set("the and for with you your our are will this that from have has into using use able work team role job".split())


def _bow(text: str) -> Counter:
    return Counter(w for w in _WORD.findall(text.lower()) if w not in _STOP)


def _cosine_bow(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    num = sum(a[w] * b[w] for w in common)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def similarities(profile_text: str, job_texts: list[str]) -> tuple[list[float], str]:
    model = _embedder()
    if model is not None:
        vecs = model.encode([profile_text] + job_texts, normalize_embeddings=True)
        p = vecs[0]
        # MiniLM cosine for related texts is usually 0.2-0.7; stretch to 0-1.
        return [max(0.0, min(1.0, (float(v @ p) - 0.15) / 0.55)) for v in vecs[1:]], "embeddings"
    pb = _bow(profile_text)
    return [min(1.0, _cosine_bow(pb, _bow(t)) * 2.5) for t in job_texts], "word-overlap"


# ---------------- scoring ----------------

def _salary_fit(job: dict, prefs: dict) -> tuple[float, str | None, bool]:
    """Returns (score 0-1, reason, passes_hard_filter)."""
    lo, hi = job.get("salary_min"), job.get("salary_max")
    target, minimum = prefs.get("target_salary"), prefs.get("min_salary")
    cur = prefs.get("currency", "")
    if not lo and not hi:
        return 0.5, "Salary not listed", True
    lo, hi = lo or hi, hi or lo
    pay = f"{cur} {lo:,.0f}" + (f"-{hi:,.0f}" if hi != lo else "")
    est = " (estimated)" if job.get("salary_is_estimate") else ""
    if minimum and hi < minimum:
        return 0.0, None, False
    if not target:
        return 0.7, f"Pays {pay}{est}", True
    if lo <= target <= hi or lo >= target:
        return 1.0, f"Pays {pay}{est} - meets your target", True
    gap = (target - hi) / target
    return max(0.0, 1 - gap * 3), f"Pays {pay}{est} - below your target of {cur} {target:,.0f}", True


def _location_ok(job: dict, req: dict, prefs: dict) -> bool:
    if prefs.get("country") and job.get("country") and job["country"] != prefs["country"]:
        return False
    mode = prefs.get("work_mode", "any")
    if mode == "remote" and req["work_mode"] not in ("remote", "not stated"):
        return False
    if mode == "onsite" and req["work_mode"] == "remote":
        return False
    locs = [l.lower() for l in prefs.get("locations", [])]
    if locs and req["work_mode"] != "remote":
        if not any(l in (job.get("location") or "").lower() for l in locs):
            return False
    return True


_ABBREV = {"bi": "business intelligence", "ml": "machine learning", "ai": "artificial intelligence ai",
           "qa": "quality assurance qa test", "ui": "ui design", "ux": "ux design", "dev": "developer",
           "devops": "devops", "fullstack": "full stack", "crm": "crm"}
_IGNORE = {"junior", "senior", "graduate", "lead", "i", "ii", "iii", "the", "of", "and", "a", "an", "to", "in"}


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        out += _ABBREV.get(w, w).split()
    return [w for w in out if w not in _IGNORE]


def _field_of(job: dict, fields: list) -> str | None:
    """Which field this job belongs to. The title must contain the main role word (e.g. 'analyst')
    plus at least one other word (e.g. 'data'), so 'Data Analyst' doesn't pull in 'Data Engineer'."""
    title = set(_words(job.get("title", "")))
    for field in fields:
        words = _words(field)
        if not words:
            continue
        if all(w in title for w in words):
            return field
        if len(words) >= 2 and words[-1] in title and any(w in title for w in words[:-1]):
            return field
    return None


def _field_ok(job: dict, prefs: dict) -> bool:
    return _field_of(job, prefs["job_fields"]) is not None


def _closest_role(job: dict) -> str:
    return _field_of(job, list(ROLES)) or "Related role"


def explore_fields(profile: dict, chosen: list, n: int = 2) -> list:
    """The candidate's best-fitting roles that they didn't already choose."""
    strength = {s["name"]: s["level_hint"] for s in profile.get("skills", []) if s.get("verified")}
    chosen_words = [set(_words(c)) for c in chosen]
    out = []
    for r in suggest_roles(strength, top=8):
        words = set(_words(r["role"]))
        if r["match_percent"] < 30 or any(words <= cw or cw <= words for cw in chosen_words):
            continue
        out.append(r["role"])
        if len(out) == n:
            break
    return out


def _diverse(results: list, field_order: list, top_n: int) -> list:
    """Take turns across fields (best first in each) so one field can't fill every spot."""
    by_field = {}
    for r in results:
        by_field.setdefault(r["field"], []).append(r)
    order = [f for f in field_order if f in by_field] + [f for f in by_field if f not in field_order]
    picked = []
    while len(picked) < top_n and any(by_field.values()):
        for f in order:
            if by_field.get(f) and len(picked) < top_n:
                picked.append(by_field[f].pop(0))
    return picked


def find_matches(profile: dict, prefs: dict, top_n: int = 10) -> dict:
    skills = {s["name"].lower(): s for s in profile.get("skills", []) if s.get("verified")}
    level = profile.get("experience_level", "unknown")
    extra = explore_fields(profile, prefs["job_fields"]) if prefs.get("explore_related", True) else []
    search_prefs = dict(prefs, explore_fields=extra)
    all_fields = list(prefs["job_fields"]) + extra
    jobs, source, warnings = collect_jobs(search_prefs)

    avoid = {c.lower() for c in prefs.get("avoid_companies", [])}
    liked = {c.lower() for c in prefs.get("preferred_companies", [])}

    # Dedupe
    unique, seen = [], set()
    for job in jobs:
        key = (job.get("title", "").lower().strip(), job.get("company", "").lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append((job, extract_requirements(job)))

    def run_filters(any_city: bool, related_roles: bool):
        out, dropped = [], Counter()
        p = dict(prefs, locations=[] if any_city else prefs.get("locations", []))
        for job, req in unique:
            company = job.get("company", "").lower()
            if any(a in company for a in avoid):
                dropped["company you want to avoid"] += 1
                continue
            field_match = _field_of(job, all_fields)
            if not field_match:
                # Related role: only if the candidate already covers at least half its required skills.
                rs = req["required_skills"]
                cover = sum(s.lower() in skills for s in rs) / len(rs) if rs else 0
                if not (related_roles and cover >= 0.5):
                    dropped["different job field"] += 1
                    continue
            if not _location_ok(job, req, p):
                dropped["location / work mode"] += 1
                continue
            if req["level"] not in LEVEL_OK.get(level, LEVEL_OK["unknown"]):
                dropped["too senior for your experience"] += 1
                continue
            sal_score, sal_reason, sal_ok = _salary_fit(job, prefs)
            if not sal_ok:
                dropped["below your minimum salary"] += 1
                continue
            note = None
            job = dict(job, _field=field_match or _closest_role(job))
            if not field_match:
                note = "Related role outside your chosen fields - your skills fit it well"
            elif any_city and prefs.get("locations") and _location_ok(job, req, prefs) is False:
                note = "In a different city from the ones you chose"
            out.append((job, req, sal_score, sal_reason, note))
        return out, dropped

    # Strict first; widen step by step if fewer than 5 jobs pass. Salary minimum,
    # work mode, level and avoided companies are never relaxed.
    candidates, filtered_out = run_filters(False, False)
    if len(candidates) < 5 and prefs.get("locations"):
        candidates, _ = run_filters(True, False)
    if len(candidates) < 5:
        candidates, _ = run_filters(bool(prefs.get("locations")), True)
    if len(candidates) > len(run_filters(False, False)[0]):
        warnings.append("Fewer than 5 jobs matched your exact filters, so some nearby options are included "
                        "and labelled.")

    if not candidates:
        return {"jobs": [], "source": source, "similarity_method": None, "total_listings": len(jobs),
                "passed_filters": 0,
                "filtered_out": dict(filtered_out),
                "warnings": warnings + ["No jobs passed your filters. Try more locations, 'any' work mode, "
                                        "or a lower minimum salary."]}

    profile_text = " ".join(
        [profile.get("headline") or ""]
        + [f"{s['name']} {s.get('evidence', '')}" for s in skills.values()]
        + [p.get("summary") or p.get("description") or "" for p in profile.get("projects", [])]
        + [e.get("summary") or "" for e in profile.get("experience", [])]
    )
    sims, sim_method = similarities(profile_text, [f"{j['title']}. {j.get('description', '')}" for j, *_ in candidates])

    results = []
    for (job, req, sal_score, sal_reason, note), sim in zip(candidates, sims):
        req_skills, nice_skills = req["required_skills"], req["nice_skills"]
        weight = lambda s: STRENGTH_WEIGHT.get(skills[s.lower()]["level_hint"], 0) if s.lower() in skills else 0
        possible = 2 * len(req_skills) + len(nice_skills)
        got = 2 * sum(weight(s) for s in req_skills) + sum(weight(s) for s in nice_skills)
        skill_score = got / possible if possible else 0.5

        level_score = 1.0 if req["level"] == "entry" or level == "experienced" else 0.6
        score = 0.50 * skill_score + 0.25 * sim + 0.15 * sal_score + 0.10 * level_score
        if note:
            score *= 0.9  # exact-filter matches rank above widened ones
        is_liked = any(l in job.get("company", "").lower() for l in liked)
        if is_liked:
            score = min(1.0, score + 0.05)

        matched = [s for s in req_skills if s.lower() in skills]
        missing = [s for s in req_skills if s.lower() not in skills]
        nice_have = [s for s in nice_skills if s.lower() in skills]

        reasons = []
        if req_skills:
            reasons.append(f"Matches {len(matched)} of {len(req_skills)} required skills"
                           + (f" ({', '.join(matched[:5])})" if matched else ""))
        if nice_have:
            reasons.append(f"Also has nice-to-have: {', '.join(nice_have[:4])}")
        if missing:
            reasons.append(f"Missing: {', '.join(missing[:5])}")
        if sal_reason:
            reasons.append(sal_reason)
        reasons.append({"entry": "Entry-level role", "mid": "Mid-level role (a step up)",
                        "senior": "Senior role"}[req["level"]] + f" - you are {level}")
        if is_liked:
            reasons.append("One of your preferred companies")
        if note:
            reasons.insert(0, note)
        if req["skills_inferred_from_title"]:
            reasons.append("Listing is short, so typical skills for this title were used")

        coverage = len(matched) / len(req_skills) if req_skills else 0
        results.append({
            "job_id": job["id"],
            "title": job["title"],
            "company": job.get("company"),
            "location": job.get("location"),
            "work_mode": req["work_mode"],
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "salary_is_estimate": job.get("salary_is_estimate", False),
            "currency": prefs.get("currency"),
            "url": job.get("url"),
            "posted": job.get("posted"),
            "source": job.get("source"),
            "level": req["level"],
            "field": job["_field"],
            "field_is_suggested": job["_field"] in extra,
            "outside_filters": note,
            "match_score": round(score * 100),
            "fit": "safe" if coverage >= 0.7 else "stretch" if coverage >= 0.4 else "reach",
            "required_skills": req_skills,
            "nice_skills": nice_skills,
            "matched_skills": matched,
            "missing_skills": missing,
            "reasons": reasons,
            "description": job.get("description", "")[:1500],
        })

    # Jobs that match your exact filters always come first.
    results.sort(key=lambda r: (r["outside_filters"] is not None, -r["match_score"]))
    top_n = max(5, min(10, top_n))
    exact = [r for r in results if r["outside_filters"] is None]
    widened = [r for r in results if r["outside_filters"] is not None]
    chosen_jobs = _diverse(exact, all_fields, top_n)
    chosen_jobs += widened[: top_n - len(chosen_jobs)]
    chosen_jobs.sort(key=lambda r: (r["outside_filters"] is not None, -r["match_score"]))
    fields_found = list(dict.fromkeys(r["field"] for r in chosen_jobs))
    return {
        "jobs": chosen_jobs,
        "fields": fields_found,
        "suggested_fields": extra,
        "source": source,
        "similarity_method": sim_method,
        "total_listings": len(jobs),
        "passed_filters": len(results),
        "filtered_out": dict(filtered_out),
        "warnings": warnings,
    }
