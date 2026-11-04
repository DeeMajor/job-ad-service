"""Pull real job ads into bench/data/raw/<version>/ads.jsonl (Python port).

  .venv/bin/python -m bench.fetch --source ats --boards bench/boards.za.json --limit 400 --version v1
  .venv/bin/python -m bench.fetch --source jsonld --urls urls.txt --version v1
  .venv/bin/python -m bench.fetch --source arbeitnow|remotive --limit 40 --version smoke     (keyless, non-SA; pipeline tests)
  .venv/bin/python -m bench.fetch --source adzuna --country za --limit 50 --version x        (snippets only; dropped under MIN_WORDS)

Sources: public ATS job-board APIs (Workday CXS, Greenhouse, Lever, Workable), schema.org JobPosting JSON-LD, keyless feeds.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

import httpx

MIN_WORDS = 120
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
_client = httpx.Client(timeout=20.0, follow_redirects=True, headers={"user-agent": UA})


def strip(h: str) -> str:
    h = re.sub(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"<\s*li[^>]*>", "• ", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t]+", " ", h); h = re.sub(r"\s*\n\s*", "\n", h); h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def word_count(t: str) -> int:
    return len(re.findall(r"[a-zA-Z][a-zA-Z'’-]*", t))


def looks_english(t: str) -> bool:
    w = t.lower()
    return len(re.findall(r"\b(the|and|you|with|will|our)\b", w)) > len(re.findall(r"\b(und|der|die|das|mit|wir|sie)\b", w))


def get(url: str, retries: int = 3, **kw) -> Optional[httpx.Response]:
    last = None
    for i in range(retries):
        try:
            r = _client.get(url, **kw)
            if r.status_code >= 500 and i < retries - 1:
                time.sleep(0.5 * (i + 1)); continue
            return r
        except httpx.HTTPError as e:
            last = e; time.sleep(0.5 * (i + 1))
    print(f"[fetch] giving up on {url}: {last}", file=sys.stderr)
    return None


def post(url: str, body: dict, retries: int = 3) -> Optional[httpx.Response]:
    for i in range(retries):
        try:
            r = _client.post(url, json=body, headers={"accept": "application/json"})
            if r.status_code >= 500 and i < retries - 1:
                time.sleep(0.5 * (i + 1)); continue
            return r
        except httpx.HTTPError:
            time.sleep(0.5 * (i + 1))
    return None


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ad(**kw) -> dict:
    kw.setdefault("full_text", True); kw.setdefault("fetched_at", now())
    return kw


# ---------------- ATS boards
def ats_boards(file: str, limit: int) -> Iterator[dict]:
    boards = json.loads(Path(file).read_text(encoding="utf-8"))
    got = 0
    for b in boards:
        if got >= limit:
            return
        gen = {"greenhouse": greenhouse, "workday": workday, "workable": workable, "lever": lever}[b["ats"]]
        n = 0
        try:
            for x in gen(b):
                if got >= limit or n >= b.get("max", 60):
                    break
                got += 1; n += 1; yield x
        except Exception as e:
            print(f"[ats] {b['ats']}/{b['slug']}: {str(e)[:160]}", file=sys.stderr)
        print(f"[ats] {b['ats']}/{b['slug']}: {n} ads", file=sys.stderr)
        time.sleep(0.3)


def greenhouse(b: dict) -> Iterator[dict]:
    r = get(f"https://boards-api.greenhouse.io/v1/boards/{b['slug']}/jobs?content=true")
    if not r or r.status_code != 200:
        raise RuntimeError(f"greenhouse {r.status_code if r else 'no response'}")
    for j in r.json().get("jobs", []):
        content = j.get("content") or ""
        if re.search(r"&lt;[a-z]", content):
            content = html.unescape(content)
        yield ad(id=f"greenhouse:{b['slug']}:{j['id']}", source="greenhouse", url=j.get("absolute_url"), title=j.get("title", ""), company=b["company"], location=(j.get("location") or {}).get("name"),
                 country=b.get("country", "ZA"), posted_at=j.get("updated_at"), text=strip(content))


def lever(b: dict) -> Iterator[dict]:
    r = get(f"https://api.lever.co/v0/postings/{b['slug']}?mode=json")
    if not r or r.status_code != 200:
        raise RuntimeError(f"lever {r.status_code if r else 'no response'}")
    for j in r.json():
        lists = "\n".join(f"{l.get('text','')}\n{l.get('content','')}" for l in j.get("lists", []))
        yield ad(id=f"lever:{b['slug']}:{j['id']}", source="lever", url=j.get("hostedUrl"), title=j.get("text", ""), company=b["company"], location=(j.get("categories") or {}).get("location"),
                 country=b.get("country", "ZA"), posted_at=None, text=strip(f"{j.get('descriptionHtml') or j.get('description') or ''}\n{lists}\n{j.get('additional') or ''}"))


def workable(b: dict) -> Iterator[dict]:
    r = get(f"https://apply.workable.com/api/v1/widget/accounts/{b['slug']}")
    if not r or r.status_code != 200:
        raise RuntimeError(f"workable {r.status_code if r else 'no response'}")
    data = r.json()
    for j in data.get("jobs", []):
        d = get(f"https://apply.workable.com/api/v2/accounts/{b['slug']}/jobs/{j['shortcode']}")
        if not d or d.status_code != 200:
            continue
        full = d.json()
        yield ad(id=f"workable:{b['slug']}:{j['shortcode']}", source="workable", url=j.get("url"), title=j.get("title", ""), company=b.get("company") or data.get("name"),
                 location=", ".join(x for x in (j.get("city"), j.get("country")) if x), country=b.get("country", "ZA"), posted_at=j.get("published_on"),
                 text=strip(f"{full.get('description','')}\n{full.get('requirements','')}\n{full.get('benefits','')}"))
        time.sleep(0.2)


def workday(b: dict) -> Iterator[dict]:
    """Workday CXS: POST .../jobs (total only reliable on the first page; wraps past the end), then GET each externalPath."""
    wd = b.get("wd", "wd3"); base = f"https://{b['slug']}.{wd}.myworkdayjobs.com/wday/cxs/{b['slug']}/{b['site']}"
    offset, total = 0, float("inf")
    while offset < min(total, b.get("max", 60) + 20):
        r = post(f"{base}/jobs", {"appliedFacets": b.get("facets", {}), "limit": 20, "offset": offset, "searchText": ""})
        if not r or r.status_code != 200:
            raise RuntimeError(f"workday {r.status_code if r else 'no response'}")
        data = r.json()
        if offset == 0:
            total = data.get("total", 0)
        posts = data.get("jobPostings") or []
        if not posts:
            return
        for j in posts:
            d = get(f"{base}{j['externalPath']}", headers={"accept": "application/json"})
            if not d or d.status_code != 200:
                continue
            info = d.json().get("jobPostingInfo") or {}
            yield ad(id=f"workday:{b['slug']}:{info.get('jobReqId') or j['externalPath']}", source="workday", url=info.get("externalUrl") or f"https://{b['slug']}.{wd}.myworkdayjobs.com/{b['site']}{j['externalPath']}",
                     title=info.get("title") or j.get("title", ""), company=b["company"], location=info.get("location") or j.get("locationsText"), country=b.get("country", "ZA"),
                     posted_at=info.get("startDate"), text=strip(info.get("jobDescription") or ""))
            time.sleep(0.2)
        offset += 20


# ---------------- JSON-LD and keyless feeds
def extract_job_posting(page: str) -> Optional[dict]:
    for m in re.finditer(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>", page, re.I):
        try:
            j = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        nodes = j if isinstance(j, list) else j.get("@graph", [j]) if isinstance(j, dict) else []
        for n in nodes:
            t = n.get("@type") if isinstance(n, dict) else None
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                return n
    return None


def from_jsonld(url: str, source: str, country: str) -> Optional[dict]:
    r = get(url)
    if not r or r.status_code != 200:
        return None
    p = extract_job_posting(r.text)
    if not p:
        return None
    text = strip(p.get("description") or "")
    if not text:
        return None
    addr = ((p.get("jobLocation") or {}).get("address") or {}) if isinstance(p.get("jobLocation"), dict) else {}
    sal = ((p.get("baseSalary") or {}).get("value") or {}) if isinstance(p.get("baseSalary"), dict) else {}
    return ad(id=f"{source}:{hashlib.sha1((str(r.url) + str(p.get('title'))).encode()).hexdigest()[:10]}", source=source, url=str(r.url), title=p.get("title", ""),
              company=(p.get("hiringOrganization") or {}).get("name"), location=addr.get("addressLocality") or addr.get("addressRegion"), country=country, posted_at=p.get("datePosted"),
              salary_min=sal.get("minValue"), salary_max=sal.get("maxValue"), text=text)


def arbeitnow(limit: int) -> Iterator[dict]:
    page, got = 1, 0
    while got < limit:
        r = get(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        if not r or r.status_code != 200:
            return
        rows = r.json().get("data") or []
        if not rows:
            return
        for j in rows:
            text = strip(j.get("description") or "")
            if not looks_english(text):
                continue
            if got >= limit:
                return
            got += 1
            yield ad(id=f"arbeitnow:{j['slug']}", source="arbeitnow", url=j.get("url"), title=j.get("title", ""), company=j.get("company_name"), location=j.get("location"), country="DE",
                     posted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(j["created_at"])) if j.get("created_at") else None, text=text)
        page += 1


def remotive(limit: int) -> Iterator[dict]:
    r = get(f"https://remotive.com/api/remote-jobs?limit={limit}")
    if not r or r.status_code != 200:
        return
    for j in r.json().get("jobs", []):
        yield ad(id=f"remotive:{j['id']}", source="remotive", url=j.get("url"), title=j.get("title", ""), company=j.get("company_name"), location=j.get("candidate_required_location"), country="REMOTE",
                 posted_at=j.get("publication_date"), text=strip(j.get("description") or ""))


def adzuna(country: str, limit: int, what: Optional[str]) -> Iterator[dict]:
    """Search API only: ~65-word snippets (landing pages block automated clients). Kept for salary metadata."""
    app_id, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and key):
        raise RuntimeError("set ADZUNA_APP_ID and ADZUNA_APP_KEY")
    page, got = 1, 0
    while got < limit:
        params = {"app_id": app_id, "app_key": key, "results_per_page": 50, "content-type": "application/json"}
        if what:
            params["what"] = what
        r = get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}", params=params)
        if not r or r.status_code != 200:
            raise RuntimeError(f"adzuna {r.status_code if r else 'no response'}: {r.text[:200] if r else ''}")
        rows = r.json().get("results") or []
        if not rows:
            return
        for x in rows:
            if got >= limit:
                return
            got += 1
            yield ad(id=f"adzuna:{x['id']}", source="adzuna", url=x.get("redirect_url"), title=x.get("title", ""), company=(x.get("company") or {}).get("display_name"), location=(x.get("location") or {}).get("display_name"),
                     country=country.upper(), posted_at=x.get("created"), salary_min=x.get("salary_min"), salary_max=x.get("salary_max"), text=strip(x.get("description") or ""), full_text=False)
        page += 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="ats"); ap.add_argument("--version", default="v1"); ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--boards", default="bench/boards.za.json"); ap.add_argument("--urls"); ap.add_argument("--country", default="za"); ap.add_argument("--what")
    a = ap.parse_args(argv)
    out_dir = Path("bench/data/raw") / a.version; out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ads.jsonl"
    seen = {json.loads(l)["id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    kept = dropped = 0
    if a.source == "ats":
        gen = ats_boards(a.boards, a.limit)
    elif a.source == "jsonld":
        gen = (x for u in Path(a.urls).read_text().splitlines() if u.strip() for x in [from_jsonld(u.strip(), "jsonld", a.country.upper())] if x)
    elif a.source == "arbeitnow":
        gen = arbeitnow(a.limit)
    elif a.source == "remotive":
        gen = remotive(a.limit)
    elif a.source == "adzuna":
        gen = adzuna(a.country, a.limit, a.what)
    else:
        raise SystemExit(f"unknown source {a.source}")
    with out.open("a", encoding="utf-8") as f:
        for x in gen:
            if x["id"] in seen or word_count(x["text"]) < MIN_WORDS:
                dropped += 1; continue
            seen.add(x["id"]); kept += 1
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(json.dumps({"source": a.source, "version": a.version, "kept": kept, "dropped": dropped, "total_in_file": len(seen), "file": str(out)}))


if __name__ == "__main__":
    main()
