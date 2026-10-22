// HiringCafe source. Run in a tab on https://hiringcafe.com/classic
// Reads the JSON that the classic search page loads for itself
// (/_next/data/<buildId>/classic.json). The buildId changes whenever
// HiringCafe deploys, so it is read fresh from the page on every run.
//
// HiringCafe's "date posted" filter is unreliable when signed out, so this
// sorts by date and checks each posting's own publish date instead.
DJB.run(async () => {
  const { CFG } = DJB;
  const H = CFG.hiringcafe;
  const locRes = (CFG.location_match || []).map((s) => new RegExp(s, 'i'));
  const remoteCountries = new Set(CFG.remote_countries || []);

  let buildId = window.__NEXT_DATA__ && window.__NEXT_DATA__.buildId;
  if (!buildId) {
    const html = await (await DJB.get('/classic')).text();
    buildId = (html.match(/"buildId":"([^"]+)"/) || [])[1];
  }
  if (!buildId) throw new Error('could not find HiringCafe buildId; open https://hiringcafe.com/classic first');

  const locationOk = (v) => {
    const where = [v.formatted_workplace_location, ...(v.workplace_cities || []), ...(v.workplace_states || [])].join(' | ');
    if (locRes.some((re) => re.test(where))) return true;
    if (CFG.include_remote && v.workplace_type === 'Remote') {
      const countries = v.workplace_countries || [];
      return !remoteCountries.size || countries.some((c) => remoteCountries.has(c));
    }
    return false;
  };

  const money = (n) => (n ? '$' + Math.round(n / 1000) + 'K' : '');

  for (const kw of CFG.keywords) {
    for (let page = 0; page < H.max_pages; page++) {
      const searchState = Object.assign(
        { searchQuery: kw, dateFetchedPastNDays: Math.max(1, Math.ceil(CFG.hours / 24)), sortBy: 'date' },
        H.search_state || {}
      );
      const url = `/_next/data/${buildId}/classic.json?searchState=${encodeURIComponent(JSON.stringify(searchState))}&page=${page}`;
      let hits;
      try {
        hits = ((await (await DJB.get(url)).json()).pageProps || {}).ssrHits || [];
      } catch (e) {
        DJB.log(`"${kw}" p${page}: ${e.message}`);
        break;
      }
      if (!hits.length) break;
      let anyRecent = false;
      for (const h of hits) {
        DJB.state.scanned++;
        const v = h.v5_processed_job_data || {};
        const ji = h.job_information || {};
        const postedAt = v.estimated_publish_date || null;
        if (!DJB.recent(postedAt)) continue;
        anyRecent = true;
        const title = ji.title || ji.job_title_raw || '';
        if (!DJB.titleOk(title) || !locationOk(v)) continue;
        const lo = v.yearly_min_compensation, hi = v.yearly_max_compensation;
        DJB.add({
          id: h.objectID || h.id,
          title,
          company: v.company_name || (h.enriched_company_data || {}).name || '',
          url: h.apply_url,
          location: v.formatted_workplace_location || null,
          workplace: v.workplace_type || null,
          posted_at: postedAt,
          salary: lo || hi ? [money(lo), money(hi)].filter(Boolean).join(' - ') : null,
          employment_type: Array.isArray(v.commitment) ? v.commitment.join(', ') : v.commitment || null,
          yoe: v.min_industry_and_role_yoe ? `${v.min_industry_and_role_yoe}+ years` : null,
          summary: (v.requirements_summary || '').slice(0, CFG.snippet_chars || 250) || null,
        });
      }
      // Results are only roughly date-sorted; stop once a whole page is old.
      if (!anyRecent) break;
    }
  }
});
