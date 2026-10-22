// Shared helpers. scripts/build_js.py puts this file (and the config) ahead of
// every source script, so each source can call DJB.* without redefining it.
//
// Contract for a source script:
//   - It runs inside a browser tab that is already on the source's own site
//     (so fetch() calls are same-origin and use the person's own sign-in).
//   - It ends with `DJB.run(async () => { ... })`, which starts the work in the
//     background and returns immediately (browser tools time out after ~45s).
//   - It calls DJB.add(job) for every posting that passes the filters.
//   - Progress lives in window.__djb: { status: running|done|error, jobs, log }.
window.DJB = (function () {
  const CFG = window.__DJB_CFG;
  const state = (window.__djb = {
    source: CFG.source,
    status: 'running',
    started: new Date().toISOString(),
    finished: null,
    requests: 0,
    scanned: 0,
    jobs: [],
    log: [],
  });
  const include = CFG.title_include ? new RegExp(CFG.title_include, 'i') : null;
  const exclude = CFG.title_exclude ? new RegExp(CFG.title_exclude, 'i') : null;
  const cutoffMs = Date.now() - (CFG.hours + (CFG.grace_hours || 0)) * 3600e3;
  const seenIds = new Set();

  const UNIT_MS = { minute: 60e3, hour: 3600e3, day: 86400e3, week: 604800e3, month: 2592e6 };

  return {
    CFG,
    state,
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),

    // Strip tags and entities from an HTML fragment and collapse whitespace.
    clean(s) {
      return (s || '')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/&#39;|&#x27;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&nbsp;/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    },

    titleOk(title) {
      if (!title) return false;
      if (include && !include.test(title)) return false;
      if (exclude && exclude.test(title)) return false;
      return true;
    },

    // True when the timestamp is inside the search window (unknown counts as recent).
    recent(iso) {
      if (!iso) return true;
      const t = Date.parse(iso);
      return isNaN(t) || t >= cutoffMs;
    },

    // "5 hours ago", "Yesterday", "Reposted 3 Hours Ago", "Just now" -> ISO string or null.
    relToIso(label) {
      if (!label) return null;
      const s = String(label).toLowerCase();
      if (/just now|moments? ago|today/.test(s)) return new Date().toISOString();
      if (/yesterday/.test(s)) return new Date(Date.now() - 86400e3).toISOString();
      const m = s.match(/(\d+)\+?\s*(minute|min|hour|hr|day|week|month)s?/);
      if (!m) return null;
      const unit = { min: 'minute', hr: 'hour' }[m[2]] || m[2];
      return new Date(Date.now() - Number(m[1]) * UNIT_MS[unit]).toISOString();
    },

    async get(url, opts) {
      state.requests++;
      if (CFG.delay_ms) await new Promise((r) => setTimeout(r, CFG.delay_ms));
      const res = await fetch(url, Object.assign({ credentials: 'include' }, opts || {}));
      if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
      return res;
    },

    // Fields: id, title, company, url (required); location, workplace, posted_at,
    // posted_label, salary, applicants, employment_type, yoe, summary (optional).
    add(job) {
      if (!job || !job.id || seenIds.has(String(job.id))) return false;
      seenIds.add(String(job.id));
      // Drop postings that ask for more years than the config allows.
      const years = parseInt(String(job.yoe || '').match(/\d+/), 10);
      if (CFG.max_required_years && years > CFG.max_required_years && years < 40) {
        state.over_years = (state.over_years || 0) + 1;
        return false;
      }
      const out = { src: CFG.source };
      for (const [k, v] of Object.entries(job)) {
        if (v !== null && v !== undefined && v !== '') out[k] = v;
      }
      state.jobs.push(out);
      return true;
    },

    log(msg) {
      state.log.push(String(msg).slice(0, 300));
    },

    run(fn) {
      (async () => {
        try {
          await fn();
          state.status = 'done';
        } catch (e) {
          state.status = 'error';
          state.log.push(String((e && e.message) || e).slice(0, 300));
        }
        state.finished = new Date().toISOString();
      })();
      return `started ${CFG.source}`;
    },
  };
})();
