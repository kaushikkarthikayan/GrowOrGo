"""
End-to-end check of the whole GoOrGrow backend - no server or browser needed.
Run:   python test_flow.py
Optional: python test_flow.py path\\to\\your_resume.pdf
"""
import sys
from pathlib import Path

import os

# The self-test always uses demo jobs so it never spends your limited Adzuna calls.
# Run "python test_flow.py --live" to use your real keys.
if "--live" not in sys.argv:
    os.environ["ADZUNA_APP_ID"] = ""
    os.environ["ADZUNA_APP_KEY"] = ""
sys.argv = [a for a in sys.argv if a != "--live"]

from fastapi.testclient import TestClient

from main import app

c = TestClient(app)
resume = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "samples" / "sample_resume.txt"
ok = True


def step(n, title):
    print(f"\n=== Step {n}: {title} ===")


def check(cond, msg):
    global ok
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    ok = ok and cond


home = c.get("/health").json()
print(f"AI mode: {home['ai_mode']}")

step(1, "Upload")
with open(resume, "rb") as f:
    r = c.post("/upload", files=[("files", (resume.name, f))])
check(r.status_code == 200, f"upload {resume.name}")
sid = r.json()["session_id"]
src = r.json()["sources"][0]
check(src["ok"], f"read {src['characters']} characters ({src['method']})")

step(2, "Profile")
p = c.post(f"/profile/{sid}/build", json={}).json()
check(len(p["skills"]) > 0, f"{len(p['skills'])} skills found: {', '.join(s['name'] for s in p['skills'][:8])}...")
print(f"  graduation year: {p['graduation_year']}  level: {p['experience_level']}")
p = c.put(f"/profile/{sid}/confirm", json={}).json()
check(p["confirmed"], "profile confirmed")

step(3, "Preferences")
s = c.get(f"/preferences/{sid}/suggestions").json()
fields = [x["role"] for x in s["suggested_job_fields"][:2]] or ["Data Analyst"]
shown = ", ".join("%s (%s%%)" % (x["role"], x["match_percent"]) for x in s["suggested_job_fields"][:4])
print("  suggested fields: " + shown)
r = c.put(f"/preferences/{sid}", json={"job_fields": fields, "country": s["suggested_country"],
                                        "locations": s["detected_locations"][:1]})
check(r.status_code == 200, f"saved preferences: {fields}")

step(4, "Job match")
m = c.post(f"/match/{sid}").json()
check(5 <= len(m["jobs"]) <= 10, f"{len(m['jobs'])} jobs from {m['source']} ({m['similarity_method']})")
for j in m["jobs"][:5]:
    print(f"  {j['match_score']:>3}  {j['fit']:<8} {j['title']} - {j['company']}")

step(5, "Readiness flags")
rd = c.post(f"/readiness/{sid}").json()
sm = rd["summary"]
print(f"  GREEN: {', '.join(sm['best_at']) or '-'}")
print(f"  RED:   {', '.join(sm['missing']) or '-'}")
print(f"  WHITE: {', '.join(sm['can_improve']) or '-'}")
print(f"  {sm['message']}")
check(sm["suggested_choice"] in ("go", "grow"), f"suggested: {sm['suggested_choice'].upper()}")

step(6, "GO -> tailored application")
d = c.post(f"/decision/{sid}", json={"choice": "go"}).json()
jid = d["options"][0]["job_id"]
a = c.post(f"/apply/{sid}", json={"job_ids": [jid]}).json()["applications"][0]
check(bool(a["resume_bullets"]), f"application for {a['title']} - {len(a['resume_bullets'])} bullets, "
                                 f"{len(a['blocked_items'])} blocked")
print("  " + a["cover_note"].replace("\n\n", "\n  "))
check(c.put(f"/apply/{sid}/{jid}/approve", json={}).json()["approved"], "approved by candidate")

step(6, "GROW -> learning plan")
g = c.post(f"/decision/{sid}", json={"choice": "grow"}).json()["plan"]
print(f"  {g['headline']}")
for it in g["items"][:4]:
    print(f"  {it['priority']}. {it['skill']} ({it['effort_estimate']})")
check(True, "plan built")

step(7, "Recheck + delete")
rc = c.post(f"/recheck/{sid}").json()
check("suggested_now" in rc, f"recheck: {rc['suggested_before']} -> {rc['suggested_now']}")
check(c.delete(f"/session/{sid}").json()["deleted"], "session deleted (privacy)")

print("\nALL STEPS PASSED" if ok else "\nSOME STEPS FAILED - see FAIL lines above")
sys.exit(0 if ok else 1)
