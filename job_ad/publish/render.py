"""Platform-ready payloads from a JobAd: normalised fields, renderings (html/text/markdown/json-ld), per-platform payloads and validation."""
from __future__ import annotations

import html as htmlmod
import re
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..metrics.text import render_ad, render_markdown, words
from ..metrics.types import JobAd
from .platforms import PLATFORMS, Platform

SA_PROVINCES = {
    "gauteng": "Gauteng", "western cape": "Western Cape", "kwazulu-natal": "KwaZulu-Natal", "kwazulu natal": "KwaZulu-Natal", "kzn": "KwaZulu-Natal", "eastern cape": "Eastern Cape",
    "free state": "Free State", "limpopo": "Limpopo", "mpumalanga": "Mpumalanga", "north west": "North West", "northern cape": "Northern Cape",
}
CITY_PROVINCE = {
    "johannesburg": "Gauteng", "sandton": "Gauteng", "pretoria": "Gauteng", "midrand": "Gauteng", "centurion": "Gauteng", "randburg": "Gauteng", "soweto": "Gauteng", "roodepoort": "Gauteng", "kempton park": "Gauteng", "boksburg": "Gauteng", "germiston": "Gauteng",
    "cape town": "Western Cape", "stellenbosch": "Western Cape", "bellville": "Western Cape", "paarl": "Western Cape", "george": "Western Cape", "somerset west": "Western Cape", "moorreesburg": "Western Cape", "riviersonderend": "Western Cape",
    "durban": "KwaZulu-Natal", "pietermaritzburg": "KwaZulu-Natal", "umhlanga": "KwaZulu-Natal", "richards bay": "KwaZulu-Natal", "amanzimtoti": "KwaZulu-Natal",
    "port elizabeth": "Eastern Cape", "gqeberha": "Eastern Cape", "east london": "Eastern Cape", "bloemfontein": "Free State", "polokwane": "Limpopo", "nelspruit": "Mpumalanga", "mbombela": "Mpumalanga", "rustenburg": "North West", "kimberley": "Northern Cape", "colesberg": "Northern Cape",
}
EMPLOYMENT_TYPES = {  # our brief vocabulary → schema.org / platform vocabularies
    "permanent": {"schema": "FULL_TIME", "linkedin": "Full-time", "indeed": "fulltime", "generic": "Permanent"},
    "fixed_term": {"schema": "CONTRACTOR", "linkedin": "Contract", "indeed": "contract", "generic": "Fixed-term contract"},
    "contract": {"schema": "CONTRACTOR", "linkedin": "Contract", "indeed": "contract", "generic": "Contract"},
    "part_time": {"schema": "PART_TIME", "linkedin": "Part-time", "indeed": "parttime", "generic": "Part-time"},
    "internship": {"schema": "INTERN", "linkedin": "Internship", "indeed": "internship", "generic": "Internship"},
    "learnership": {"schema": "INTERN", "linkedin": "Internship", "indeed": "internship", "generic": "Learnership"},
    "temporary": {"schema": "TEMPORARY", "linkedin": "Temporary", "indeed": "temporary", "generic": "Temporary"},
}
SALARY_UNIT = {"year": "YEAR", "month": "MONTH", "week": "WEEK", "day": "DAY", "hour": "HOUR"}


class PublishExtras(BaseModel):
    """What the client knows that the ad text does not: where applications go, identifiers, taxonomy."""
    apply_url: Optional[str] = None
    reference: Optional[str] = Field(default=None, description="your job reference / external id, for updates and withdrawals")
    category: Optional[str] = Field(default=None, description="platform category / sector / industry (SA boards require one)")
    employment_type: Optional[str] = Field(default=None, description="permanent | fixed_term | contract | part_time | internship | learnership | temporary")
    company_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    date_posted: Optional[date] = None
    valid_through: Optional[date] = Field(default=None, description="defaults to the ad's closing date when parseable")
    country: str = "ZA"


class Location(BaseModel):
    raw: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: str = "ZA"
    remote: bool = False
    hybrid: bool = False


class Salary(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: str = "ZAR"
    unit: str = "MONTH"
    basis: Optional[str] = None


class Fields(BaseModel):
    title: str
    company_name: Optional[str] = None
    location: Location
    employment_type: Optional[str] = None
    employment_type_schema: Optional[str] = None
    salary: Optional[Salary] = None
    closing_date: Optional[date] = None
    reference: Optional[str] = None
    category: Optional[str] = None
    apply_url: Optional[str] = None
    word_count: int


class Renderings(BaseModel):
    html: str
    text: str
    markdown: str
    json_ld: dict[str, Any]
    teaser: str


class Issue(BaseModel):
    severity: str  # error | warning
    field: str
    message: str


class ChannelPayload(BaseModel):
    platform: str
    ready: bool
    issues: list[Issue]
    payload: dict[str, Any]


class RenderResult(BaseModel):
    fields: Fields
    renderings: Renderings
    channels: dict[str, ChannelPayload]


# ---------------- normalisation
def parse_location(raw: Optional[str], country: str = "ZA", work_mode: Optional[str] = None) -> Location:
    loc = Location(raw=raw, country=country, remote=work_mode == "remote", hybrid=work_mode == "hybrid")
    if not raw:
        return loc
    parts = [p.strip() for p in re.split(r"[,/|·]", raw) if p.strip()]
    low = [p.lower() for p in parts]
    for p, l in zip(parts, low):
        if l in SA_PROVINCES:
            loc.province = SA_PROVINCES[l]
        elif l in CITY_PROVINCE:
            loc.city = loc.city or p.title() if p.islower() else loc.city or p
            loc.province = loc.province or CITY_PROVINCE[l]
        elif l in ("south africa", "za", "rsa"):
            loc.country = "ZA"
    if not loc.city and parts:
        first = parts[0]
        if first.lower() not in SA_PROVINCES and first.lower() not in ("south africa", "za", "rsa"):
            loc.city = first
    return loc


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    t = re.sub(r"[,\s]+\d{1,2}:\d{2}.*$", "", s.strip())
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _esc(s: str) -> str:
    return htmlmod.escape(s, quote=False)


def render_html(ad: JobAd) -> str:
    """Conservative HTML: p, h2, ul/li, strong, br only — the intersection of what job boards accept."""
    L: list[str] = [f"<h2>{_esc(ad.title)}</h2>"]
    meta = " · ".join(x for x in [ad.company.name if ad.company and ad.company.name else None, ad.location, ad.work_mode if ad.work_mode and ad.work_mode != "unspecified" else None, ad.work_mode_detail] if x)
    if meta:
        L.append(f"<p><strong>{_esc(meta)}</strong></p>")
    if ad.pay and (ad.pay.min or ad.pay.max):
        from ..metrics.text import render_pay
        L.append(f"<p><strong>{_esc(render_pay(ad.pay))}</strong></p>")
    def para(title: str, body: Optional[str]) -> None:
        if body:
            L.append(f"<h3>{_esc(title)}</h3>")
            L.extend(f"<p>{_esc(p.strip())}</p>" for p in re.split(r"\n{2,}|\n", body) if p.strip())
    def lst(title: str, items: list[str]) -> None:
        if items:
            L.append(f"<h3>{_esc(title)}</h3><ul>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>")
    para("About us", ad.company.about if ad.company else None); para("About the role", ad.summary); para("Your team", ad.team)
    lst("What you'll do", ad.responsibilities); lst("What you need", ad.must_have); lst("Nice to have", ad.nice_to_have); lst("What we offer", ad.benefits)
    para("How to apply", ad.process)
    if ad.closing_date:
        L.append(f"<p><strong>Closing date:</strong> {_esc(ad.closing_date)}</p>")
    for x in (ad.apply_contact, ad.accessibility_statement, ad.ee_statement, ad.popia_notice, ad.other):
        if x:
            L.append(f"<p>{_esc(x)}</p>")
    return "\n".join(L)


def render_teaser(ad: JobAd, apply_url: Optional[str], max_chars: int = 280) -> str:
    loc = ad.location or ""
    pay = ""
    if ad.pay and ad.pay.min and ad.pay.max and ad.pay.period:
        pay = f" R{int(ad.pay.min):,}–R{int(ad.pay.max):,}/{ {'month':'month','year':'year','hour':'hour','day':'day','week':'week'}[ad.pay.period] }"
    company = f" at {ad.company.name}" if ad.company and ad.company.name else ""
    hook = (ad.summary or "").split(". ")[0].strip().rstrip(".") if ad.summary else ""
    base = f"We're hiring: {ad.title}{company}{' in ' + loc if loc else ''}.{pay and (pay + '.') or ''}"
    link = f" Apply: {apply_url}" if apply_url else ""
    room = max_chars - len(base) - len(link) - 1
    if hook and room > 30:
        hook = hook if len(hook) <= room else hook[: room - 1].rsplit(" ", 1)[0] + "…"
        base = f"{base} {hook}."
    return (base + link).strip()


def json_ld(ad: JobAd, f: Fields, extras: PublishExtras, html: str) -> dict[str, Any]:
    d: dict[str, Any] = {"@context": "https://schema.org/", "@type": "JobPosting", "title": ad.title, "description": html,
                         "datePosted": (extras.date_posted or date.today()).isoformat(),
                         "hiringOrganization": {"@type": "Organization", "name": f.company_name or ""}}
    if extras.company_url: d["hiringOrganization"]["sameAs"] = extras.company_url
    if extras.company_logo_url: d["hiringOrganization"]["logo"] = extras.company_logo_url
    vt = extras.valid_through or f.closing_date
    if vt: d["validThrough"] = vt.isoformat()
    if f.employment_type_schema: d["employmentType"] = f.employment_type_schema
    if f.reference: d["identifier"] = {"@type": "PropertyValue", "name": f.company_name or "ref", "value": f.reference}
    addr: dict[str, Any] = {"@type": "PostalAddress", "addressCountry": f.location.country}
    if f.location.city: addr["addressLocality"] = f.location.city
    if f.location.province: addr["addressRegion"] = f.location.province
    d["jobLocation"] = {"@type": "Place", "address": addr}
    if f.location.remote:
        d["jobLocationType"] = "TELECOMMUTE"; d["applicantLocationRequirements"] = {"@type": "Country", "name": "South Africa" if f.location.country == "ZA" else f.location.country}
    if f.salary and (f.salary.min or f.salary.max):
        val: dict[str, Any] = {"@type": "QuantitativeValue", "unitText": f.salary.unit}
        if f.salary.min is not None: val["minValue"] = f.salary.min
        if f.salary.max is not None: val["maxValue"] = f.salary.max
        d["baseSalary"] = {"@type": "MonetaryAmount", "currency": f.salary.currency, "value": val}
    if extras.apply_url: d["directApply"] = True; d["url"] = extras.apply_url
    return d


def normalise(ad: JobAd, extras: PublishExtras) -> Fields:
    et = extras.employment_type
    sal = None
    if ad.pay and (ad.pay.min or ad.pay.max):
        sal = Salary(min=ad.pay.min, max=ad.pay.max, currency=ad.pay.currency or "ZAR", unit=SALARY_UNIT.get(ad.pay.period or "month", "MONTH"), basis=ad.pay.basis)
    return Fields(title=ad.title.strip(), company_name=ad.company.name if ad.company else None, location=parse_location(ad.location, extras.country, ad.work_mode),
                  employment_type=et, employment_type_schema=EMPLOYMENT_TYPES.get(et or "", {}).get("schema"), salary=sal, closing_date=_parse_date(ad.closing_date),
                  reference=extras.reference, category=extras.category, apply_url=extras.apply_url, word_count=len(words(render_ad(ad, headings=False))))


# ---------------- per-platform payloads
def _check_limits(p: Platform, values: dict[str, str]) -> list[Issue]:
    out: list[Issue] = []
    for lim in p.limits:
        v = values.get(lim.field)
        if v is None:
            continue
        n = len(words(v)) if lim.unit == "words" else len(v)
        if n > lim.max:
            out.append(Issue(severity="error" if lim.kind == "hard" else "warning", field=lim.field, message=f"{lim.field} is {n} {lim.unit}; {p.name} {'limit' if lim.kind == 'hard' else 'recommends at most'} {lim.max}."))
    if p.word_band and "description" in values:
        n = len(words(values["description"]))
        if n < p.word_band[0]:
            out.append(Issue(severity="warning", field="description", message=f"description is {n} words; {p.name} performs best at {p.word_band[0]}–{p.word_band[1]}."))
    return out


def build_channel(p: Platform, ad: JobAd, f: Fields, r: Renderings, extras: PublishExtras) -> ChannelPayload:
    issues: list[Issue] = []
    for req in p.requires:
        if not getattr(extras, req, None):
            issues.append(Issue(severity="error", field=req, message=f"{p.name} requires `{req}`; supply it in publish extras."))
    if p.id in ("pnet", "careers24", "careerjunction") and not f.location.province:
        issues.append(Issue(severity="error", field="location", message=f"{p.name} needs a South African province; could not derive one from '{f.location.raw}'."))
    desc = r.html if p.description_format == "html" else r.text
    payload: dict[str, Any] = {"title": f.title, "company": f.company_name, "location": f.location.model_dump(), "employment_type": EMPLOYMENT_TYPES.get(f.employment_type or "", {}).get(p.id if p.id in ("linkedin", "indeed") else "generic"),
                               "apply_url": extras.apply_url, "reference": f.reference, "closing_date": f.closing_date.isoformat() if f.closing_date else None}
    if p.supports_salary and f.salary:
        payload["salary"] = f.salary.model_dump()
    if p.supports_remote_flag:
        payload["remote"] = f.location.remote; payload["hybrid"] = f.location.hybrid
    if p.id == "social_teaser":
        payload["teaser"] = r.teaser; payload["link"] = extras.apply_url
        issues += _check_limits(p, {"teaser": r.teaser})
    elif p.id == "careers_site":
        payload["html"] = r.html; payload["json_ld"] = r.json_ld
        issues += _check_limits(p, {"title": f.title, "description": r.text})
    else:
        payload["description"] = desc; payload["description_format"] = p.description_format
        if p.requires and "category" in p.requires:
            payload["category"] = f.category
        issues += _check_limits(p, {"title": f.title, "description": r.text})
    return ChannelPayload(platform=p.id, ready=not any(i.severity == "error" for i in issues), issues=issues, payload=payload)


def render_all(ad: JobAd, extras: Optional[PublishExtras] = None, channels: Optional[list[str]] = None) -> RenderResult:
    extras = extras or PublishExtras()
    f = normalise(ad, extras)
    html = render_html(ad)
    r = Renderings(html=html, text=render_ad(ad), markdown=render_markdown(ad), json_ld=json_ld(ad, f, extras, html), teaser=render_teaser(ad, extras.apply_url))
    ids = channels or list(PLATFORMS)
    unknown = [c for c in ids if c not in PLATFORMS]
    if unknown:
        raise KeyError(f"unknown platform(s): {unknown}; see GET /v1/platforms")
    return RenderResult(fields=f, renderings=r, channels={c: build_channel(PLATFORMS[c], ad, f, r, extras) for c in ids})
