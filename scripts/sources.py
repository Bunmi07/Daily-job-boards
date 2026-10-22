"""Registry of job-board sources.

To add a board: write sources/<name>.js (see sources/README.md for the
contract), then add an entry here with the page the browser tab must be on
and a function that turns the user's config into that script's settings.
"""

from __future__ import annotations

US_REMOTE_SEARCH = {"location": "United States", "geo_id": 103644278, "remote": True}


def _linkedin(cfg: dict, src: dict) -> dict:
    searches = src.get("searches")
    if not searches:
        searches = []
        for loc in cfg["search"].get("locations", []):
            li = loc.get("linkedin") or {}
            searches.append(
                {
                    "location": li.get("location", loc["name"]),
                    "geo_id": li.get("geo_id"),
                    "distance": li.get("distance", 25),
                }
            )
        if cfg["search"].get("include_remote") and "US" in cfg["search"].get("remote_countries", ["US"]):
            remote = dict(US_REMOTE_SEARCH)
            if src.get("remote_keywords"):
                remote["keywords"] = src["remote_keywords"]
            searches.append(remote)
    return {
        "linkedin": {
            "searches": searches,
            "max_pages": src.get("max_pages", 4),
            "enrich_limit": src.get("enrich_limit", 80),
            "snippet_chars": src.get("snippet_chars", 0),
        }
    }


def _builtin(cfg: dict, src: dict) -> dict:
    return {
        "builtin": {
            "categories": src.get("categories", ["product-management"]),
            "max_pages": src.get("max_pages", 4),
        }
    }


def _hiringcafe(cfg: dict, src: dict) -> dict:
    return {
        "hiringcafe": {
            "max_pages": src.get("max_pages", 10),
            "search_state": src.get("search_state") or {},
        }
    }


def _wellfound(cfg: dict, src: dict) -> dict:
    return {
        "wellfound": {
            "roles": src.get("roles", ["product-manager"]),
            "location_slugs": src.get("location_slugs", []),
            "max_pages": src.get("max_pages", 5),
        }
    }


# name -> (label shown in reports, start page for the tab, settings builder)
SOURCES = {
    "linkedin": ("LinkedIn", lambda s: "https://www.linkedin.com/jobs/", _linkedin),
    "builtin": ("Built In", lambda s: f"https://www.{s.get('site', 'builtin.com')}/jobs", _builtin),
    "hiringcafe": ("HiringCafe", lambda s: "https://hiringcafe.com/classic", _hiringcafe),
    "wellfound": ("Wellfound", lambda s: "https://wellfound.com/jobs", _wellfound),
}

# Order used when the same job appears on several boards: the first board in
# this list supplies the headline fields (LinkedIn first for its applicant count).
PRIORITY = ["linkedin", "builtin", "wellfound", "hiringcafe"]


def label(name: str) -> str:
    return SOURCES.get(name, (name.title(),))[0]
