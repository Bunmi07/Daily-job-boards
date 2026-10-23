# daily-job-board

A daily job digest that Claude runs for you. Each run it:

1. Searches **LinkedIn, Built In, HiringCafe and Wellfound** for roles posted
   since the last run (once or twice a day), from your own Chrome.
2. Filters them by your titles, location, pay, years of experience, and the
   companies you've already applied to.
3. Merges the same role found on several boards into one entry, labeled
   **On N boards**, with a link to each. It also shows LinkedIn's posting time
   and applicant count.
4. Reads the full job description of each shortlisted role, then ranks the
   roles against a profile you write, sorting them into
   **Apply first**, **Solid fits**, **Contract** and **Worth a look**, each
   with a one-line reason.
5. Emails you the report.

It's built for any kind of job search: the role, location and profile all live
in one config file.

## How it works

```
 Claude (cloud)                         Your Chrome (Claude in Chrome extension)
 ──────────────                         ─────────────────────────────────────────
 djb.py plan / js  ── script per board ─▶  linkedin.com tab   ─┐
                                           builtinnyc.com tab  ├─ each script calls its own
                                           hiringcafe.com tab  │  site's listing endpoints
                                           wellfound.com tab  ─┘  and filters in the page
 raw/<board>.txt   ◀── page text export ──  export.js
 djb.py merge      → candidates.md
 Claude scores     → scores.json            (fit against your profile)
 djb.py render     → report.html  ──▶  Gmail
```

The board scripts run in your browser because these sites don't offer public
APIs, and some need you to be signed in. Everything after the export (merging,
ranking and the email) runs in Claude's workspace.

## What you need

- A Claude plan with **Claude in Chrome**, plus **Gmail** connected in Claude
  (for the email).
- Chrome open and signed in to **LinkedIn** and **Wellfound**.
- For a daily run: a **scheduled task** in Claude, and a computer that's awake
  at that time. See [docs/setup.md](docs/setup.md).

## Quick start

1. Clone this repo, or give Claude its URL.
2. Copy `config.example.yaml` to `config.local.yaml` and fill it in. The
   `profile` paragraph matters most, because it drives the ranking.
3. Ask Claude: *"Run the daily-job-board skill in this repo with my
   config.local.yaml."* Claude follows [SKILL.md](SKILL.md) step by step.
4. Once a manual run looks right, schedule it. [docs/setup.md](docs/setup.md)
   has a ready-to-paste prompt for the scheduled task.

To check the merge and report code without a browser:

```
pip install -r requirements.txt
python -m unittest discover tests
```

## Configuration

See [config.example.yaml](config.example.yaml); every field is commented.
The main ones:

| Field | What it does |
|---|---|
| `profile` | Plain-English summary of you and what you want. Claude ranks against it. |
| `search.keywords` | What gets typed into each board's search. A source can override it. |
| `search.title_include` / `title_exclude` | Whole-word title filters. Prefix `re:` for a regex. |
| `search.locations[].match` | How a posting's location must read to count as local. |
| `search.include_remote`, `remote_countries` | Also keep remote roles open to these countries. |
| `search.max_required_years` | Drop roles asking for more years than this. |
| `search.flag_salary_below` | Keep, but label, roles whose listed pay is below this. |
| `pipeline` | Roles you've applied to. The same role is dropped; other roles there are labeled. |
| `sources.*` | Turn boards on or off; set Built In's city site and categories, and Wellfound's role and location slugs. |

## Adding a job board

Each board is one script in `sources/` plus one entry in
`scripts/sources.py`. See [sources/README.md](sources/README.md).

## Limits and good manners

- **These are unofficial endpoints.** Each board script reads the same data the
  site's own pages load, and any of them can change without notice. When a
  board breaks, the email still goes out, and its "Board checks" footer says
  which board failed.
- **Check each site's terms.** Automated access may be against some sites'
  terms of service. This tool makes a modest number of requests once a day from
  your own signed-in browser, with a delay between requests. It doesn't get
  around logins, CAPTCHAs or rate limits, and it shouldn't be changed to.
- **Your data stays local.** `config.local.yaml` and `runs/` are in
  `.gitignore`. Only the example config is meant to be committed.

## License

MIT
