"""
GoOrGrow backend.
Run:   uvicorn main:app --reload
Test:  http://127.0.0.1:8000/docs
"""
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import document, llm, matching, store
from app import preferences as prefs_mod
from app.config import MAX_FILE_MB
from app.extract import extract_text
from app.links import read_link
from app.profile import _experience_level, build_profile
from app.readiness import build_readiness
from app.skills import normalize_skill, skills_in_line
from app import apply as apply_mod
from app import grow as grow_mod

app = FastAPI(title="GoOrGrow API", version="0.1")

# Lets the React/Next.js frontend (on another port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def website():
    """The GoOrGrow website (frontend)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"message": "GoOrGrow backend is running", "docs": "/docs", "ai_mode": llm.provider()}


@app.get("/health/check")
def health_check():
    """Tests your API keys with one tiny call each. Never shows the keys themselves."""
    from app.jobs import check_adzuna
    return {"ai": llm.check(), "jobs": check_adzuna()}


# ---------- Part 1: upload documents and links ----------

@app.post("/upload")
async def upload(
    files: List[UploadFile] = File(default=[], description="Resume, LinkedIn PDF, certificates (PDF/DOCX/PNG/JPG/TXT)"),
    links: Optional[str] = Form(default=None, description="Portfolio / GitHub links, separated by commas or new lines"),
    session_id: Optional[str] = Form(default=None, description="Leave empty to start a new session"),
):
    files = [f for f in files if f and f.filename]
    link_list = [l.strip() for l in (links or "").replace("\n", ",").split(",") if l.strip()]
    if not files and not link_list:
        raise HTTPException(400, "Upload at least one file or add at least one link.")

    try:
        session = store.get_session(session_id) if session_id else store.create_session()
    except KeyError:
        raise HTTPException(404, "Session not found")

    results = []

    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            results.append({"source": f.filename, "type": "file", "ok": False,
                            "warnings": [f"File is larger than {MAX_FILE_MB} MB"]})
            continue
        try:
            out = extract_text(f.filename, data)
        except ValueError as e:
            results.append({"source": f.filename, "type": "file", "ok": False, "warnings": [str(e)]})
            continue
        except Exception as e:  # damaged or password-protected files
            results.append({"source": f.filename, "type": "file", "ok": False,
                            "warnings": [f"Could not read this file: {e}"]})
            continue
        results.append({"source": f.filename, "type": "file", "ok": bool(out["text"]), **out})

    for url in link_list:
        try:
            out = read_link(url)
        except Exception as e:
            results.append({"source": url, "type": "link", "ok": False,
                            "warnings": [f"Could not open this link: {e}"]})
            continue
        results.append({"source": url, "type": "link", "ok": bool(out["text"]), **out})

    session["sources"].extend(r for r in results if r.get("ok"))
    store.save_session(session)

    return {
        "session_id": session["session_id"],
        "sources": [
            {
                "source": r["source"],
                "type": r["type"],
                "ok": r["ok"],
                "method": r.get("method"),
                "characters": len(r.get("text", "")),
                "preview": r.get("text", "")[:500],
                "warnings": r.get("warnings", []),
            }
            for r in results
        ],
        "total_sources_saved": len(session["sources"]),
    }


# ---------- Part 1b: build and confirm the profile ----------

class BuildProfileRequest(BaseModel):
    graduation_year: Optional[int] = Field(default=None, ge=1980, le=2040, description="Overrides the year found in the resume")


class ConfirmSkill(BaseModel):
    name: str
    evidence: Optional[str] = None
    level_hint: Optional[str] = "mentioned"


class ConfirmProfileRequest(BaseModel):
    graduation_year: Optional[int] = Field(default=None, ge=1980, le=2040)
    keep_skills: Optional[List[str]] = Field(default=None, description="Skill names to keep (others are removed). Leave empty to keep all verified skills.")
    add_skills: List[ConfirmSkill] = Field(default=[], description="Skills the candidate adds themselves")


def _load(session_id: str) -> dict:
    try:
        return store.get_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")


@app.post("/profile/{session_id}/build")
def build_profile_endpoint(session_id: str, body: BuildProfileRequest = BuildProfileRequest()):
    """Reads all uploaded text and creates the structured profile (skills, education, projects...)."""
    session = _load(session_id)
    try:
        session["profile"] = build_profile(session, body.graduation_year)
        for stale in ("matches", "readiness", "decision", "applications"):
            session.pop(stale, None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.save_session(session)
    return session["profile"]


@app.get("/profile/{session_id}")
def get_profile(session_id: str):
    session = _load(session_id)
    if "profile" not in session:
        raise HTTPException(404, "Profile not built yet - call /profile/{session_id}/build")
    return session["profile"]


@app.put("/profile/{session_id}/confirm")
def confirm_profile(session_id: str, body: ConfirmProfileRequest):
    """Checkpoint 1: the candidate reviews the profile, removes wrong skills, adds missing ones."""
    session = _load(session_id)
    prof = session.get("profile")
    if not prof:
        raise HTTPException(404, "Profile not built yet")

    skills = prof["skills"]
    if body.keep_skills is not None:
        keep = {normalize_skill(s).lower() for s in body.keep_skills}
        skills = [s for s in skills if s["name"].lower() in keep]
        # A skill the candidate explicitly keeps counts as confirmed by them.
        for s in skills:
            s["verified"] = True
    else:
        skills = [s for s in skills if s["verified"]]

    have = {s["name"].lower() for s in skills}
    for add in body.add_skills:
        name = normalize_skill(add.name)
        if name.lower() in have:
            continue
        skills.append({
            "name": name,
            "evidence": add.evidence or "Added by the candidate during profile review",
            "source": "candidate",
            "level_hint": add.level_hint if add.level_hint in ("used_at_work", "used_in_project", "mentioned") else "mentioned",
            "verified": True,
        })
        have.add(name.lower())

    prof["skills"] = skills
    if body.graduation_year:
        prof["graduation_year"] = body.graduation_year
        prof["experience_level"] = _experience_level(body.graduation_year)
    prof["confirmed"] = True
    session["profile"] = prof
    store.save_session(session)
    return prof


# ---------- Part 2: preferences ----------

@app.get("/preferences/{session_id}/suggestions")
def preference_suggestions(session_id: str):
    """Smart defaults for the preferences screen: job fields that fit the profile, detected cities..."""
    return prefs_mod.suggestions(_load(session_id))


@app.put("/preferences/{session_id}")
def save_preferences(session_id: str, body: prefs_mod.Preferences):
    session = _load(session_id)
    session["preferences"] = prefs_mod.to_saved(body)
    store.save_session(session)
    return session["preferences"]


@app.get("/preferences/{session_id}")
def get_preferences(session_id: str):
    session = _load(session_id)
    if "preferences" not in session:
        raise HTTPException(404, "Preferences not saved yet")
    return session["preferences"]


# ---------- Part 3: find and rank jobs ----------

class MatchRequest(BaseModel):
    top_n: int = Field(default=10, ge=5, le=10, description="How many jobs to return (5-10)")


ANALYSIS_STEPS = [
    "Reading your confirmed profile",
    "Collecting job listings",
    "Pulling out what each job asks for",
    "Filtering by field, place, level and salary",
    "Comparing your skills with every requirement",
    "Ranking your best matches",
]


@app.post("/match/{session_id}")
def match_jobs(session_id: str, body: MatchRequest = MatchRequest()):
    """Collects listings, filters them and returns the best 5-10 jobs with reasons."""
    session = _load(session_id)
    if "profile" not in session:
        raise HTTPException(400, "Build the profile first: /profile/{session_id}/build")
    if "preferences" not in session:
        raise HTTPException(400, "Save preferences first: /preferences/{session_id}")
    result = matching.find_matches(session["profile"], session["preferences"], body.top_n)
    if not session["profile"].get("confirmed"):
        result["warnings"].insert(0, "Profile not confirmed yet - results use only verified skills.")
    result["analysis_steps"] = ANALYSIS_STEPS
    session["matches"] = result
    for stale in ("readiness", "decision", "applications"):
        session.pop(stale, None)
    store.save_session(session)
    return result


@app.get("/match/{session_id}")
def get_matches(session_id: str):
    session = _load(session_id)
    if "matches" not in session:
        raise HTTPException(404, "No matches yet - call POST /match/{session_id}")
    return session["matches"]


# ---------- Part 3c: readiness flags ----------

@app.post("/readiness/{session_id}")
def readiness_endpoint(session_id: str):
    """Green / white / red flags for every skill, readiness % per job, and a salary reality check."""
    session = _load(session_id)
    if "matches" not in session:
        raise HTTPException(400, "Run the job match first: POST /match/{session_id}")
    try:
        session["readiness"] = build_readiness(session["profile"], session["matches"], session["preferences"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.save_session(session)
    return session["readiness"]


@app.get("/readiness/{session_id}")
def get_readiness(session_id: str):
    session = _load(session_id)
    if "readiness" not in session:
        raise HTTPException(404, "No readiness yet - call POST /readiness/{session_id}")
    return session["readiness"]


# ---------- Part 4: GO or GROW ----------

class DecisionRequest(BaseModel):
    choice: Literal["go", "grow"]


@app.post("/decision/{session_id}")
def decide(session_id: str, body: DecisionRequest):
    """The candidate picks GO or GROW. GO returns the jobs to choose from; GROW returns the learning plan."""
    session = _load(session_id)
    if "readiness" not in session:
        raise HTTPException(400, "Run readiness first: POST /readiness/{session_id}")
    r = session["readiness"]
    session["decision"] = {"choice": body.choice, "suggested": r["summary"]["suggested_choice"]}

    if body.choice == "grow":
        session["grow_plan"] = grow_mod.build_plan(r)
        store.save_session(session)
        return {"choice": "grow", "plan": session["grow_plan"]}

    order = {"go": 0, "go_stretch": 1, "grow": 2}
    by_id = {j["job_id"]: j for j in session["matches"]["jobs"]}
    options = sorted(r["jobs"], key=lambda j: (order[j["recommendation"]], -(j["match_score"] or 0)))
    store.save_session(session)
    return {
        "choice": "go",
        "message": "Pick one or more jobs and we'll prepare a tailored application for each.",
        "options": [{
            **o,
            "location": by_id.get(o["job_id"], {}).get("location"),
            "salary_min": by_id.get(o["job_id"], {}).get("salary_min"),
            "salary_max": by_id.get(o["job_id"], {}).get("salary_max"),
            "currency": by_id.get(o["job_id"], {}).get("currency"),
            "url": by_id.get(o["job_id"], {}).get("url"),
        } for o in options],
    }


class ApplyRequest(BaseModel):
    job_ids: List[str] = Field(..., min_length=1, max_length=10, description="Job ids from the GO options")


@app.post("/apply/{session_id}")
def prepare_applications(session_id: str, body: ApplyRequest):
    """GO: build tailored, evidence-checked application material for each selected job."""
    session = _load(session_id)
    if "readiness" not in session:
        raise HTTPException(400, "Run readiness first")
    jobs = {j["job_id"]: j for j in session["matches"]["jobs"]}
    rjobs = {j["job_id"]: j for j in session["readiness"]["jobs"]}
    unknown = [i for i in body.job_ids if i not in jobs]
    if unknown:
        raise HTTPException(400, f"Unknown job ids: {', '.join(unknown)}")

    apps = session.setdefault("applications", {})
    out = []
    for jid in body.job_ids:
        apps[jid] = apply_mod.tailor_application(session["profile"], jobs[jid], rjobs.get(jid))
        out.append(apps[jid])
    store.save_session(session)
    return {"applications": out}


class ApproveRequest(BaseModel):
    summary: Optional[str] = None
    resume_bullets: Optional[List[str]] = None
    cover_note: Optional[str] = None


@app.put("/apply/{session_id}/{job_id}/approve")
def approve_application(session_id: str, job_id: str, body: ApproveRequest = ApproveRequest()):
    """Checkpoint 2: the candidate edits (optional) and approves. We still never submit anything."""
    session = _load(session_id)
    app_ = session.get("applications", {}).get(job_id)
    if not app_:
        raise HTTPException(404, "No application prepared for this job")

    my_skills = {s["name"].lower() for s in session["profile"]["skills"] if s.get("verified")}
    warnings = []
    if body.summary is not None:
        app_["summary"] = body.summary
    if body.resume_bullets is not None:
        app_["resume_bullets"] = [{"text": b, "evidence_ids": [], "edited_by_candidate": True} for b in body.resume_bullets]
    if body.cover_note is not None:
        app_["cover_note"] = body.cover_note
    # Gentle check on the candidate's own edits: warn, don't block - it's their application.
    for text in [body.summary or "", body.cover_note or ""] + (body.resume_bullets or []):
        for s in skills_in_line(text, in_skills_section=True):
            if s.lower() not in my_skills and s not in (app_.get("title") or ""):
                warnings.append(f"Your edit mentions '{s}', which isn't in your profile - only keep it if it's true.")
    app_["approved"] = True
    app_["edit_warnings"] = sorted(set(warnings))
    store.save_session(session)
    return {"approved": True, "apply_link": app_.get("apply_link"), "warnings": app_["edit_warnings"],
            "next": "Open the apply link and submit it yourself. Good luck!"}


@app.get("/apply/{session_id}/{job_id}/document", response_class=HTMLResponse)
def application_document(session_id: str, job_id: str):
    """The finished application (resume + cover letter) as a printable page."""
    session = _load(session_id)
    app_ = session.get("applications", {}).get(job_id)
    if not app_:
        raise HTTPException(404, "No application prepared for this job")
    return document.render(app_, session["profile"])


@app.get("/grow/{session_id}")
def get_grow_plan(session_id: str):
    session = _load(session_id)
    if "grow_plan" not in session:
        raise HTTPException(404, "No learning plan yet - choose GROW first")
    return session["grow_plan"]


@app.post("/recheck/{session_id}")
def recheck(session_id: str):
    """After learning: upload new resume/project links to the same session, then call this.
    Rebuilds the profile (keeping skills you added yourself), re-runs matching and flags,
    and shows what changed."""
    session = _load(session_id)
    if "preferences" not in session or "readiness" not in session:
        raise HTTPException(400, "Complete one full check first")
    before = session["readiness"]
    kept = [s for s in session.get("profile", {}).get("skills", []) if s.get("source") == "candidate"]

    prof = build_profile(session)
    have = {s["name"].lower() for s in prof["skills"]}
    prof["skills"] += [s for s in kept if s["name"].lower() not in have]
    session["profile"] = prof
    session["matches"] = matching.find_matches(prof, session["preferences"])
    after = build_readiness(prof, session["matches"], session["preferences"])
    session["readiness"] = after

    red_before = {f["skill"] for f in before["flags"]["red"]}
    red_after = {f["skill"] for f in after["flags"]["red"]}
    green_after = {f["skill"] for f in after["flags"]["green"]}
    store.save_session(session)
    return {
        "suggested_before": before["summary"]["suggested_choice"],
        "suggested_now": after["summary"]["suggested_choice"],
        "jobs_ready_before": before["summary"]["jobs_ready_now"],
        "jobs_ready_now": after["summary"]["jobs_ready_now"],
        "fixed_skills": sorted(red_before - red_after),
        "now_green": sorted((red_before - red_after) & green_after),
        "still_missing": sorted(red_after),
        "message": after["summary"]["message"],
    }


@app.get("/session/{session_id}")
def get_session(session_id: str):
    try:
        s = store.get_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    return {
        "session_id": s["session_id"],
        "created_at": s["created_at"],
        "sources": [{"source": x["source"], "type": x["type"], "characters": len(x["text"])} for x in s["sources"]],
    }


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    """Privacy: let the user delete everything they uploaded."""
    try:
        deleted = store.delete_session(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    return {"deleted": deleted}
