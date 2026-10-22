// Built In source. Run in a tab on the Built In site set in the config
// (for example https://www.builtinnyc.com/jobs).
// Reads the server-rendered category listing pages filtered to recent jobs.
// Built In's own filter is "updated in the last day", so each card's age label
// ("5 Hours Ago", "Yesterday") is also checked against the search window.
DJB.run(async () => {
  const { CFG } = DJB;
  const B = CFG.builtin;
  const days = Math.max(1, Math.ceil(CFG.hours / 24));

  // Text pieces of a card, in reading order (DOMParser documents have no innerText).
  const leafText = (el) => {
    const out = [];
    const walk = el.ownerDocument.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) {
      const t = walk.currentNode.textContent.replace(/\s+/g, ' ').trim();
      if (t) out.push(t);
    }
    return out;
  };
  const short = (l) => l.length <= 60;

  for (const cat of B.categories) {
    for (let page = 1; page <= B.max_pages; page++) {
      const url = `/jobs/${cat}?daysSinceUpdated=${days}` + (page > 1 ? `&page=${page}` : '');
      let doc;
      try {
        const html = await (await DJB.get(url)).text();
        doc = new DOMParser().parseFromString(html, 'text/html');
      } catch (e) {
        DJB.log(`${cat} p${page}: ${e.message}`);
        break;
      }
      const cards = [...doc.querySelectorAll('[data-id="job-card"]')];
      if (!cards.length) break;
      for (const card of cards) {
        DJB.state.scanned++;
        const a = card.querySelector('a[data-id="job-card-title"]');
        const title = (a && a.textContent.trim()) || '';
        if (!DJB.titleOk(title)) continue;
        const href = a.getAttribute('href') || '';
        const id = (href.match(/(\d+)\/?$/) || [])[1] || href;
        const company = ((card.querySelector('[data-id="company-title"]') || {}).textContent || '').trim();
        const lines = leafText(card).filter(short);
        const age = lines.find((l) => /\bago\b|yesterday|today|just now/i.test(l)) || null;
        const postedAt = DJB.relToIso(age);
        if (!DJB.recent(postedAt)) continue;
        DJB.add({
          id,
          title,
          company,
          url: new URL(href, location.origin).href.split('?')[0],
          workplace: lines.find((l) => /^(Remote|Hybrid|In-Office)$/i.test(l)) || null,
          location: lines.find((l) => /,\s*[A-Z]{2}\b|USA|\d+ Locations/i.test(l) && l !== title) || null,
          salary: lines.find((l) => /\d+\s?K.*(Annually|Hourly)|\$\d/.test(l)) || null,
          posted_label: age,
          posted_at: postedAt,
        });
      }
    }
  }
});
