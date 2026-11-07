"""Part 3a: collect job listings and pull out what each job asks for.

Sources (in order):
1. Adzuna API - real listings, used when ADZUNA_APP_ID and ADZUNA_APP_KEY are set in .env.
   Results are cached for a few hours to save the free monthly quota.
2. data/jobs.csv - optional, e.g. a Kaggle dataset you download.
3. app/data/sample_jobs.json - built-in demo listings (fictional companies marked "(demo)").
"""
import csv
import hashlib
import json
import os
import re
import time

import httpx

from .config import BASE_DIR, DATA_DIR
from .roles import ROLES
from .skills import skills_in_line

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_HOURS = 24
# Adzuna's trial key allows only a few calls in total, so we count every live call
# and switch to the backup listings before the limit is reached.
CALL_LOG = DATA_DIR / "adzuna_calls.json"


def adzuna_calls_used() -> int:
    try:
        return int(json.loads(CALL_LOG.read_text())["used"])
    except Exception:
        return 0


def _count_call() -> None:
    CALL_LOG.write_text(json.dumps({"used": adzuna_calls_used() + 1}))


def adzuna_budget_left() -> int:
    return int(os.getenv("ADZUNA_MAX_CALLS", "20")) - adzuna_calls_used()
SAMPLE_FILE = BASE_DIR / "app" / "data" / "sample_jobs.json"
CSV_FILE = DATA_DIR / "jobs.csv"

NICE_MARKERS = re.compile(r"(nice to have|desirable|bonus|is a plus|preferred|advantageous|would be great)", re.I)
SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead|principal|head of|manager|staff|director|architect)\b", re.I)
ENTRY_RE = re.compile(r"\b(junior|jr\.?|graduate|entry[- ]level|trainee|intern(ship)?|apprentice(ship)?|associate|early careers?|fresher)\b", re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)


# ---------------- sources ----------------

def adzuna_enabled() -> bool:
    return bool(os.getenv("ADZUNA_APP_ID", "").strip() and os.getenv("ADZUNA_APP_KEY", "").strip())


def check_adzuna() -> dict:
    """One small live search so you can confirm your Adzuna keys work."""
    if not adzuna_enabled():
        return {"ok": False, "message": "No Adzuna keys set - using demo listings."}
    used, left = adzuna_calls_used(), adzuna_budget_left()
    if used > 0:
        # Already made a successful live call - don't spend another one just to check.
        return {"ok": True, "message": f"Adzuna keys set. {used} live call(s) used so far, {max(left, 0)} left before switching to demo listings."}
    if left <= 0:
        return {"ok": False, "message": "Adzuna call limit reached - using demo listings."}
    _count_call()
    try:
        r = httpx.get("https://api.adzuna.com/v1/api/jobs/gb/search/1", timeout=20, params={
            "app_id": os.getenv("ADZUNA_APP_ID", "").strip(), "app_key": os.getenv("ADZUNA_APP_KEY", "").strip(),
            "results_per_page": 1, "what": "data analyst", "content-type": "application/json"})
        if r.status_code == 200:
            return {"ok": True, "message": f"Adzuna keys work ({r.json().get('count', 0):,} UK data analyst jobs live). "
                                          f"{adzuna_budget_left()} live calls left before switching to demo listings."}
        return {"ok": False, "message": f"Adzuna error {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "message": f"Could not reach Adzuna: {e}"}


def _cache_get(key: str):
    path = CACHE_DIR / f"{key}.json"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_HOURS * 3600:
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _cache_put(key: str, data) -> None:
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")


def _adzuna_search(country: str, what: str, where: str | None, salary_min: int | None) -> list[dict]:
    params = {
        "app_id": os.getenv("ADZUNA_APP_ID", "").strip(),
        "app_key": os.getenv("ADZUNA_APP_KEY", "").strip(),
        "results_per_page": 50,
        "what": what,
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
    if salary_min:
        params["salary_min"] = salary_min
    key = hashlib.md5(json.dumps([country, what, where, salary_min]).encode()).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if adzuna_budget_left() <= 0:
        raise RuntimeError("the Adzuna call limit set in .env (ADZUNA_MAX_CALLS) has been reached")
    _count_call()
    r = httpx.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params, timeout=20)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("results", []):
        jobs.append({
            "id": f"adzuna-{j.get('id')}",
            "title": j.get("title", "").replace("<strong>", "").replace("</strong>", ""),
            "company": (j.get("company") or {}).get("display_name", "Unknown company"),
            "location": (j.get("location") or {}).get("display_name", ""),
            "country": country,
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "salary_is_estimate": str(j.get("salary_is_predicted", "0")) == "1",
            "description": re.sub(r"<[^>]+>", "", j.get("description", "")),
            "url": j.get("redirect_url"),
            "posted": j.get("created"),
            "source": "Jobs by Adzuna",
        })
    _cache_put(key, jobs)
    return jobs


def _csv_jobs() -> list[dict]:
    if not CSV_FILE.exists():
        return []
    jobs = []
    with open(CSV_FILE, encoding="utf-8", errors="ignore") as f:
        for i, row in enumerate(csv.DictReader(f)):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}

            def num(k):
                try:
                    return float(re.sub(r"[^\d.]", "", row.get(k, "")) or 0) or None
                except ValueError:
                    return None

            jobs.append({
                "id": f"csv-{i}",
                "title": row.get("title") or row.get("job_title", ""),
                "company": row.get("company") or row.get("company_name", "Unknown company"),
                "location": row.get("location", ""),
                "country": row.get("country", "").lower() or None,
                "salary_min": num("salary_min") or num("min_salary"),
                "salary_max": num("salary_max") or num("max_salary"),
                "description": row.get("description") or row.get("job_description", ""),
                "url": row.get("url") or row.get("job_posting_url"),
                "posted": row.get("posted") or row.get("date"),
                "source": "Your jobs.csv",
            })
    return [j for j in jobs if j["title"]]


def _sample_jobs() -> list[dict]:
    jobs = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    for j in jobs:
        j["source"] = "Demo listing (fictional company)"
    return jobs


def collect_jobs(prefs: dict) -> tuple[list[dict], str, list[str]]:
    """Return (jobs, source_name, warnings)."""
    warnings: list[str] = []
    if adzuna_enabled():
        try:
            jobs: list[dict] = []
            # Max 4 calls per new search (your 2 main fields + 2 roles that fit your skills, first city).
            # Repeat searches come from the 24-hour cache and cost nothing.
            where = prefs["locations"][0] if prefs.get("locations") else None
            fields = prefs["job_fields"][:2] + prefs.get("explore_fields", [])[:2]
            for field in dict.fromkeys(fields):
                query = re.sub(r"\s*/\s*", " ", field)
                for job in _adzuna_search(prefs["country"], query, where, prefs.get("min_salary")):
                    jobs.append(dict(job))
            if jobs:
                return jobs, "adzuna", warnings
            warnings.append("Adzuna returned no jobs for these preferences - showing other listings.")
        except RuntimeError:
            warnings.append("Live Adzuna calls are used up for now, so these are other listings. "
                            "Searches you've already run still show real jobs.")
        except Exception as e:
            warnings.append(f"Could not reach Adzuna ({e}) - showing other listings.")

    jobs = _csv_jobs()
    if jobs:
        return jobs, "csv", warnings
    if not adzuna_enabled():
        warnings.append("Using built-in demo listings. Add Adzuna keys in .env to see real jobs.")
    else:
        warnings.append("These are demo listings from fictional companies.")
    return _sample_jobs(), "demo", warnings


# ---------------- requirement extraction ----------------

def extract_requirements(job: dict) -> dict:
    """Pull required / nice-to-have skills, level and work mode out of a listing's text."""
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    required: list[str] = []
    nice: list[str] = []
    # Split into sentences; anything after a "nice to have" marker counts as optional.
    for sentence in re.split(r"(?<=[.!?;])\s+|\n", text):
        target = nice if NICE_MARKERS.search(sentence) else required
        for s in sorted(skills_in_line(sentence, in_skills_section=True)):
            if s not in required and s not in nice:
                target.append(s)

    inferred = False
    if len(required) < 2:
        # Short descriptions (Adzuna gives snippets): fall back to the typical skills for this title.
        title = job.get("title", "").lower()
        for role, spec in ROLES.items():
            words = [w for w in re.split(r"[^a-z]+", role.lower()) if len(w) > 2]
            if words and all(w in title for w in words[:2]):
                for s in spec["core"]:
                    if s not in required and s not in nice:
                        required.append(s)
                inferred = True
                break

    if job.get("level_hint"):
        level = job["level_hint"]
    elif SENIOR_RE.search(job.get("title", "")):
        level = "senior"
    elif ENTRY_RE.search(text):
        level = "entry"
    else:
        years = [int(y) for y in YEARS_RE.findall(text)]
        level = "senior" if years and max(years) >= 5 else "mid" if years and max(years) >= 2 else "entry"

    if job.get("work_mode"):
        mode = job["work_mode"]
    elif REMOTE_RE.search(text):
        mode = "remote"
    elif HYBRID_RE.search(text):
        mode = "hybrid"
    else:
        mode = "not stated"

    return {"required_skills": required, "nice_skills": nice, "level": level,
            "work_mode": mode, "skills_inferred_from_title": inferred}
