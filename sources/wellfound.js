// Wellfound (formerly AngelList Talent) source. Run in a tab on
// https://wellfound.com/jobs while signed in to Wellfound.
// Reads the data embedded in Wellfound's role/location listing pages
// (/role/l/<role>/<location> and /role/r/<role> for remote).
// Listings are not sorted by date, so every page up to max_pages is read and
// each job's own go-live time is checked against the search window.
DJB.run(async () => {
  const { CFG } = DJB;
  const W = CFG.wellfound;
  const usOnly = (CFG.remote_countries || []).includes('US');

  const paths = [];
  for (const role of W.roles) {
    for (const loc of W.location_slugs || []) paths.push(`/role/l/${role}/${loc}`);
    if (CFG.include_remote) paths.push(`/role/r/${role}`);
  }

  for (const base of paths) {
    for (let page = 1; page <= W.max_pages; page++) {
      let data;
      try {
        const html = await (await DJB.get(base + (page > 1 ? `?page=${page}` : ''))).text();
        const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
        if (!m) throw new Error('no page data (signed out or blocked?)');
        data = JSON.parse(m[1]).props.pageProps.apolloState.data;
      } catch (e) {
        DJB.log(`${base} p${page}: ${e.message}`);
        break;
      }
      let count = 0;
      for (const startup of Object.values(data)) {
        if (startup.__typename !== 'StartupResult') continue;
        for (const ref of startup.highlightedJobListings || []) {
          const j = data[ref.__ref];
          if (!j) continue;
          count++;
          DJB.state.scanned++;
          const postedAt = j.liveStartAt ? new Date(j.liveStartAt * 1000).toISOString() : null;
          if (!DJB.recent(postedAt) || !DJB.titleOk(j.title)) continue;
          const remoteOk =
            !j.remote || !usOnly || !(j.acceptedRemoteLocationNames || []).length ||
            j.acceptedRemoteLocationNames.some((n) => /United States|US\b|Americas|Anywhere|Worldwide/i.test(n));
          if (base.startsWith('/role/r/') && !remoteOk) continue;
          DJB.add({
            id: j.id,
            title: j.title.trim(),
            company: startup.name,
            url: `https://wellfound.com/jobs/${j.id}-${j.slug}`,
            location: (j.locationNames || []).join(' / ') || null,
            workplace: j.remote ? 'Remote' : 'In office',
            posted_at: postedAt,
            salary: j.compensation || null,
            employment_type: j.jobType || null,
            yoe: j.yearsExperienceMin ? `${j.yearsExperienceMin}+ years` : null,
            company_size: startup.companySize ? startup.companySize.replace(/^SIZE_/, '').replace('_', '-').replace(/_PLUS$|_$/, '+') : null,
            summary: startup.highConcept || null,
          });
        }
      }
      if (!count) break;
    }
  }
});
