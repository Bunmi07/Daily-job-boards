// Reads the full job description for each shortlisted role and writes a short
// digest onto the page, so Claude can score roles on what the posting actually
// asks for instead of the title alone.
//
// Built by `djb.py details`, which puts the shortlist in CFG.items:
//   [{key, src, id, url, title, company}]
// Same-origin pages (LinkedIn, Built In, Wellfound) are read from the tab they
// belong to. Greenhouse, Ashby and Lever postings are read from their public
// job-board APIs, which allow cross-origin reads, so they work from any tab.
// Anything else falls back to the board's own summary.
DJB.run(async () => {
  const { CFG, clean } = DJB;
  const D = CFG.details;
  const ashbyBoards = new Map();
  // Cross-origin APIs allow anonymous reads only; sending cookies makes the browser block them.
  const xget = (url) => DJB.get(url, { credentials: 'omit' });

  const ldJob = (html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    for (const s of doc.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const o = JSON.parse(s.textContent);
        const list = [].concat(o['@graph'] || o);
        const jp = list.find((x) => x && x['@type'] === 'JobPosting');
        if (jp) return jp;
      } catch (e) {
        /* not JSON */
      }
    }
    return null;
  };

  const readers = {
    async linkedin(it) {
      const html = await (await DJB.get('/jobs-guest/jobs/api/jobPosting/' + it.id)).text();
      const body = (html.match(/show-more-less-html__markup[^>]*>([\s\S]*?)<\/div>/) || [])[1];
      const crit = [...html.matchAll(/description__job-criteria-text[^>]*>([\s\S]*?)</g)].map((m) => clean(m[1]));
      const applicants = (clean(html).match(/((?:Over )?\d[\d,]* applicants|Be among the first \d+ applicants)/i) || [])[1];
      return { text: body, level: crit[0] && crit[0] !== 'Not Applicable' ? crit[0] : null, applicants };
    },
    async builtin(it) {
      const html = await (await DJB.get(new URL(it.url).pathname)).text();
      const jp = ldJob(html);
      return jp ? { text: jp.description, posted: jp.datePosted } : null;
    },
    async wellfound(it) {
      const html = await (await DJB.get(new URL(it.url).pathname)).text();
      const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
      if (!m) return null;
      const data = JSON.parse(m[1]).props.pageProps.apolloState.data;
      const j = data['JobListing:' + it.id];
      return j ? { text: j.descriptionHtml || j.description } : null;
    },
    async ats(it) {
      const u = new URL(it.url);
      let m;
      if (/greenhouse\.io$/.test(u.hostname) && (m = u.pathname.match(/^\/([^/]+)\/jobs\/(\d+)/))) {
        const j = await (await xget(`https://boards-api.greenhouse.io/v1/boards/${m[1]}/jobs/${m[2]}`)).json();
        const tmp = document.createElement('textarea');
        tmp.innerHTML = j.content || '';
        return { text: tmp.value };
      }
      if (u.searchParams.get('gh_jid')) {
        // Company-hosted Greenhouse page: the board token is usually the company slug.
        const token = (it.board_token || '').trim();
        if (token) {
          const j = await (await xget(`https://boards-api.greenhouse.io/v1/boards/${token}/jobs/${u.searchParams.get('gh_jid')}`)).json();
          const tmp = document.createElement('textarea');
          tmp.innerHTML = j.content || '';
          return { text: tmp.value };
        }
      }
      if (u.hostname === 'jobs.ashbyhq.com' && (m = u.pathname.match(/^\/([^/]+)\/([0-9a-f-]{36})/))) {
        if (!ashbyBoards.has(m[1])) {
          const b = await (await xget(`https://api.ashbyhq.com/posting-api/job-board/${m[1]}?includeCompensation=true`)).json();
          ashbyBoards.set(m[1], b.jobs || []);
        }
        const j = ashbyBoards.get(m[1]).find((x) => x.id === m[2]);
        return j ? { text: j.descriptionPlain || j.descriptionHtml } : null;
      }
      if (u.hostname === 'jobs.lever.co' && (m = u.pathname.match(/^\/([^/]+)\/([0-9a-f-]{36})/))) {
        const j = await (await xget(`https://api.lever.co/v0/postings/${m[1]}/${m[2]}`)).json();
        const lists = (j.lists || []).map((l) => `${l.text}: ${l.content}`).join(' ');
        return { text: [j.descriptionPlain, lists, j.additionalPlain].join(' ') };
      }
      return null;
    },
  };

  // Keep the opening (what the role is) and the requirements section (what
  // they ask for), within D.chars characters. The requirements section is the
  // first heading-like match followed by talk of years or experience.
  const REQ = /(qualifications|requirements|what you(?:'|’)?ll (?:need|bring)|what you bring|what we(?:'|’)?re looking for|you (?:have|bring|might be a fit)|about you|who you are|must[- ]haves?|you should have|skills (?:and|&) experience)/gi;
  const digest = (raw) => {
    const t = clean(raw);
    if (!t) return '';
    const head = t.slice(0, D.head_chars);
    const body = t.slice(D.head_chars);
    const hits = [...body.matchAll(REQ)];
    const near = (m, n) => /years|experience/i.test(body.slice(m.index, m.index + n));
    // Prefer a capitalised heading ("Requirements", "What You'll Bring") over the word mid-sentence.
    let hit = hits.find((m) => /^[A-Z]/.test(m[0]) && near(m, 250)) || hits.find((m) => near(m, 120));
    let at = hit ? hit.index : -1;
    if (at < 0) {
      const y = body.search(/\d+\+?\s*(?:-|–|to)?\s*\d*\+?\s+years/i);
      at = y >= 0 ? Math.max(0, y - 150) : 0;
    }
    // A match near the very end is usually boilerplate ("if you have the experience, apply").
    if (body.length - at < 500) at = 0;
    return (head + (at > 0 ? ' … ' : ' ') + body.slice(at)).slice(0, D.chars);
  };
  const FLAGS = [
    ['cs/eng degree', /(computer science|engineering)\s+degree|degree in (computer science|engineering)|B\.?S\.? in (computer science|engineering)/i],
    ['hands-on coding', /(write|writing) (production )?code|hands[- ]on (coding|engineering|development)|software engineering experience|former (software )?engineer/i],
    ['people manager', /direct reports|manage a team of|people management|managing (a team of )?(product managers|pms)/i],
    ['startup-only', /(early[- ]stage|seed|series a) (startup )?experience (is )?required|must have (startup|founding) experience/i],
    ['sql', /\bSQL\b/],
    ['payments', /\bpayments?\b/i],
    ['healthcare', /health ?care|clinical|payer|provider|patient/i],
    ['AI/LLM', /\b(LLM|generative AI|GenAI|AI agents?|machine learning)\b/i],
    ['developer platform', /developer (experience|platform|tools?|tooling)|SDKs?\b|APIs? (platform|products?)/i],
  ];

  // Where the job really is. Boards (LinkedIn especially) tag hybrid and on-site roles as
  // remote, so this reads the whole posting, not the digest, and quotes what it found.
  const OFFICE = [
    /\bhybrid\b/i,
    /\b(?:on[- ]?site|in[- ]office|in the office|in[- ]person)\b/i,
    /\b\d\s*(?:\+\s*)?(?:days?|x)\s*(?:a|per|\/|each)?\s*week\b/i,
    /\bmust (?:be )?(?:locate[d]?|live|reside|be based|based|relocate)\b/i,
    /\b(?:relocat\w+|commut\w+ distance|local candidates)\b/i,
  ];
  const where = (t) => {
    const found = [];
    let end = -1;
    for (const re of OFFICE) {
      const m = t.match(re);
      // Skip a match already inside the previous quote.
      if (!m || found.length >= 2 || (m.index >= end - 70 && m.index < end)) continue;
      found.push('"…' + t.slice(Math.max(0, m.index - 60), m.index + 70).trim() + '…"');
      end = m.index + 70;
    }
    if (found.length) return 'office: ' + found.join(' ');
    return /\bremote\b/i.test(t) ? 'says remote' : 'location not stated';
  };

  for (const it of D.items) {
    DJB.state.scanned++;
    const reader = readers[it.src] && it.src !== 'hiringcafe' ? readers[it.src] : readers.ats;
    let r = null;
    try {
      r = await reader(it);
    } catch (e) {
      DJB.log(`${it.key}: ${e.message}`);
    }
    const full = clean(r && r.text);
    // Flags come from the kept text (role + requirements), not benefits boilerplate.
    const kept = full ? digest(full) : '';
    const years = [...new Set((full.match(/\d+\+?\s?(?:-|–|to)?\s?\d*\+?\s+years?/gi) || []).map((s) => s.replace(/\s+/g, ' ')))].slice(0, 4);
    DJB.add({
      id: it.key,
      title: it.title,
      company: it.company,
      ok: Boolean(full),
      chars: full.length,
      level: r && r.level,
      applicants: r && r.applicants,
      posted: r && r.posted,
      years: years.join('; '),
      flags: FLAGS.filter(([, re]) => re.test(kept)).map(([n]) => n).join(', '),
      where: full ? where(full) : null,
      text: kept,
    });
  }

  // Write the digests onto the page for one page-text read.
  const lines = DJB.state.jobs.map((j) =>
    [
      `## [${j.id}] ${j.title} — ${j.company}`,
      [j.ok ? `read ${j.chars} chars` : 'DESCRIPTION NOT READ', j.level && `level: ${j.level}`, j.applicants, j.posted && `posted ${j.posted}`, j.years && `years: ${j.years}`, j.flags && `flags: ${j.flags}`]
        .filter(Boolean)
        .join(' | '),
      j.where && `where: ${j.where}`,
      j.text,
    ].filter(Boolean).join('\n')
  );
  const pre = document.createElement('pre');
  pre.style.whiteSpace = 'pre-wrap';
  // One short line listing the roles whose description was actually read. It is saved
  // to $RUN/read.txt, and render leaves out every role not on it.
  const read = DJB.state.jobs.filter((j) => j.ok).map((j) => j.id);
  pre.textContent = `DJB_DETAILS_BEGIN ${CFG.source}\n\n${lines.join('\n\n')}\n\nDJB_READ ${read.join(',')}\nDJB_DETAILS_END`;
  document.title = 'daily-job-board details';
  document.body.replaceChildren(pre);
});
