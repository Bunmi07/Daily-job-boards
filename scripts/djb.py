#!/usr/bin/env python3
"""daily-job-board command line.

  python scripts/djb.py plan   --config CONFIG                 list enabled sources and the page each needs
  python scripts/djb.py js     --config CONFIG --source NAME   print the script to run in that source's tab
  python scripts/djb.py merge  --config CONFIG --run RUN_DIR   filter + merge raw exports into candidates
  python scripts/djb.py render --config CONFIG --run RUN_DIR   build the email from candidates + scores

A run directory looks like:
  RUN_DIR/raw/<source>.txt      page text copied from each tab after export.js
  RUN_DIR/candidates.json       written by merge
  RUN_DIR/candidates.md         written by merge, read by Claude for scoring
  RUN_DIR/scores.json           written by Claude: {"<key>": {"tier": ..., "why": ...}}
  RUN_DIR/report.html|.txt      written by render
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import PRIORITY, SOURCES, label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TIERS = [
    ("apply_first", "Apply first"),
    ("solid", "Solid fits"),
    ("contract", "Contract"),
    ("maybe", "Worth a look"),
]

# ---------------------------------------------------------------- config


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text()) or {}
    s = cfg.setdefault("search", {})
    s.setdefault("hours", 24)
    s.setdefault("grace_hours", 2)
    s.setdefault("keywords", ["product manager"])
    s.setdefault("title_include", [])
    s.setdefault("title_exclude", [])
    s.setdefault("locations", [])
    s.setdefault("include_remote", True)
    s.setdefault("remote_countries", ["US"])
    s.setdefault("employment_types", [])
    s.setdefault("min_salary", 0)
    s.setdefault("flag_salary_below", 0)
    s.setdefault("max_required_years", 0)
    cfg.setdefault("skip_companies", [])
    cfg.setdefault("pipeline", [])
    cfg.setdefault("sources", {})
    r = cfg.setdefault("report", {})
    r.setdefault("max_jobs", 30)
    r.setdefault("timezone", "America/New_York")
    r.setdefault("subject", "Daily job board · {date} · {count} roles")
    return cfg


def phrases_regex(items: list[str], word_bounds: bool = True) -> str:
    """Plain phrases -> one case-insensitive alternation usable in Python and JS."""
    parts = []
    for p in items:
        p = str(p).strip()
        if not p:
            continue
        if p.startswith("re:"):
            parts.append(p[3:])
        else:
            parts.append(re.escape(p).replace(r"\ ", r"\s+"))
    if not parts:
        return ""
    body = "(?:" + "|".join(parts) + ")"
    return rf"\b{body}\b" if word_bounds else body


def enabled_sources(cfg: dict) -> list[str]:
    return [n for n, s in cfg["sources"].items() if n in SOURCES and (s or {}).get("enabled", True)]


# ---------------------------------------------------------------- plan / js


def cmd_plan(cfg: dict, _args) -> None:
    for name in enabled_sources(cfg):
        print(f"{name}\t{SOURCES[name][1](cfg['sources'][name] or {})}")


def cmd_js(cfg: dict, args) -> None:
    name = args.source
    if name not in SOURCES:
        sys.exit(f"unknown source {name!r}; known: {', '.join(SOURCES)}")
    src = cfg["sources"].get(name) or {}
    s = cfg["search"]
    settings = {
        "source": name,
        "hours": s["hours"],
        "grace_hours": s["grace_hours"],
        "keywords": src.get("keywords", s["keywords"]),
        "title_include": phrases_regex(s["title_include"]),
        "title_exclude": phrases_regex(s["title_exclude"]),
        "location_match": [phrases_regex(loc.get("match", []), False) for loc in s["locations"] if loc.get("match")],
        "include_remote": s["include_remote"],
        "remote_countries": s["remote_countries"],
        "max_required_years": s["max_required_years"],
        "snippet_chars": src.get("snippet_chars", 160),
        "delay_ms": src.get("delay_ms", 300),
    }
    settings.update(SOURCES[name][2](cfg, src))
    out = [
        f"window.__DJB_CFG = {json.dumps(settings)};",
        (ROOT / "sources" / "_common.js").read_text(),
        (ROOT / "sources" / f"{name}.js").read_text(),
    ]
    text = "\n".join(out)
    # Drop comment-only and blank lines: the script is pasted into a tool call
    # every run, so shorter is cheaper. Nothing else is changed.
    text = "\n".join(l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("//")) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out} ({len(text)} chars)")
    else:
        print(text)


# ---------------------------------------------------------------- normalising

_CO_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|company|plc|gmbh|holdings|group|technologies|technology|usa|us)\b\.?"
)
_TITLE_SWAPS = [
    (r"\bsr\b\.?", "senior"),
    (r"\bjr\b\.?", "junior"),
    (r"\bmgr\b\.?", "manager"),
    (r"\bpm\b", "product manager"),
    (r"\btpm\b", "technical program manager"),
    (r"&", " and "),
]


def norm_company(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\.(ai|com|io|co|app)\b", " ", s)
    s = _CO_SUFFIX.sub(" ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_title(title: str) -> str:
    s = (title or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.split(r"\s[-–—|]\s(?=(?:remote|hybrid|us|usa|united states|new york|nyc|onsite)\b)", s)[0]
    for pat, rep in _TITLE_SWAPS:
        s = re.sub(pat, rep, s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def salary_max(text: str | None) -> int | None:
    """Best-effort top of a pay range in USD per year."""
    if not text:
        return None
    t = text.lower().replace(",", "")
    nums = []
    for n, k in re.findall(r"\$?\s?(\d+(?:\.\d+)?)\s?(k)?\b", t):
        v = float(n) * (1000 if k else 1)
        nums.append(v)
    nums = [n for n in nums if n >= 10]
    if not nums:
        return None
    top = max(nums)
    has_k = "k" in t
    if (re.search(r"/\s?h|hour|hr\b", t) and top < 500) or (not has_k and top < 100):
        top *= 2080
    elif top < 1000:  # "150-180" style with no K
        top *= 1000
    return int(top)


def pretty_salary(text: str | None) -> str | None:
    """'$180,000.00/yr - $240,000.00/yr' -> '$180K–$240K'; leaves odd formats alone."""
    if not text:
        return None
    t = text.lower().replace(",", "")
    nums = [float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s?(k)?\b", t)]
    nums = [n for n in nums if n >= 10]
    if not nums:
        return text.strip()
    hourly = (bool(re.search(r"/\s?h|hour|hr\b", t)) and max(nums) < 500) or ("k" not in t and max(nums) < 100)
    if hourly:
        fmt = lambda n: f"${n:g}"  # noqa: E731
        suffix = "/hr"
    else:
        nums = [n * 1000 if n < 1000 else n for n in nums]
        fmt = lambda n: f"${round(n / 1000)}K"  # noqa: E731
        suffix = ""
    lo, hi = min(nums), max(nums)
    return (fmt(lo) if lo == hi else f"{fmt(lo)}–{fmt(hi)}") + suffix


def short_years(text: str | None) -> str | None:
    """'4+ years of experience working on...' -> '4+ yrs'."""
    if not text:
        return None
    m = re.match(r"\s*(\d+\s?\+?\s?(?:(?:-|–|to)\s?\d+\s?\+?)?)\s*(?:years?|yrs?)", text, re.I)
    if not m:
        return None
    n = int(re.match(r"\d+", m.group(1)).group())
    if n >= 40:
        return None
    return re.sub(r"\s+", "", m.group(1)).replace("to", "–") + " yrs"


def applicants_label(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"first (\d+)", text)
    if m:
        return f"Under {m.group(1)} applicants"
    return text.strip()


def parse_export(text: str) -> dict:
    m = re.search(r"DJB_EXPORT_BEGIN(.*)DJB_EXPORT_END", text, re.S)
    body = m.group(1) if m else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(body)


# ---------------------------------------------------------------- merge


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _same_company(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and long_.startswith(short)


def cmd_merge(cfg: dict, args) -> None:
    run = Path(args.run)
    s = cfg["search"]
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=s["hours"] + s["grace_hours"])
    inc = re.compile(phrases_regex(s["title_include"]), re.I) if s["title_include"] else None
    exc = re.compile(phrases_regex(s["title_exclude"]), re.I) if s["title_exclude"] else None
    skip = {norm_company(c) for c in cfg["skip_companies"]}
    pipeline = [(norm_company(p["company"]), norm_title(p.get("title", "")), p) for p in cfg["pipeline"]]
    letters = lambda t: re.sub(r"[^a-z]", "", (t or "").lower())  # noqa: E731
    want_types = [letters(t) for t in s["employment_types"]]

    health, jobs, dropped = {}, [], {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for f in sorted((run / "raw").glob("*")):
        try:
            data = parse_export(f.read_text())
        except Exception as e:  # noqa: BLE001
            health[f.stem] = {"status": "unreadable", "error": str(e)[:200], "jobs": 0}
            continue
        src = data.get("source", f.stem)
        health[src] = {
            "status": data.get("status"),
            "scanned": data.get("scanned"),
            "jobs": len(data.get("jobs", [])),
            "log": data.get("log", [])[:5],
        }
        for j in data.get("jobs", []):
            j.setdefault("src", src)
            if not j.get("url") and src == "linkedin" and j.get("id"):
                j["url"] = f"https://www.linkedin.com/jobs/view/{j['id']}"
            title, company = j.get("title", ""), j.get("company", "")
            if not title or not company:
                drop("missing title/company")
                continue
            if inc and not inc.search(title):
                drop("title not targeted")
                continue
            if exc and exc.search(title):
                drop("title excluded")
                continue
            if j.get("posted_at"):
                try:
                    if dt.datetime.fromisoformat(j["posted_at"].replace("Z", "+00:00")) < cutoff:
                        drop("older than window")
                        continue
                except ValueError:
                    pass
            et = letters(j.get("employment_type"))
            if want_types and et and not any(w in et for w in want_types):
                drop("employment type")
                continue
            yrs = re.search(r"\d+", str(j.get("yoe") or ""))
            if s["max_required_years"] and yrs and s["max_required_years"] < int(yrs.group()) < 40:
                drop("asks for too many years")
                continue
            top = salary_max(j.get("salary"))
            if s["min_salary"] and top and top < s["min_salary"]:
                drop("pay below minimum")
                continue
            ck = norm_company(company)
            if ck in skip:
                drop("skipped company")
                continue
            j["_ck"], j["_tk"], j["_pay"] = ck, norm_title(title), top
            note = None
            for pk, pt, p in pipeline:
                if _same_company(ck, pk):
                    if pt and _similar(pt, j["_tk"]) >= 0.8:
                        note = "applied"
                    else:
                        note = f"In your pipeline: {p.get('title') or 'another role'}" + (
                            f" ({p['status']})" if p.get("status") else ""
                        )
                    break
            if note == "applied":
                drop("already applied")
                continue
            j["_pipeline"] = note
            jobs.append(j)

    # Cluster the same role across boards (and repeat postings on one board).
    clusters: list[list[dict]] = []
    for j in jobs:
        for c in clusters:
            h = c[0]
            if _same_company(j["_ck"], h["_ck"]) and (j["_tk"] == h["_tk"] or _similar(j["_tk"], h["_tk"]) >= 0.88):
                c.append(j)
                break
        else:
            clusters.append([j])

    def prio(j):
        return PRIORITY.index(j["src"]) if j["src"] in PRIORITY else len(PRIORITY)

    out = []
    for c in clusters:
        c.sort(key=prio)
        first = lambda field: next((x[field] for x in c if x.get(field)), None)  # noqa: E731
        boards = []
        for x in c:
            b = next((b for b in boards if b["src"] == x["src"]), None)
            if b:
                b["postings"] += 1
                continue
            boards.append(
                {
                    "src": x["src"],
                    "label": label(x["src"]),
                    "url": x.get("url"),
                    "posted_label": x.get("posted_label"),
                    "applicants": x.get("applicants"),
                    "postings": 1,
                }
            )
        # Prefer an exact posting time over a coarse one like "Yesterday".
        timed = [x for x in c if x.get("posted_at")]
        timed.sort(key=lambda x: (str(x.get("posted_label", "")).lower() == "yesterday", prio(x)))
        head = c[0]
        key = hashlib.sha1(f"{head['_ck']}|{head['_tk']}".encode()).hexdigest()[:8]
        top = next((x["_pay"] for x in c if x.get("_pay")), None)
        out.append(
            {
                "key": key,
                "title": head["title"],
                "company": head["company"],
                "location": first("location"),
                "workplace": first("workplace"),
                "salary": pretty_salary(first("salary")),
                "salary_max": top,
                "below_pay_target": bool(s["flag_salary_below"] and top and top < s["flag_salary_below"]),
                "posted_at": timed[0]["posted_at"] if timed else None,
                "applicants": applicants_label(first("applicants")),
                "employment_type": first("employment_type"),
                "seniority": first("seniority"),
                "yoe": short_years(first("yoe")),
                "company_size": re.sub(r"^SIZE_(\d+)_(\d+)$", r"\1-\2", first("company_size") or "") or None,
                "summary": first("summary"),
                "pipeline": head.get("_pipeline"),
                "boards": boards,
                "url": boards[0]["url"],
            }
        )

    out.sort(key=lambda r: r["posted_at"] or "", reverse=True)
    out.sort(key=lambda r: len(r["boards"]), reverse=True)

    result = {
        "generated_at": now.isoformat(timespec="seconds"),
        "window_hours": s["hours"],
        "health": health,
        "dropped": dropped,
        "kept_postings": len(jobs),
        "candidates": out,
    }
    (run / "candidates.json").write_text(json.dumps(result, indent=1))
    (run / "candidates.md").write_text(candidates_md(result, now))
    print(
        f"{len(out)} roles from {len(jobs)} postings "
        f"({sum(1 for r in out if len(r['boards']) > 1)} on 2+ boards); dropped {sum(dropped.values())}: {dropped}"
    )
    for src, h in health.items():
        print(f"  {label(src)}: {h.get('status')} · {h.get('jobs')} matched of {h.get('scanned')} scanned")


def ago(iso: str | None, now: dt.datetime) -> str:
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    mins = max(0, int((now - t).total_seconds() // 60))
    if mins < 60:
        return f"{mins}m ago"
    if mins < 48 * 60:
        return f"{mins // 60}h ago"
    return f"{mins // 1440}d ago"


def candidates_md(result: dict, now: dt.datetime) -> str:
    lines = [
        "# Candidates to score",
        "",
        "One line per role. Score each key in scores.json (see SKILL.md step 5).",
        "",
    ]
    for r in result["candidates"]:
        bits = [
            f"[{r['key']}] {r['title']} — {r['company']}",
            " / ".join(x for x in (r["location"], r["workplace"]) if x),
            r["salary"] or "pay n/a",
            r["employment_type"] or "",
            r["seniority"] or "",
            r["yoe"] or "",
            ago(r["posted_at"], now),
            "boards: " + ", ".join(b["label"] for b in r["boards"]),
            r["applicants"] or "",
            r["company_size"] or "",
            r["pipeline"] or "",
            "BELOW PAY TARGET" if r["below_pay_target"] else "",
            (r["summary"] or "")[:180],
        ]
        lines.append("- " + " | ".join(b for b in bits if b))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- render


def cmd_render(cfg: dict, args) -> None:
    from zoneinfo import ZoneInfo

    import jinja2

    run = Path(args.run)
    data = json.loads((run / "candidates.json").read_text())
    scores_path = run / "scores.json"
    scores = json.loads(scores_path.read_text()) if scores_path.exists() else {}
    tz = ZoneInfo(cfg["report"]["timezone"])
    now = dt.datetime.now(dt.timezone.utc)

    groups = {k: [] for k, _ in TIERS}
    for r in data["candidates"]:
        sc = scores.get(r["key"], {})
        tier = sc.get("tier", "maybe" if not scores else "skip")
        if tier not in groups:
            continue
        r["why"] = sc.get("why", "")
        r["ago"] = ago(r["posted_at"], now)
        groups[tier].append(r)

    budget = cfg["report"]["max_jobs"]
    sections = []
    for k, title in TIERS:
        rows = groups[k][: max(0, budget)]
        budget -= len(rows)
        if rows:
            sections.append({"key": k, "title": title, "rows": rows})
    shown = sum(len(sec["rows"]) for sec in sections)
    cross = sum(1 for sec in sections for r in sec["rows"] if len(r["boards"]) > 1)
    date_str = now.astimezone(tz).strftime("%a %b %-d")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(ROOT / "report"),
        autoescape=jinja2.select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ctx = {
        "owner": cfg.get("owner", {}).get("name", ""),
        "date": date_str,
        "hours": data["window_hours"],
        "sections": sections,
        "shown": shown,
        "total": len(data["candidates"]),
        "cross": cross,
        "health": [
            {"label": label(k), **v} for k, v in data["health"].items()
        ],
        "scored": bool(scores),
    }
    html = env.get_template("email.html.j2").render(**ctx)
    text = env.get_template("email.txt.j2").render(**ctx)
    (run / "report.html").write_text(html)
    (run / "report.txt").write_text(text)
    subject = cfg["report"]["subject"].format(date=date_str, count=shown)
    (run / "subject.txt").write_text(subject)
    print(f"{subject}\n{shown} roles in {len(sections)} sections; html {len(html)} chars -> {run / 'report.html'}")


# ---------------------------------------------------------------- main


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "js", "merge", "render"])
    ap.add_argument("--config", default="config.local.yaml")
    ap.add_argument("--source")
    ap.add_argument("--run", help="run directory, e.g. runs/2026-10-22")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    {"plan": cmd_plan, "js": cmd_js, "merge": cmd_merge, "render": cmd_render}[args.command](cfg, args)


if __name__ == "__main__":
    main()
