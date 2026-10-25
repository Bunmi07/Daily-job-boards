---
name: daily-job-board
description: Search LinkedIn, Built In, HiringCafe and Wellfound for jobs posted since the last run, merge roles listed on several boards, read each shortlisted job description, rank the roles against the person's profile, and email the report. Use for a daily or twice-daily job digest or when asked to run the job board.
---

# Daily job board

Runs one job search across several boards in the person's own Chrome, merges
the results, reads the full description of each shortlisted role, ranks them
against the profile in their config, and emails an HTML report. Every step is
driven by this file; the scripts do the mechanical parts so results are the
same every run.

Paths below are relative to this repository's root.

## What you need

- **Claude in Chrome** connected, with Chrome open and signed in to LinkedIn and
  Wellfound. Built In and HiringCafe work signed out.
- **A config file.** `config.local.yaml`, copied from `config.example.yaml`. A
  scheduled task may paste the config into its prompt instead; write it to
  `config.local.yaml` before step 1.
- **Gmail connected** to send the email. Without it, deliver `report.html`
  with SendUserFile instead and say email wasn't available.
- Python 3.10+ with `pyyaml` and `jinja2` (`pip install -r requirements.txt`).

## Run

Set `RUN=runs/$(TZ=America/New_York date +%F-%H%M)` (use the config's
`report.timezone`) and create `$RUN/raw/`. Each run gets its own folder, so two
runs on one day don't collide.

With `search.hours: auto`, the search window is the time since the previous
time in `search.schedule`, so a twice-daily schedule only reports roles posted
since the last email.

### 1. Plan

```
python scripts/djb.py plan --config config.local.yaml
```

Prints each enabled source and the page its tab must be on.

### 2. Open one tab per source

Get the tab context first. Then create one new tab per source and navigate it
to the printed page. Each script must run on its own board's site, because it
calls that site's own endpoints. Keep the tabs open until step 6 is done.

### 3. Start every source

For each source:

```
python scripts/djb.py js --config config.local.yaml --source <name> --out $RUN/<name>.js
```

Read `$RUN/<name>.js` and pass its full contents, unchanged, to the
JavaScript tool in that source's tab. It returns `started <name>` right away;
the work continues in the background. Start all sources before waiting on any.

### 4. Wait, export, collect

Check each tab with:

```js
window.__djb ? `${__djb.status} · ${__djb.jobs.length} jobs · ${__djb.scanned} scanned · ${__djb.requests} requests` : 'not started'
```

LinkedIn usually takes 1-3 minutes and HiringCafe 1-2. Re-check about every
30 seconds, and give up on a source after 6 minutes.

When a source shows `done` or `error`, run the contents of
`sources/export.js` in that tab, then read the tab's page text. Save
everything between `DJB_EXPORT_BEGIN` and `DJB_EXPORT_END` (markers included)
to `$RUN/raw/<name>.txt`. Copy the text exactly; don't retype or summarize it.

A source that errors or times out still gets exported so the report can show
it failed.

### 5. Merge

```
python scripts/djb.py merge --config config.local.yaml --run $RUN
```

This filters titles, location (including remote roles outside the US), pay,
years asked, employment type, skipped companies and roles already in the
pipeline. It also merges the same role found on several boards into one entry
that lists every board it was seen on. It writes `candidates.json` and
`candidates.md`.

### 6. Read the job descriptions

```
python scripts/djb.py details --config config.local.yaml --run $RUN
```

This picks the shortlist (up to `report.details_limit` roles, least crowded
and newest first; crowded roles are read too, just last) and writes one
`$RUN/details-<tab>.js` per tab that has roles to read. LinkedIn, Built In and
Wellfound descriptions are read in their own tabs. HiringCafe roles are read
from the hiring company's Greenhouse, Ashby or Lever page, from the HiringCafe
tab.

For each file, pass its full contents, unchanged, to the JavaScript tool in
the tab named in the file name. Check progress with the same status line as
step 4. When it shows `done`, read the tab's page text: everything between
`DJB_DETAILS_BEGIN` and `DJB_DETAILS_END` is one digest per role, headed
`## [key] title — company`, with how much was read, the years it asks for,
flags (degree, coding, people management, domains), a `where:` line (office
or hybrid wording quoted from the full posting, `says remote`, or `location
not stated`) and the opening plus the requirements section of the posting.

The last line before `DJB_DETAILS_END` is `DJB_READ key,key,...`: the roles
whose description was actually read. Save that whole line, from every details
tab, to `$RUN/read.txt` (one line per tab). **A role whose description wasn't
read is never sent**: render leaves out every key that isn't on a `DJB_READ`
line, and with no `read.txt` it sends no roles at all.

Read every digest before scoring. You don't need to save the digests
themselves. Close the tabs you created once all digests are read.

### 7. Score against the profile

Read the `profile` in the config, `$RUN/candidates.md` and the digests. Write
`$RUN/scores.json` mapping keys to a tier, a lane and a reason. Leave out any
key you would mark `skip`: missing keys are treated as skipped.

```json
{"a1b2c3d4": {"tier": "apply_first", "lane": "pm", "why": "Asks 4+ yrs PM shipping developer APIs; you shipped an SDK to hundreds of devs. Wants SQL."}}
```

`lane` is `pm` (product management), `tpm` (technical or product program
management) or `ops` (product operations). It shows as a badge in the email.

**Score from the posting, not the title.** For each role, compare what the
description requires with what the profile says the person has actually done:

1. **Function.** Is the job really product management, or product-facing
   program management? A "Product Manager" that is business analysis, project
   coordination, merchandising or marketing in disguise is `skip`.
2. **Level.** Compare the years and scope the posting requires with the
   profile. More than about one year above the person's experience, or
   lead / principal / staff / group / people-manager scope, is `skip`.
   Associate or entry-level is `skip` unless the profile asks for it.
3. **Hard requirements.** A required background the profile says the person
   lacks (for example "5+ years of healthcare product experience", "payments
   experience required", "former software engineer", deep infrastructure such
   as Kubernetes or GPUs, a security clearance) caps the role at `maybe`, and
   at `skip` when it's the core of the job. "Preferred" or "nice to have"
   gaps only lower it one tier.
4. **What the profile says no to.** Respect it (for example roles that read
   the person as an engineer, founding roles, a location).
   **Location: don't trust a "Remote" tag.** Boards, LinkedIn above all, tag
   hybrid and on-site roles as remote. Check the digest's `where:` line and
   the posting: if it asks for office time (hybrid, on-site, "N days a week",
   "must live in / relocate to") anywhere outside the profile's area, it's
   `skip`, whatever the board says. A role listed outside the area whose
   `where:` is `location not stated` can't be confirmed remote: `skip` it
   unless the board listed it as plain "United States" or the area itself.
5. **Pay.** Listed pay well under the profile's target lowers a tier.
6. **Freshness.** Roles with over 200 applicants are never `apply_first`;
   100-200 applicants needs an unusually strong match. Under 25 or under 50
   applicants is a reason to put a strong fit first, not to promote a weak one.

Tiers:

- `apply_first`: the posting's requirements clearly match the profile's real
  experience, the level is reachable, nothing above rules it out, and it isn't
  overcrowded. At most about 6 per run. When the profile ranks one lane above
  another (for example PM over TPM), prefer that lane among equal fits, but a
  strong fit in the second lane beats a weak fit in the first.
- `solid`: a reasonable fit with one clear stretch.
- `contract`: contract or temporary roles worth a look, whatever the fit.
- `maybe`: on target but thin, or capped by a gap in rule 3.
- `skip`: fails rule 1, 2 or 4, or is a staffing-agency copy of a role
  already listed.

Score only roles whose description you read. A role whose digest says
`DESCRIPTION NOT READ`, or that wasn't on the shortlist, is left out of
`scores.json` entirely: never score from a title, pay or board label alone.

Write each `why` in plain words, up to about 25. Quote or closely paraphrase
one concrete requirement from the posting and say how the profile meets it or
where the gap is. Use only the posting and the profile: don't add facts about
the company from your own knowledge, and don't invent experience. Base the
tier on the fit, not the board: being on several boards is shown separately
and doesn't raise a tier by itself.

### 8. Render

**Report history.** Runs start from a fresh clone, so the list of what
earlier reports sent lives in the claude.ai Project attached to the session,
as the doc `claude/job-board-history.json`. Before rendering, read it with the
Projects tool (`project_read`) and save its contents to `$RUN/history.json`;
if it doesn't exist yet, or the session has no Project, write `[]` there.

```
python scripts/djb.py render --config config.local.yaml --run $RUN --history $RUN/history.json
```

This writes `report.html`, `report.txt` and `subject.txt`. Within each tier,
the least crowded roles come first (by LinkedIn applicant count), then the
newest. Only roles on a `DJB_READ` line are included.

A company whose roles made at least two earlier reports in the last 14 days
is flagged "keeps posting", with a box at the top of the email listing its
roles from today and before. Large employers often cap applications or make
you wait after a rejection, so the box helps pick the single best fit there.

Render also adds this run's roles to `$RUN/history.json`. After sending (step
9), write that file back with `project_write` to `claude/job-board-history.json`
(`local_path` = `$RUN/history.json`). Skip this when the session has no
Project; the flag then just won't appear.

### 9. Send

Send with Gmail to `owner.email` from the config:

- subject: the contents of `subject.txt`
- `htmlBody`: the contents of `report.html`
- `body`: the contents of `report.txt`

Then reply with one line: how many roles were sent, how many were apply-first,
and any board that failed.

## When something breaks

- **A source returns 0 jobs and logs HTTP 4xx/5xx or "no page data".** The
  site changed or blocked the request. Send the report anyway; its "Board
  checks" footer shows the failure. Don't work around a block or a CAPTCHA.
- **Many digests say DESCRIPTION NOT READ.** The board changed its page
  layout, or the ATS link isn't Greenhouse, Ashby or Lever. Those roles are
  left out; send the report anyway (its footer counts what was left out).
- **LinkedIn shows no applicant counts.** The detail endpoint changed. The
  report still works without them.
- **HiringCafe fails with "buildId".** Make sure the tab is on
  `https://hiringcafe.com/classic`. The script reads a fresh buildId from the
  page each run.
- **The JavaScript tool times out.** A script was pasted without `DJB.run(...)`
  at the end, or the tab is frozen. Reload the tab and start that source again.

To add a board, see `sources/README.md`.
