---
name: daily-job-board
description: Search LinkedIn, Built In, HiringCafe and Wellfound for jobs posted in the last day, merge roles listed on several boards, rank them against the person's profile, and email the report. Use for a daily job digest or when asked to run the job board.
---

# Daily job board

Runs one job search across several boards in the person's own Chrome, merges
the results, ranks them against the profile in their config, and emails an
HTML report. Every step is driven by this file; the scripts do the mechanical
parts so results are the same every day.

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

Set `RUN=runs/$(date +%F)` and create `$RUN/raw/`.

### 1. Plan

```
python scripts/djb.py plan --config config.local.yaml
```

Prints each enabled source and the page its tab must be on.

### 2. Open one tab per source

Get the tab context first. Then create one new tab per source and navigate it
to the printed page. Each script must run on its own board's site, because it
calls that site's own endpoints.

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
it failed. Close the tabs you created when all exports are saved.

### 5. Merge

```
python scripts/djb.py merge --config config.local.yaml --run $RUN
```

This filters titles, location, pay, employment type, skipped companies and
roles already in the pipeline. It also merges the same role found on several
boards into one entry that lists every board it was seen on. It writes
`candidates.json` and `candidates.md`.

### 6. Score against the profile

Read the `profile` in the config and `$RUN/candidates.md`. Write
`$RUN/scores.json` mapping keys to a tier and a reason. Leave out any key you
would mark `skip`: missing keys are treated as skipped, which keeps the file
short.

```json
{"a1b2c3d4": {"tier": "apply_first", "why": "AI agent platform PM at a fintech; matches the compliance-agent work. Asks 5+ yrs."}}
```

Tiers:

- `apply_first`: the domain or skills clearly match the profile, the level is
  reachable (required years no more than about one above theirs), and nothing
  in the profile rules it out. Keep this to about 8 or fewer.
- `solid`: a reasonable fit with one clear stretch, such as a domain gap, a
  higher level, or below-target pay.
- `contract`: contract or temporary roles worth a look. Use this whatever the
  fit, so contracts are easy to find.
- `maybe`: on target but thin, such as a vague posting or an unknown company.
- `skip`: wrong function, wrong level, a staffing-agency copy of a role that's
  already listed, or something the profile says no to. Skipped roles are left
  out of the email.

Write each `why` in plain words, up to about 20, and tie it to something in
the profile. Name the main gap when there is one. Use only what the candidate
line shows; don't invent details about the company or role. Base the tier on
the profile, not the board: being on several boards is shown separately and
doesn't raise a tier by itself.

### 7. Render

```
python scripts/djb.py render --config config.local.yaml --run $RUN
```

This writes `report.html`, `report.txt` and `subject.txt`.

### 8. Send

Send with Gmail to `owner.email` from the config:

- subject: the contents of `subject.txt`
- `htmlBody`: the contents of `report.html`
- `body`: the contents of `report.txt`

Then reply with one line: how many roles were sent, how many were on several
boards, and any board that failed.

## When something breaks

- **A source returns 0 jobs and logs HTTP 4xx/5xx or "no page data".** The
  site changed or blocked the request. Send the report anyway; its "Board
  checks" footer shows the failure. Don't work around a block or a CAPTCHA.
- **LinkedIn shows no applicant counts.** The detail endpoint changed. The
  report still works without them.
- **HiringCafe fails with "buildId".** Make sure the tab is on
  `https://hiringcafe.com/classic`. The script reads a fresh buildId from the
  page each run.
- **The JavaScript tool times out.** A script was pasted without `DJB.run(...)`
  at the end, or the tab is frozen. Reload the tab and start that source again.

To add a board, see `sources/README.md`.
