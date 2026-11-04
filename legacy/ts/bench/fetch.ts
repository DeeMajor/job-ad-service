/**
 * Pull real job ads into bench/data/raw/<version>/ads.jsonl.
 *
 *   tsx bench/fetch.ts --source adzuna --country za --limit 300 --version v1 [--what "accountant"]
 *   tsx bench/fetch.ts --source jsonld --urls urls.txt --version v1
 *   tsx bench/fetch.ts --source ats --boards bench/boards.za.json --version v1       (keyless: Greenhouse / Workday / Workable / Lever public job-board APIs of named employers)
 *   tsx bench/fetch.ts --source arbeitnow|remotive --limit 50 --version smoke   (keyless, non-SA; pipeline testing only)
 *
 * Note: Adzuna's landing pages block automated clients (CloudFront 403), so the API yields ~65-word snippets only;
 * those fall under MIN_WORDS and are dropped. Use --source ats for full-text South African ads.
 *
 * Adzuna needs ADZUNA_APP_ID and ADZUNA_APP_KEY (free developer key, https://developer.adzuna.com/).
 * The search API returns a truncated description; we follow redirect_url to the original posting and
 * read its schema.org JobPosting JSON-LD for the full text. Ads with < MIN_WORDS words are dropped.
 */
import fs from "node:fs";
import path from "node:path";
import dns from "node:dns";
import net from "node:net";

// Node's happy-eyeballs gives each address 250 ms to connect; transatlantic hosts (api.adzuna.com) need longer,
// so every address "times out" while curl succeeds. Use plain sequential connects, IPv4 first.
dns.setDefaultResultOrder("ipv4first");
net.setDefaultAutoSelectFamily(false);

/** fetch with timeout and two retries on network errors / 5xx. */
async function fetchRetry(url: string, init: RequestInit = {}, tries = 3): Promise<Response> {
  let last: unknown;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, { ...init, signal: init.signal ?? AbortSignal.timeout(20000) });
      if (res.status >= 500 && i < tries - 1) { await sleep(500 * (i + 1)); continue; }
      return res;
    } catch (e) { last = e; await sleep(500 * (i + 1)); }
  }
  throw last;
}

export interface RawAd {
  id: string;
  source: string;
  url?: string;
  title: string;
  company?: string;
  location?: string;
  country: string;
  posted_at?: string;
  salary_min?: number;
  salary_max?: number;
  text: string;          // plain text, HTML stripped
  full_text: boolean;    // false when only the API snippet was available
  fetched_at: string;
}

const MIN_WORDS = 120;
const args = parseArgs(process.argv.slice(2));

async function main() {
  const source = args.source ?? "adzuna";
  const version = args.version ?? "v1";
  const limit = Number(args.limit ?? 300);
  const outDir = path.join("bench/data/raw", version);
  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, "ads.jsonl");
  const seen = new Set<string>(fs.existsSync(outFile) ? fs.readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => (JSON.parse(l) as RawAd).id) : []);
  const out = fs.createWriteStream(outFile, { flags: "a" });
  let kept = 0, dropped = 0;
  const emit = (ad: RawAd | undefined) => {
    if (!ad) { dropped++; return; }
    if (seen.has(ad.id) || wordCount(ad.text) < MIN_WORDS) { dropped++; return; }
    seen.add(ad.id); out.write(JSON.stringify(ad) + "\n"); kept++;
  };

  if (source === "adzuna") for await (const ad of adzuna(args.country ?? "za", limit, args.what)) emit(ad);
  else if (source === "jsonld") for (const u of fs.readFileSync(args.urls!, "utf8").split("\n").filter(Boolean)) emit(await fromJsonLd(u, "jsonld", args.country ?? "za"));
  else if (source === "ats") for await (const ad of atsBoards(args.boards ?? "bench/boards.za.json", limit)) emit(ad);
  else if (source === "arbeitnow") for await (const ad of arbeitnow(limit)) emit(ad);
  else if (source === "remotive") for await (const ad of remotive(limit)) emit(ad);
  else throw new Error(`unknown source ${source}`);
  out.end();
  console.log(JSON.stringify({ source, version, kept, dropped, total_in_file: seen.size, file: outFile }));
}

// ---------------- sources
async function* adzuna(country: string, limit: number, what?: string): AsyncGenerator<RawAd | undefined> {
  const id = process.env.ADZUNA_APP_ID, key = process.env.ADZUNA_APP_KEY;
  if (!id || !key) throw new Error("set ADZUNA_APP_ID and ADZUNA_APP_KEY");
  let page = 1, got = 0;
  while (got < limit) {
    const q = new URLSearchParams({ app_id: id, app_key: key, results_per_page: "50", "content-type": "application/json" });
    if (what) q.set("what", what);
    const res = await fetchRetry(`https://api.adzuna.com/v1/api/jobs/${country}/search/${page}?${q}`);
    if (!res.ok) throw new Error(`adzuna ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { results: any[] };
    if (!data.results?.length) return;
    for (const r of data.results) {
      if (got >= limit) return;
      got++;
      const snippet = strip(r.description ?? "");
      const base: RawAd = {
        id: `adzuna:${r.id}`, source: "adzuna", url: r.redirect_url, title: r.title ?? "", company: r.company?.display_name,
        location: r.location?.display_name, country: country.toUpperCase(), posted_at: r.created, salary_min: r.salary_min, salary_max: r.salary_max,
        text: snippet, full_text: false, fetched_at: new Date().toISOString(),
      };
      const full = r.redirect_url ? await fromJsonLd(r.redirect_url, "adzuna", country.toUpperCase()).catch(() => undefined) : undefined;
      yield full ? { ...base, text: full.text, full_text: true, url: full.url ?? base.url } : base;
      await sleep(250);
    }
    page++;
  }
}

// ---------------- ATS public job-board APIs (no keys). Config: [{ "ats": "greenhouse", "slug": "ozow", "company": "Ozow" }, ...]
interface Board { ats: "greenhouse" | "workday" | "workable" | "lever"; slug: string; company: string; wd?: string; site?: string; country?: string; /** Workday appliedFacets, e.g. locationCountry for a global tenant */ facets?: Record<string, string[]>; /** cap per board so one employer does not dominate the corpus */ max?: number }
const BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36";

async function* atsBoards(file: string, limit: number): AsyncGenerator<RawAd | undefined> {
  const boards: Board[] = JSON.parse(fs.readFileSync(file, "utf8"));
  let got = 0;
  for (const b of boards) {
    if (got >= limit) return;
    try {
      const gen = b.ats === "greenhouse" ? greenhouse(b) : b.ats === "workday" ? workday(b) : b.ats === "workable" ? workable(b) : lever(b);
      let fromBoard = 0;
      for await (const ad of gen) { if (got >= limit || fromBoard >= (b.max ?? 60)) break; got++; fromBoard++; yield ad; }
      console.error(`[ats] ${b.ats}/${b.slug}: ${fromBoard} ads`);
    } catch (e) { console.error(`[ats] ${b.ats}/${b.slug}: ${String(e).slice(0, 160)}`); }
    await sleep(300);
  }
}

async function* greenhouse(b: Board): AsyncGenerator<RawAd> {
  const res = await fetchRetry(`https://boards-api.greenhouse.io/v1/boards/${b.slug}/jobs?content=true`, { headers: { "user-agent": BROWSER_UA } });
  if (!res.ok) throw new Error(`greenhouse ${res.status}`);
  const data = (await res.json()) as { jobs: any[] };
  for (const j of data.jobs ?? []) {
    yield { id: `greenhouse:${b.slug}:${j.id}`, source: "greenhouse", url: j.absolute_url, title: j.title, company: b.company, location: j.location?.name, country: b.country ?? "ZA", posted_at: j.updated_at, text: strip(decodeEntities(j.content ?? "")), full_text: true, fetched_at: new Date().toISOString() };
  }
}

async function* lever(b: Board): AsyncGenerator<RawAd> {
  const res = await fetchRetry(`https://api.lever.co/v0/postings/${b.slug}?mode=json`, { headers: { "user-agent": BROWSER_UA } });
  if (!res.ok) throw new Error(`lever ${res.status}`);
  const data = (await res.json()) as any[];
  for (const j of data) {
    const lists = (j.lists ?? []).map((l: any) => `${l.text}\n${l.content}`).join("\n");
    yield { id: `lever:${b.slug}:${j.id}`, source: "lever", url: j.hostedUrl, title: j.text, company: b.company, location: j.categories?.location, country: b.country ?? "ZA", posted_at: j.createdAt ? new Date(j.createdAt).toISOString() : undefined, text: strip(`${j.descriptionHtml ?? j.description ?? ""}\n${lists}\n${j.additional ?? ""}`), full_text: true, fetched_at: new Date().toISOString() };
  }
}

async function* workable(b: Board): AsyncGenerator<RawAd> {
  const res = await fetchRetry(`https://apply.workable.com/api/v1/widget/accounts/${b.slug}`, { headers: { "user-agent": BROWSER_UA } });
  if (!res.ok) throw new Error(`workable ${res.status}`);
  const data = (await res.json()) as { name?: string; jobs: any[] };
  for (const j of data.jobs ?? []) {
    const d = await fetchRetry(`https://apply.workable.com/api/v2/accounts/${b.slug}/jobs/${j.shortcode}`, { headers: { "user-agent": BROWSER_UA } });
    if (!d.ok) continue;
    const full = (await d.json()) as any;
    yield { id: `workable:${b.slug}:${j.shortcode}`, source: "workable", url: j.url, title: j.title, company: b.company || data.name, location: [j.city, j.country].filter(Boolean).join(", "), country: b.country ?? "ZA", posted_at: j.published_on, text: strip(`${full.description ?? ""}\n${full.requirements ?? ""}\n${full.benefits ?? ""}`), full_text: true, fetched_at: new Date().toISOString() };
    await sleep(200);
  }
}

/** Workday CXS API: POST .../wday/cxs/{tenant}/{site}/jobs then GET each job's externalPath for the description. */
async function* workday(b: Board): AsyncGenerator<RawAd> {
  const base = `https://${b.slug}.${b.wd ?? "wd3"}.myworkdayjobs.com/wday/cxs/${b.slug}/${b.site}`;
  const headers = { "user-agent": BROWSER_UA, "content-type": "application/json", accept: "application/json" };
  let offset = 0;
  let total = Infinity; // Workday reports `total` only on the first page and wraps around past the end
  while (offset < Math.min(total, (b.max ?? 60) + 20)) {
    const res = await fetchRetry(`${base}/jobs`, { method: "POST", headers, body: JSON.stringify({ appliedFacets: b.facets ?? {}, limit: 20, offset, searchText: "" }) });
    if (!res.ok) throw new Error(`workday ${res.status}`);
    const data = (await res.json()) as { total: number; jobPostings: any[] };
    if (offset === 0) total = data.total ?? 0;
    if (!data.jobPostings?.length) return;
    for (const j of data.jobPostings) {
      const d = await fetchRetry(`${base}${j.externalPath}`, { headers });
      if (!d.ok) continue;
      const info = ((await d.json()) as any).jobPostingInfo ?? {};
      yield { id: `workday:${b.slug}:${info.jobReqId ?? j.externalPath}`, source: "workday", url: info.externalUrl ?? `https://${b.slug}.${b.wd ?? "wd3"}.myworkdayjobs.com/${b.site}${j.externalPath}`, title: info.title ?? j.title, company: b.company, location: info.location ?? j.locationsText, country: b.country ?? "ZA", posted_at: info.startDate, text: strip(info.jobDescription ?? ""), full_text: true, fetched_at: new Date().toISOString() };
      await sleep(200);
    }
    offset += 20;
  }
}

function decodeEntities(s: string): string {
  // Greenhouse returns HTML with entities escaped once more (&lt;p&gt;); decode a layer if it looks escaped.
  return /&lt;[a-z]/.test(s) ? s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&") : s;
}

async function* arbeitnow(limit: number): AsyncGenerator<RawAd | undefined> {
  let page = 1, got = 0;
  while (got < limit) {
    const res = await fetchRetry(`https://www.arbeitnow.com/api/job-board-api?page=${page}`);
    if (!res.ok) return;
    const data = (await res.json()) as { data: any[] };
    if (!data.data?.length) return;
    for (const r of data.data) {
      if (got >= limit) return;
      const text = strip(r.description ?? "");
      if (!looksEnglish(text)) continue;
      got++;
      yield { id: `arbeitnow:${r.slug}`, source: "arbeitnow", url: r.url, title: r.title, company: r.company_name, location: r.location, country: "DE", posted_at: r.created_at ? new Date(r.created_at * 1000).toISOString() : undefined, text, full_text: true, fetched_at: new Date().toISOString() };
    }
    page++;
  }
}

async function* remotive(limit: number): AsyncGenerator<RawAd | undefined> {
  const res = await fetchRetry(`https://remotive.com/api/remote-jobs?limit=${limit}`);
  if (!res.ok) return;
  const data = (await res.json()) as { jobs: any[] };
  for (const r of data.jobs ?? []) {
    yield { id: `remotive:${r.id}`, source: "remotive", url: r.url, title: r.title, company: r.company_name, location: r.candidate_required_location, country: "REMOTE", posted_at: r.publication_date, text: strip(r.description ?? ""), full_text: true, fetched_at: new Date().toISOString() };
  }
}

/** Fetch a page and extract the first schema.org JobPosting JSON-LD block. */
export async function fromJsonLd(url: string, source: string, country: string): Promise<RawAd | undefined> {
  const res = await fetchRetry(url, { headers: { "user-agent": "Mozilla/5.0 (job-ad-benchmark; +contact: recruitment-platform)" }, redirect: "follow", signal: AbortSignal.timeout(15000) }, 2);
  if (!res.ok) return undefined;
  const html = await res.text();
  const posting = extractJobPosting(html);
  if (!posting) return undefined;
  const text = strip(posting.description ?? "");
  if (!text) return undefined;
  return {
    id: `${source}:${hash(res.url + posting.title)}`, source, url: res.url, title: posting.title ?? "", company: posting.hiringOrganization?.name,
    location: posting.jobLocation?.address?.addressLocality ?? posting.jobLocation?.address?.addressRegion, country, posted_at: posting.datePosted,
    salary_min: posting.baseSalary?.value?.minValue, salary_max: posting.baseSalary?.value?.maxValue, text, full_text: true, fetched_at: new Date().toISOString(),
  };
}

export function extractJobPosting(html: string): any | undefined {
  const re = /<script[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    try {
      const j = JSON.parse(m[1].trim());
      const nodes: any[] = Array.isArray(j) ? j : j["@graph"] ? j["@graph"] : [j];
      const hit = nodes.find((n) => n && (n["@type"] === "JobPosting" || (Array.isArray(n["@type"]) && n["@type"].includes("JobPosting"))));
      if (hit) return hit;
    } catch { /* ignore malformed blocks */ }
  }
  return undefined;
}

// ---------------- helpers
export function strip(html: string): string {
  return html
    .replace(/<\s*(br|\/p|\/div|\/li|\/h[1-6]|\/tr)\s*\/?>/gi, "\n")
    .replace(/<\s*li[^>]*>/gi, "• ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;|&rsquo;|&#8217;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/[ \t]+/g, " ").replace(/\s*\n\s*/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}
const wordCount = (t: string) => (t.match(/[a-zA-Z][a-zA-Z'’-]*/g) ?? []).length;
const looksEnglish = (t: string) => { const w = t.toLowerCase(); const en = (w.match(/\b(the|and|you|with|will|our)\b/g) ?? []).length; const de = (w.match(/\b(und|der|die|das|mit|wir|sie)\b/g) ?? []).length; return en > de; };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
function hash(s: string): string { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return (h >>> 0).toString(16); }
function parseArgs(argv: string[]): Record<string, string> { const o: Record<string, string> = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) { const k = argv[i].slice(2); const v = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true"; o[k] = v; } return o; }

if (process.argv[1] && /fetch\.ts$/.test(process.argv[1])) main().catch((e) => { console.error(e); process.exit(1); });
