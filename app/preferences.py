"""Part 2: the candidate's preferences - job field, salary, place, companies they like."""
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .roles import ROLES, suggest_roles

# Country codes supported by the Adzuna jobs API, with their currency.
COUNTRIES = {
    "gb": ("United Kingdom", "GBP"), "in": ("India", "INR"), "us": ("United States", "USD"),
    "ca": ("Canada", "CAD"), "au": ("Australia", "AUD"), "de": ("Germany", "EUR"),
    "fr": ("France", "EUR"), "nl": ("Netherlands", "EUR"), "ie": ("Ireland", "EUR"),
    "sg": ("Singapore", "SGD"), "nz": ("New Zealand", "NZD"), "za": ("South Africa", "ZAR"),
}

KNOWN_CITIES = {
    "gb": ["London", "Manchester", "Birmingham", "Leeds", "Newcastle", "Liverpool", "Bristol",
           "Edinburgh", "Glasgow", "Cambridge", "Oxford", "Nottingham", "Sheffield", "Reading", "Cardiff"],
    "in": ["Chennai", "Bangalore", "Bengaluru", "Hyderabad", "Mumbai", "Pune", "Delhi", "Noida",
           "Gurgaon", "Gurugram", "Kolkata", "Coimbatore", "Kochi"],
    "us": ["New York", "San Francisco", "Seattle", "Austin", "Boston", "Chicago"],
}


class Preferences(BaseModel):
    job_fields: List[str] = Field(..., min_length=1, max_length=5,
                                  description="Job titles or fields, e.g. ['Data Analyst', 'BI Analyst']")
    country: str = Field(default="gb", description="Country code: gb, in, us, ca, au, de ...")
    locations: List[str] = Field(default=[], max_length=5, description="Cities. Empty = anywhere in the country")
    work_mode: Literal["any", "remote", "hybrid", "onsite"] = "any"
    target_salary: Optional[int] = Field(default=None, ge=0, description="Yearly salary you are aiming for")
    min_salary: Optional[int] = Field(default=None, ge=0, description="Lowest yearly salary you would accept")
    explore_related: bool = Field(default=True, description="Also include other roles that fit the candidate's skills")
    preferred_companies: List[str] = Field(default=[], max_length=20)
    avoid_companies: List[str] = Field(default=[], max_length=20)

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in COUNTRIES:
            raise ValueError(f"Unsupported country '{v}'. Use one of: {', '.join(COUNTRIES)}")
        return v

    @field_validator("job_fields", "locations", "preferred_companies", "avoid_companies")
    @classmethod
    def _clean_list(cls, v: List[str]) -> List[str]:
        seen, out = set(), []
        for item in v:
            item = item.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
        return out


def to_saved(prefs: Preferences) -> dict:
    data = prefs.model_dump()
    data["currency"] = COUNTRIES[prefs.country][1]
    warnings = []
    if prefs.min_salary and prefs.target_salary and prefs.min_salary > prefs.target_salary:
        warnings.append("Minimum salary is higher than the target salary - please check.")
    overlap = {c.lower() for c in prefs.preferred_companies} & {c.lower() for c in prefs.avoid_companies}
    if overlap:
        warnings.append("Some companies are in both 'preferred' and 'avoid': " + ", ".join(sorted(overlap)))
    data["warnings"] = warnings
    return data


def suggestions(session: dict) -> dict:
    """Smart defaults for the preferences screen, built from the candidate's profile."""
    prof = session.get("profile") or {}
    strength = {s["name"]: s["level_hint"] for s in prof.get("skills", []) if s.get("verified")}
    text = "\n".join(s["text"] for s in session.get("sources", []))

    found_cities = []
    detected_country = None
    for code, cities in KNOWN_CITIES.items():
        for city in cities:
            if re.search(rf"\b{re.escape(city)}\b", text, re.I) and city not in found_cities:
                found_cities.append(city)
                detected_country = detected_country or code

    return {
        "suggested_job_fields": suggest_roles(strength),
        "all_job_fields": list(ROLES),
        "detected_locations": found_cities[:5],
        "suggested_country": detected_country or "gb",
        "countries": {k: v[0] for k, v in COUNTRIES.items()},
        "work_modes": ["any", "remote", "hybrid", "onsite"],
        "experience_level": prof.get("experience_level", "unknown"),
        "note": None if strength else "Build the profile first for personalised suggestions.",
    }
