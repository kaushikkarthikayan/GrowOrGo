"""Part 1: read profile links (portfolio sites and GitHub).
LinkedIn has no open API and blocks scraping, so we ask for the PDF export instead."""
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import GITHUB_TOKEN

TIMEOUT = 15
MAX_CHARS = 15000
HEADERS = {"User-Agent": "GoOrGrow/0.1 (hackathon project)"}


def _github(username: str) -> dict:
    headers = {"Accept": "application/vnd.github+json", **HEADERS}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
        user = client.get(f"https://api.github.com/users/{username}")
        if user.status_code == 404:
            raise ValueError(f"GitHub user '{username}' not found")
        user.raise_for_status()
        repos = client.get(
            f"https://api.github.com/users/{username}/repos",
            params={"per_page": 50, "sort": "updated"},
        )
        repos.raise_for_status()

    u = user.json()
    lines = [f"GitHub profile: {u.get('name') or username}"]
    if u.get("bio"):
        lines.append(f"Bio: {u['bio']}")
    for r in repos.json():
        if r.get("fork"):
            continue
        desc = r.get("description") or ""
        lang = r.get("language") or ""
        topics = ", ".join(r.get("topics") or [])
        lines.append(
            f"Project: {r['name']}"
            + (f" - {desc}" if desc else "")
            + (f" (language: {lang})" if lang else "")
            + (f" [topics: {topics}]" if topics else "")
        )
    return {"text": "\n".join(lines), "method": "github_api", "warnings": []}


def _webpage(url: str) -> dict:
    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    text = "\n".join(t.strip() for t in soup.get_text("\n").splitlines() if t.strip())
    warnings = []
    if len(text) < 100:
        warnings.append("Very little text found - the site may load its content with JavaScript.")
    return {"text": text[:MAX_CHARS], "method": "webpage", "warnings": warnings}


def read_link(url: str) -> dict:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if "linkedin.com" in host:
        return {
            "text": "",
            "method": "skipped",
            "warnings": [
                "LinkedIn pages can't be read automatically. On your LinkedIn profile, "
                "click More > Save to PDF, then upload that PDF instead."
            ],
        }
    if host in ("github.com", "www.github.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return _github(parts[0])
    return _webpage(url)
