/**
 * Detección de ATS y fetch JSON para scan.mjs / scan-list.mjs.
 * APIs públicas de vacantes (sin key): Greenhouse, Ashby, Lever (US+EU),
 * Recruitee (/api/offers), Workable (widget accounts).
 */

export const FETCH_TIMEOUT_MS = 15_000;

export function detectApi(company) {
  if (company.api && company.api.includes('greenhouse')) {
    return { type: 'greenhouse', url: company.api };
  }
  if (company.api && /recruitee\.com\/api\/offers/i.test(company.api)) {
    return { type: 'recruitee', url: company.api.trim() };
  }
  if (
    company.api &&
    /apply\.workable\.com\/api\/v1\/widget\/accounts\//i.test(company.api)
  ) {
    return { type: 'workable', url: company.api.trim() };
  }

  const url = company.careers_url || '';

  const ashbyMatch = url.match(/jobs\.ashbyhq\.com\/([^/?#]+)/);
  if (ashbyMatch) {
    return {
      type: 'ashby',
      url: `https://api.ashbyhq.com/posting-api/job-board/${ashbyMatch[1]}?includeCompensation=true`,
    };
  }

  const leverMatch = url.match(/jobs\.lever\.co\/([^/?#]+)/);
  if (leverMatch) {
    return {
      type: 'lever',
      url: `https://api.lever.co/v0/postings/${leverMatch[1]}`,
    };
  }

  // Recruitee: https://{client}.recruitee.com/... → GET .../api/offers
  const recruiteeMatch = url.match(
    /https?:\/\/([a-z0-9-]+)\.recruitee\.com/i
  );
  if (recruiteeMatch) {
    const sub = recruiteeMatch[1].toLowerCase();
    if (!['www', 'cdn', 'support', 'status', 'help'].includes(sub)) {
      return {
        type: 'recruitee',
        url: `https://${recruiteeMatch[1]}.recruitee.com/api/offers`,
      };
    }
  }

  // Workable: https://apply.workable.com/{account}/ → widget JSON
  const workableMatch = url.match(
    /apply\.workable\.com\/([a-z0-9-]+)\/?(?:$|[?#])/i
  );
  if (workableMatch) {
    const acct = workableMatch[1].toLowerCase();
    if (acct !== 'j' && acct !== 'api' && acct !== 'careers') {
      return {
        type: 'workable',
        url: `https://apply.workable.com/api/v1/widget/accounts/${workableMatch[1]}`,
      };
    }
  }

  const ghEuMatch = url.match(/job-boards(?:\.eu)?\.greenhouse\.io\/([^/?#]+)/);
  if (ghEuMatch && !company.api) {
    return {
      type: 'greenhouse',
      url: `https://boards-api.greenhouse.io/v1/boards/${ghEuMatch[1]}/jobs`,
    };
  }

  // Host exacto boards.greenhouse.io (no confundir con job-boards.greenhouse.io)
  const boardsPath = url.match(/https?:\/\/boards\.greenhouse\.io\/([^/?#]+)/i);
  if (boardsPath) {
    return {
      type: 'greenhouse',
      url: `https://boards-api.greenhouse.io/v1/boards/${boardsPath[1]}/jobs`,
    };
  }

  const subGh = url.match(/https?:\/\/([a-z0-9-]+)\.greenhouse\.io(?:\/|\?|#|$)/i);
  if (subGh) {
    const sub = subGh[1].toLowerCase();
    if (!['job-boards', 'boards', 'www', 'support'].includes(sub)) {
      return {
        type: 'greenhouse',
        url: `https://boards-api.greenhouse.io/v1/boards/${subGh[1]}/jobs`,
      };
    }
  }

  return null;
}

export function parseGreenhouse(json, companyName) {
  const jobs = json.jobs || [];
  return jobs.map(j => ({
    title: j.title || '',
    url: j.absolute_url || '',
    company: companyName,
    location: j.location?.name || '',
  }));
}

export function parseAshby(json, companyName) {
  const jobs = json.jobs || [];
  return jobs.map(j => ({
    title: j.title || '',
    url: j.jobUrl || '',
    company: companyName,
    location: j.location || '',
  }));
}

export function parseLever(json, companyName) {
  if (!Array.isArray(json)) return [];
  return json.map(j => ({
    title: j.text || '',
    url: j.hostedUrl || '',
    company: companyName,
    location: j.categories?.location || '',
  }));
}

/** Recruitee: { offers: [ { title, careers_url, status, location, city, ... } ] } */
export function parseRecruitee(json, companyName) {
  const offers = json.offers || [];
  return offers
    .filter(
      o =>
        !o.status ||
        o.status === 'published' ||
        o.status === 'open'
    )
    .map(o => {
      let loc = o.location || o.city || '';
      if (!loc && Array.isArray(o.locations) && o.locations.length) {
        const L = o.locations[0];
        loc = [L.city, L.country || L.country_code].filter(Boolean).join(', ');
      }
      return {
        title: o.title || '',
        url: o.careers_url || o.careers_apply_url || '',
        company: companyName,
        location: loc || '',
      };
    });
}

/** Workable widget: { jobs: [ { title, url, city, country, ... } ] } */
export function parseWorkable(json, companyName) {
  const jobs = json.jobs || [];
  return jobs.map(j => {
    const loc = [j.city, j.state, j.country].filter(Boolean).join(', ');
    return {
      title: j.title || '',
      url: j.url || j.shortlink || '',
      company: companyName,
      location: loc || '',
    };
  });
}

export const PARSERS = {
  greenhouse: parseGreenhouse,
  ashby: parseAshby,
  lever: parseLever,
  recruitee: parseRecruitee,
  workable: parseWorkable,
};

export async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Lever: si la cuenta está en la región EU, el mismo slug responde en api.eu.lever.co.
 */
export async function fetchBoardJson(api) {
  const { type, url } = api;
  if (type !== 'lever') {
    return fetchJson(url);
  }
  try {
    return await fetchJson(url);
  } catch (e) {
    const msg = String(e.message || e);
    if (/\b404\b/.test(msg) || msg.includes('HTTP 404')) {
      const euUrl = url.replace('https://api.lever.co/', 'https://api.eu.lever.co/');
      return await fetchJson(euUrl);
    }
    throw e;
  }
}
