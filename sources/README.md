# Board scripts

Each file here is a small script that runs inside a browser tab that's already
on that board's website. Running there means its `fetch()` calls are
same-origin and use the person's own sign-in.

`scripts/djb.py js --source <name>` builds the script that actually gets
pasted into the tab, in this order:

1. `window.__DJB_CFG = {...}`: settings from the user's config.
2. `_common.js`: shared helpers (`DJB.*`).
3. `<name>.js`: the board itself.

After the board shows `done`, `export.js` writes the results onto the page as
JSON so they can be read in one page-text read.

`details.js` is the second pass: `djb.py details` puts the shortlist into it,
and it reads each role's full description (same-origin on LinkedIn, Built In
and Wellfound; through the public Greenhouse, Ashby and Lever APIs for
HiringCafe roles) and writes a short digest onto the page. To support a new
board there, add a reader to `readers` in `details.js` and the board to
`DETAIL_TABS` in `djb.py`.

## Contract

A board script must:

- End with `DJB.run(async () => { ... })`. This starts the work in the
  background and returns at once, because browser tool calls time out after
  about 45 seconds.
- Use `DJB.get(url)` for requests. It adds the configured delay, counts
  requests, and throws on HTTP errors.
- Increase `DJB.state.scanned` for every posting it looks at.
- Skip postings that fail `DJB.titleOk(title)` or `DJB.recent(isoTime)`.
- Call `DJB.add(job)` for every posting it keeps:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Unique on that board |
| `title`, `company` | yes | |
| `url` | yes | Link to the posting; drop tracking query strings when the link still works without them |
| `posted_at` | strongly preferred | ISO time; `DJB.relToIso("5 hours ago")` helps |
| `posted_label` | no | The board's own wording ("Yesterday") |
| `location`, `workplace` | no | `workplace`: Remote / Hybrid / On-site |
| `salary` | no | Any text; merge normalizes it |
| `employment_type`, `yoe`, `applicants`, `company_size`, `summary` | no | `yoe` should start with the number of years ("5+ years ...") |

- Use `DJB.log(msg)` for problems instead of throwing, so one bad page doesn't
  sink the whole board.

## Adding a board

1. Write `sources/<name>.js` following the contract.
2. Add an entry to `SOURCES` in `scripts/sources.py` with a label, the start
   page the tab must be on, and a function that turns the user's config into
   the script's settings. Add it to `PRIORITY` too. Boards earlier in that list
   supply the headline fields when a role appears on several boards.
3. Add a `sources.<name>` block to `config.example.yaml`.
4. Do a run and check the board's line in the email's "Board checks" footer.

Keep scripts polite: no parallel request floods, no getting around logins or
CAPTCHAs, and a page limit that matches what a person would read.
