// Run after a source reports status "done". Replaces the tab's page with the
// collected results as plain JSON so the whole batch can be read in one go with
// a page-text read (tool results for scripts are truncated; page text is not).
// Fields the merge step can rebuild are dropped to keep the export short.
(() => {
  const s = window.__djb;
  if (!s) return 'nothing to export: no source has run in this tab';
  const jobs = s.jobs.map((j) => {
    const o = Object.assign({}, j);
    delete o.src;
    if (o.url === 'https://www.linkedin.com/jobs/view/' + o.id) delete o.url;
    if (o.seniority === 'Not Applicable') delete o.seniority;
    if (o.posted_at) o.posted_at = o.posted_at.slice(0, 16) + 'Z';
    return o;
  });
  const json = JSON.stringify({
    source: s.source,
    status: s.status,
    started: s.started,
    finished: s.finished,
    requests: s.requests,
    scanned: s.scanned,
    over_years: s.over_years || 0,
    log: s.log.slice(0, 25),
    jobs,
  });
  const pre = document.createElement('pre');
  pre.textContent = 'DJB_EXPORT_BEGIN' + json + 'DJB_EXPORT_END';
  const main = document.createElement('main');
  main.appendChild(pre);
  document.title = 'daily-job-board export';
  if (!document.body) document.documentElement.appendChild(document.createElement('body'));
  document.body.replaceChildren(main);
  return `exported ${jobs.length} jobs (${json.length} chars) from ${s.source}`;
})();
