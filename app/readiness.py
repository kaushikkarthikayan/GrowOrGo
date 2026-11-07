"""Part 3c: readiness flags - what you're best at, what you're missing, what you can improve.

🟢 GREEN  = on track: you have the skill with real proof (used at work or in a project) and your target jobs want it.
⚪ WHITE  = neutral / needs a push:
            - "weak_evidence": you list it, but there's no project or job showing you used it
            - "nice_to_have_gap": you don't have it, but jobs only list it as nice-to-have
            - "not_in_demand": you have it, but these target jobs don't ask for it (not shown in the Grow list)
🔴 RED    = need to improve: your target jobs require it and you don't have it.

Also gives every matched job a readiness % and a recommendation (go / go-stretch / grow),
plus a salary reality check using only real salary figures from the listings."""
from collections import defaultdict
from statistics import median

STRONG = {"used_at_work", "used_in_project"}
PROOF_WEIGHT = {"used_at_work": 1.0, "used_in_project": 0.9, "mentioned": 0.6}

GO_AT = 70       # readiness % needed for "go"
STRETCH_AT = 50  # readiness % for "go (stretch)"


def job_readiness(job: dict, skills: dict) -> dict:
    req = job.get("required_skills", [])
    status = []
    total = 0.0
    for s in req:
        have = skills.get(s.lower())
        if have and have["level_hint"] in STRONG:
            state = "met"
        elif have:
            state = "partly_met"
        else:
            state = "missing"
        total += PROOF_WEIGHT.get(have["level_hint"], 0) if have else 0
        status.append({"skill": s, "status": state,
                       "evidence": have.get("evidence") if have else None})
    pct = round(100 * total / len(req)) if req else 50
    missing = [x["skill"] for x in status if x["status"] == "missing"]
    if pct >= GO_AT and len(missing) <= 1:
        rec = "go"
    elif pct >= STRETCH_AT:
        rec = "go_stretch"
    else:
        rec = "grow"
    return {"readiness_percent": pct, "recommendation": rec, "requirements": status}


def build_readiness(profile: dict, matches: dict, prefs: dict) -> dict:
    jobs = matches.get("jobs", [])
    if not jobs:
        raise ValueError("No matched jobs yet - run the job match first.")

    skills = {s["name"].lower(): s for s in profile.get("skills", []) if s.get("verified")}
    all_jobs = jobs
    # Flags and the GO/GROW suggestion are based on the jobs inside the user's own choices;
    # widened "related role / other city" jobs only count if nothing else matched.
    in_filter = [j for j in jobs if not j.get("outside_filters")]
    jobs = in_filter or jobs
    n = len(jobs)

    required_by = defaultdict(list)
    nice_by = defaultdict(list)
    for j in jobs:
        label = f"{j['title']} - {j.get('company') or ''}".strip(" -")
        for s in j.get("required_skills", []):
            required_by[s].append(label)
        for s in j.get("nice_skills", []):
            nice_by[s].append(label)

    green, white, red = [], [], []
    all_demanded = set(required_by) | set(nice_by)

    for name in sorted(all_demanded, key=lambda s: (-len(required_by[s]), -len(nice_by[s]), s)):
        have = skills.get(name.lower())
        demand = {"required_in": len(required_by[name]), "nice_in": len(nice_by[name]), "out_of_jobs": n,
                  "jobs": (required_by[name] + nice_by[name])[:5]}
        if have and have["level_hint"] in STRONG:
            green.append({"skill": name, "flag": "green", "reason": "You've used it and your target jobs want it",
                          "evidence": have.get("evidence"), **demand})
        elif have:
            white.append({"skill": name, "flag": "white", "code": "weak_evidence",
                          "reason": "You list it, but there's no project or job showing you used it - add proof",
                          "evidence": have.get("evidence"), **demand})
        elif required_by[name]:
            red.append({"skill": name, "flag": "red", "reason": f"Required by {len(required_by[name])} of your {n} matched jobs",
                        **demand})
        else:
            white.append({"skill": name, "flag": "white", "code": "nice_to_have_gap",
                          "reason": "Not required, but would make you stand out", **demand})

    for key, s in skills.items():
        if s["name"] not in all_demanded:
            white.append({"skill": s["name"], "flag": "white", "code": "not_in_demand",
                          "reason": "You have it, but these target jobs don't ask for it",
                          "evidence": s.get("evidence"), "required_in": 0, "nice_in": 0, "out_of_jobs": n, "jobs": []})

    # Per-job readiness
    per_job = []
    for j in all_jobs:
        r = job_readiness(j, skills)
        per_job.append({"job_id": j["job_id"], "title": j["title"], "company": j.get("company"),
                        "match_score": j.get("match_score"), "outside_filters": j.get("outside_filters"), **r})

    counts = defaultdict(int)
    for p in per_job:
        if p["job_id"] in {j["job_id"] for j in jobs}:
            counts[p["recommendation"]] += 1
    # GO needs at least one job you're ready for now, and half your jobs within reach.
    overall = "go" if counts["go"] >= 1 and counts["go"] + counts["go_stretch"] >= -(-n // 2) else "grow"

    return {
        "summary": {
            "best_at": [g["skill"] for g in green[:5]],
            "missing": [r["skill"] for r in red[:5]],
            "can_improve": [w["skill"] for w in white if w["code"] in ("weak_evidence", "nice_to_have_gap")][:5],
            "counts": {"green": len(green), "white": len(white), "red": len(red)},
            "jobs_ready_now": counts["go"],
            "jobs_stretch": counts["go_stretch"],
            "jobs_need_growth": counts["grow"],
            "suggested_choice": overall,
            "message": (
                f"You're ready to apply to {counts['go']} job(s) now"
                + (f" and could stretch for {counts['go_stretch']} more" if counts["go_stretch"] else "")
                + ". " + ("GO looks like a good choice." if overall == "go"
                          else f"Building {', '.join(r['skill'] for r in red[:3])} first would open up more roles - GROW looks like a good choice.")
            ),
        },
        "flags": {"green": green, "white": white, "red": red},
        "jobs": per_job,
        "based_on": f"{n} job(s) matching your chosen fields and places"
                    + ("" if in_filter else " (widened search)"),
        "salary_check": salary_check(jobs, prefs),
    }


def salary_check(jobs: list[dict], prefs: dict) -> dict:
    """Compare the target salary with what the matched jobs really pay (listed figures only)."""
    target, cur = prefs.get("target_salary"), prefs.get("currency", "")
    mids = []
    for j in jobs:
        lo, hi = j.get("salary_min"), j.get("salary_max")
        if (lo or hi) and not j.get("salary_is_estimate"):
            lo, hi = lo or hi, hi or lo
            mids.append((lo + hi) / 2)
    if not mids:
        return {"status": "unknown", "message": "None of the matched jobs list a confirmed salary, so we can't check your target."}
    med = median(mids)
    info = {"median_pay": round(med), "currency": cur, "based_on_jobs": len(mids), "target": target}
    if not target:
        return {"status": "no_target", "message": f"Matched jobs pay around {cur} {med:,.0f} a year.", **info}
    diff = (target - med) / med
    if diff <= 0.05:
        return {"status": "realistic", "message": f"Your target of {cur} {target:,.0f} is realistic - matched jobs pay around {cur} {med:,.0f}.", **info}
    if diff <= 0.20:
        return {"status": "ambitious", "message": f"Your target is {diff:.0%} above what matched jobs pay ({cur} {med:,.0f}). Closing your red-flag skills or a step up in level would help.", **info}
    return {"status": "unrealistic_now", "message": f"Your target is {diff:.0%} above typical pay for these roles ({cur} {med:,.0f}). It likely needs more experience or a more senior role.", **info}
