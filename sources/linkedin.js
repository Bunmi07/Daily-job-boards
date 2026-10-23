// LinkedIn source. Run in a tab on https://www.linkedin.com/ (any page).
// Uses LinkedIn's public "guest" job endpoints, the same ones the logged-out
// jobs page calls. They are undocumented and can change without notice.
//
// Step 1: search every keyword x location for postings in the last N hours.
// Step 2: open each matching posting's detail endpoint to read the signals the
//         search card leaves out: applicant count, seniority, employment type,
//         pay, and the years-of-experience line.
DJB.run(async () => {
  const { CFG, clean } = DJB;
  const L = CFG.linkedin;
  const hits = [];

  for (const s of L.searches) {
    for (const kw of s.keywords || CFG.keywords) {
      for (let page = 0; page < L.max_pages; page++) {
        const p = new URLSearchParams({
          keywords: kw,
          location: s.location,
          f_TPR: 'r' + Math.round((CFG.hours + (CFG.grace_hours || 0)) * 3600),
          sortBy: 'DD',
          start: String(page * 25),
        });
        if (s.geo_id) p.set('geoId', String(s.geo_id));
        if (s.distance) p.set('distance', String(s.distance));
        if (s.remote) p.set('f_WT', '2');
        let html;
        try {
          html = await (await DJB.get('/jobs-guest/jobs/api/seeMoreJobPostings/search?' + p)).text();
        } catch (e) {
          DJB.log(`search "${kw}" @ ${s.location}: ${e.message}`);
          break;
        }
        const cards = html.split('<li>').slice(1);
        if (!cards.length) break;
        for (const b of cards) {
          DJB.state.scanned++;
          const m = (re) => clean((b.match(re) || [])[1]);
          const id = (b.match(/jobPosting:(\d+)/) || [])[1];
          const title = m(/base-search-card__title[^>]*>([\s\S]*?)<\/h3>/);
          if (!id || !DJB.titleOk(title)) continue;
          const label = m(/<time[^>]*>([\s\S]*?)<\/time>/);
          hits.push({
            id,
            title,
            company: m(/base-search-card__subtitle[^>]*>([\s\S]*?)<\/h4>/),
            location: m(/job-search-card__location[^>]*>([\s\S]*?)<\/span>/),
            workplace: s.remote ? 'Remote' : null,
            posted_label: label,
            posted_at: DJB.relToIso(label),
            salary: m(/job-search-card__salary-info[^>]*>([\s\S]*?)<\/span>/),
            url: 'https://www.linkedin.com/jobs/view/' + id,
          });
        }
        if (cards.length < 10) break;
      }
    }
  }

  // De-duplicate across keyword/location searches, newest first.
  const byId = new Map();
  for (const h of hits) if (!byId.has(h.id)) byId.set(h.id, h);
  const jobs = [...byId.values()].sort((a, b) => (b.posted_at || '').localeCompare(a.posted_at || ''));

  let enriched = 0;
  for (const job of jobs) {
    if (enriched < L.enrich_limit) {
      try {
        const html = await (await DJB.get('/jobs-guest/jobs/api/jobPosting/' + job.id)).text();
        const text = clean(html);
        const pick = (re) => ((text.match(re) || [])[1] || '').trim();
        job.applicants =
          pick(/((?:Over )?\d[\d,]* applicants|Be among the first \d+ applicants)/i) || null;
        job.seniority = pick(/Seniority level\s+(.+?)\s+Employment type/);
        job.employment_type = pick(/Employment type\s+(Full-time|Part-time|Contract|Temporary|Internship|Volunteer|Other)/);
        const posted = pick(/(\d+\s+(?:minute|hour|day|week)s?\s+ago)/i);
        if (posted) {
          job.posted_label = posted;
          job.posted_at = DJB.relToIso(posted);
        }
        if (!job.salary) {
          job.salary =
            pick(/(\$\d[\d,.]*\s?[Kk]?(?:\/yr)?\s?(?:-|–|to)\s?\$\d[\d,.]*\s?[Kk]?(?:\/yr)?)/) || null;
        }
        job.yoe = pick(/(\d+\+?\s?(?:-|–|to)?\s?\d*\+?\s+years?[^.;]{0,70})/i).slice(0, 110) || null;
        if (L.snippet_chars) {
          const desc = clean((html.match(/show-more-less-html__markup[^>]*>([\s\S]*?)<\/div>/) || [])[1]);
          job.summary = desc.slice(0, L.snippet_chars) || null;
        }
        enriched++;
      } catch (e) {
        DJB.log(`detail ${job.id}: ${e.message}`);
      }
    }
    DJB.add(job);
  }
  DJB.log(`searched ${CFG.keywords.length} keywords x ${L.searches.length} locations, enriched ${enriched}`);
});
