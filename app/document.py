"""The finished application: a clean, printable page (resume + cover letter) for one job.
Open it in the browser, then Print -> Save as PDF to get a file to upload with the application."""
from html import escape


def _e(x) -> str:
    return escape(str(x or ""))


def _bullets(bullets: list) -> str:
    html, current = "", object()
    for b in bullets:
        g = b.get("group")
        if g != current:
            if html:
                html += "</ul>"
            html += (f"<h3>{_e(g)}</h3>" if g else "") + "<ul>"
            current = g
        html += f"<li>{_e(b['text'])}</li>"
    return html + ("</ul>" if html else "")


def render(app: dict, profile: dict) -> str:
    c = app.get("candidate") or {}
    name = c.get("name") or profile.get("name") or "Your name"
    if name.isupper():
        name = name.title()
    contact = [x for x in [c.get("email"), c.get("phone"), *(c.get("links") or [])] if x]
    strong = [s["name"] for s in profile.get("skills", [])
              if s.get("verified") and s.get("level_hint") in ("used_at_work", "used_in_project")]
    skills = list(dict.fromkeys(app.get("keywords_to_use", []) + strong))[:14]
    education = [e.get("evidence") or e.get("summary") for e in profile.get("education", [])][:4]
    draft = "" if app.get("approved") else '<p class="draft">Draft - approve it in GoOrGrow before you send it.</p>'
    cover = "".join(f"<p>{_e(p)}</p>" for p in (app.get("cover_note") or "").split("\n\n") if p.strip())

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(name)} - {_e(app.get('title'))} application</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
  body {{ margin: 0; background: #EEF3F1; color: #17332C; font: 15px/1.55 "Atkinson Hyperlegible", "Segoe UI", sans-serif; }}
  .bar {{ max-width: 794px; margin: 24px auto 0; display: flex; gap: 12px; align-items: center; justify-content: space-between; padding: 0 8px; }}
  .bar button {{ font: 700 15px "Atkinson Hyperlegible", sans-serif; padding: 12px 22px; border-radius: 999px; border: 0; background: #2747D8; color: #fff; cursor: pointer; }}
  .bar span {{ font-size: 14px; color: #4A6660; }}
  .page {{ max-width: 794px; margin: 16px auto 32px; background: #fff; padding: 56px 64px; box-shadow: 0 1px 3px rgba(23,51,44,.12); }}
  h1 {{ font: 800 34px/1.05 "Bricolage Grotesque", sans-serif; letter-spacing: -0.02em; margin: 0; }}
  .contact {{ color: #4A6660; margin: 6px 0 4px; }}
  .for {{ font-size: 13px; color: #4A6660; margin: 0 0 22px; }}
  h2 {{ font: 600 16px "Bricolage Grotesque", sans-serif; margin: 22px 0 6px; padding-bottom: 4px; border-bottom: 2px solid #17332C; }}
  h3 {{ font-size: 15px; margin: 10px 0 2px; }}
  ul {{ margin: 0; padding-left: 18px; }} li {{ margin: 3px 0; }}
  .skills {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .skills span {{ border: 1px solid #CFDCD6; border-radius: 4px; padding: 2px 8px; font-size: 14px; }}
  .letter p {{ margin: 0 0 12px; }}
  .draft {{ background: #FFF7DD; border-left: 4px solid #F2C14E; padding: 8px 12px; font-size: 14px; }}
  @media print {{
    body {{ background: #fff; }} .bar, .draft {{ display: none; }}
    .page {{ box-shadow: none; margin: 0; padding: 0; max-width: none; }}
    .page + .page {{ break-before: page; }}
  }}
</style></head><body>
<div class="bar"><span>Check every line, then print or save as PDF.</span><button onclick="window.print()">Print / Save as PDF</button></div>

<section class="page">
  {draft}
  <h1>{_e(name)}</h1>
  <p class="contact">{" | ".join(_e(x) for x in contact)}</p>
  <p class="for">Resume tailored for {_e(app.get('title'))} at {_e(app.get('company'))}</p>

  {f"<h2>Profile</h2><p>{_e(app.get('summary'))}</p>" if app.get("summary") else ""}
  <h2>Relevant experience and projects</h2>
  {_bullets(app.get("resume_bullets", []))}
  {f'<h2>Skills</h2><div class="skills">{"".join(f"<span>{_e(s)}</span>" for s in skills)}</div>' if skills else ""}
  {f'<h2>Education</h2><ul>{"".join(f"<li>{_e(x)}</li>" for x in education)}</ul>' if education else ""}
</section>

<section class="page letter">
  <h1>{_e(name)}</h1>
  <p class="contact">{" | ".join(_e(x) for x in contact)}</p>
  <h2>Cover letter - {_e(app.get('title'))}, {_e(app.get('company'))}</h2>
  {cover}
  <p>Kind regards,<br>{_e(name)}</p>
</section>
</body></html>"""
