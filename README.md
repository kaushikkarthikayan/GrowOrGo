# GoOrGrow

**AI career tool for students:** upload your resume, match it to real jobs, and get an honest verdict for each role: **GO** (apply now) or **GROW** (build these skills first).

GoOrGrow reads a candidate's resume, finds 5–10 matching jobs, flags every skill 🟢 / ⚪ / 🔴, and lets the candidate choose:

- **GO** → tailored, truthful application material (resume summary, resume points, cover letter) for the jobs they pick
- **GROW** → an ordered learning plan for the skills they're missing, then a re-check

Built with Python + FastAPI, with a plain HTML/CSS/JavaScript website (animated with GSAP) served by the same server. It works **with no API keys** (demo mode), and gets smarter when you add them.

```powershell
git clone https://github.com/kaushikkarthikayan/GrowOrGo.git
cd GrowOrGo
```

📄 A full illustrated project guide is in [`docs/GoOrGrow_Project_Guide.docx`](docs/GoOrGrow_Project_Guide.docx) (Word).

---

## 1. Setup (Windows, first time only)

You need **Python 3.12**. Python 3.15 is too new for some libraries.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1          # the line should now start with (.venv)
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell says "running scripts is disabled", run this once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Optional: reading scanned resumes.** Install Tesseract OCR from https://github.com/UB-Mannheim/tesseract/wiki using the default folder.

## 2. Add your keys (optional)

Copy `.env.example` and rename the copy to `.env`, then fill in what you have:

| Key | What it unlocks | Without it |
|---|---|---|
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (one is enough) | Smarter resume reading and better-written applications | Rule-based parsing and template drafts |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` (https://developer.adzuna.com/) | Real job listings | 32 built-in demo jobs (fictional companies marked "(demo)") |
| `GITHUB_TOKEN` | More GitHub lookups per hour | 60 lookups/hour |

**Never upload `.env` to GitHub.** It's already listed in `.gitignore`.

## 3. Run it

```powershell
.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

- **The website:** open **http://127.0.0.1:8000**
- **API test page:** open **http://127.0.0.1:8000/docs** to try every endpoint on its own

**Quick full check (no browser needed):**
```powershell
python test_flow.py                      # uses samples\sample_resume.txt
python test_flow.py C:\path\to\my_cv.pdf # or your own resume
```
It should end with `ALL STEPS PASSED`.

The first job match downloads a small AI model (~90 MB) once. To skip it, set `USE_EMBEDDINGS=false` in `.env`.

---

## 4. How the flow works (frontend order)

| Screen | Call | What comes back |
|---|---|---|
| **1. Upload** | `POST /upload` (files + optional links) | `session_id`, text preview, warnings |
| | `POST /profile/{id}/build` | Skills (each with the resume line that proves it), education, experience, projects |
| | `PUT /profile/{id}/confirm` | Candidate removes or adds skills (**checkpoint 1**) |
| **2. Preferences** | `GET /preferences/{id}/suggestions` | Suggested job fields with a match %, detected cities |
| | `PUT /preferences/{id}` | Saves field, salary, place, work mode, companies |
| **Loading animation** | `POST /match/{id}` | 5–10 jobs with score, reasons, safe/stretch/reach, plus `analysis_steps` to show while loading |
| **3. Results + flags** | `POST /readiness/{id}` | 🟢⚪🔴 flags, best at / missing / can improve, readiness % per job, salary reality check, suggested choice |
| **4. GO or GROW** | `POST /decision/{id}` with `{"choice": "go"}` or `{"choice": "grow"}` | GO: job options. GROW: learning plan |
| **GO page** | `POST /apply/{id}` with `{"job_ids": [...]}` | Summary, resume bullets, cover note, portfolio highlights, blocked lines with reasons |
| | `PUT /apply/{id}/{job_id}/approve` | Candidate edits and approves (**checkpoint 2**). Nothing is ever submitted |
| **GROW page** | `GET /grow/{id}` | Ordered learning plan |
| **Come back later** | `POST /upload` (same `session_id`), then `POST /recheck/{id}` | What changed: skills fixed, new verdict |
| **Privacy** | `DELETE /session/{id}` | Deletes everything for that user |

## 5. The rules that keep it honest

- **Every skill needs evidence.** If the AI claims a skill that isn't in the candidate's documents, it's marked unverified and not used.
- **Truthfulness guard on applications.** Any line that mentions a skill the candidate doesn't have, or a number not in their documents, is blocked and shown with the reason.
- **The candidate decides.** The system suggests GO or GROW, but the candidate chooses, and they submit applications themselves.
- **Fair scoring.** Name, gender, age, photo and college name are never used in scoring.
- **Salary checks use only real figures.** Missing salaries are shown as unknown, never guessed.

## 6. Project structure

```
main.py                 all API endpoints (also serves the website)
static/                 the website: index.html, app.css, app.js (no Node.js needed)
test_flow.py            end-to-end check
samples/                sample resume for testing
app/
  config.py             settings from .env
  store.py              one JSON file per session (data/sessions/)
  extract.py            PDF / DOCX / image / OCR text extraction
  links.py              GitHub + portfolio links (LinkedIn -> asks for the PDF)
  skills.py             skills list + aliases (edit to add skills)
  llm.py                Gemini / Claude / OpenAI / demo switch
  profile.py            builds the evidence-backed profile
  roles.py              common roles and their usual skills
  preferences.py        preferences + smart suggestions
  jobs.py               Adzuna / jobs.csv / demo listings + requirement extraction
  matching.py           filtering, scoring, reasons
  readiness.py          green / white / red flags, salary check
  grow.py               learning plan (add course links in COURSE_LINKS)
  apply.py              tailored applications + truthfulness guard
  data/sample_jobs.json demo listings
```

## 7. Ideas for later

- Add course links per skill in `app/grow.py` → `COURSE_LINKS`
- Move sessions to Supabase / PostgreSQL for multiple users
- Use application outcomes to tune the GO/GROW thresholds (`GO_AT`, `STRETCH_AT` in `readiness.py`)
- Interview prep based on each job's missing skills

## 8. Credits

- Job listings: [Jobs by Adzuna](https://www.adzuna.co.uk) (their terms ask that listings are labelled "Jobs by Adzuna")
- Animation: [GSAP](https://gsap.com) by GreenSock, bundled in `static/vendor/` under its standard no-charge licence
- Meaning matching: the pre-trained `all-MiniLM-L6-v2` model via `sentence-transformers`
- Sample resumes in `samples/` and demo job listings in `app/data/sample_jobs.json` are fictional
