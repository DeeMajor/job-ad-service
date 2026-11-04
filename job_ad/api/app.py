"""Headless job-ad service (FastAPI). No UI.

    PORT=4310 .venv/bin/uvicorn job_ad.api.app:app --host 127.0.0.1 --port 4310

  GET  /healthz                 → { ok, versions }
  GET  /v1/spec                 → the metric spec
  POST /v1/scores  { ad, context?, judge?, judge_model? }   → { scorecard, meta }   judge=false is free (deterministic only)
  POST /v1/drafts  { brief, options? }                      → { ad, scorecard, meta } one Opus call + one judge call
OpenAPI at /docs and /openapi.json. Errors: 422 validation (FastAPI), 502 upstream model API, 500.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Literal, Optional

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from ..costs import usage_cost_usd
from .jobs import CAP_REFUSALS, DAILY_CAP_USD, DRAFTS, JUDGE_CALLS, LATENCY, SPEND, TOKENS, JobRunner, SpendCap, Store

from ..drafter.brief import BRIEF_SCHEMA_VERSION, HiringBrief
from ..drafter.completeness import Completeness, check
from ..drafter.draft import draft
from ..drafter.extract import EXTRACT_PROMPT_VERSION, extract
from ..drafter.prompts import DRAFTER_PROMPT_VERSION
from ..metrics.judge.prompt import JUDGE_PROMPT_VERSION
from ..metrics.scorecard import score, score_deterministic
from ..metrics.spec import load_spec
from ..metrics.text import render_ad, render_markdown
from ..metrics.types import JobAd, Scorecard, ScoringContext

# ---- structured JSON logs to stdout (Alloy → Loki); every line carries the version stamps
class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)), "level": record.levelname, "logger": record.name, "msg": record.getMessage(), "spec": SPEC_VERSION, "drafter_prompt": DRAFTER_PROMPT_VERSION, "judge_prompt": JUDGE_PROMPT_VERSION}
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)[-2000:]
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            base.update(extra)
        return json.dumps(base, default=str)


spec = load_spec()
SPEC_VERSION = spec.version
_h = logging.StreamHandler(); _h.setFormatter(_JsonFormatter())
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), handlers=[_h], force=True)
log = logging.getLogger("job_ad.api")

store = Store(os.environ.get("REDIS_URL") or None)
spend_cap = SpendCap(store)
runner = JobRunner(store, spend_cap)
log.info("startup", extra={"extra": {"store": store.backend, "daily_cap_usd": DAILY_CAP_USD}})

app = FastAPI(title="job-ad service", version="0.1.0", description="Drafts and scores job advertisements. Headless: clients produce a HiringBrief, the service returns an ad and its scorecard.")
_client: Optional[anthropic.Anthropic] = None

# Web enrichment is a deployment-level switch (ENRICH_ENABLED=true to allow options.enrich). Off by default and currently off by decision.
ENRICH_ENABLED = os.environ.get("ENRICH_ENABLED", "").lower() in ("1", "true", "yes")

# Browser clients need CORS. Comma-separated origins in ALLOWED_ORIGINS, e.g. "http://localhost:5173,https://app.example.co.za". Empty = no CORS.
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["content-type", "authorization"], expose_headers=["x-request-id"])


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class ScoreRequest(BaseModel):
    ad: JobAd
    context: ScoringContext = Field(default_factory=ScoringContext)
    judge: bool = True
    judge_model: Optional[str] = None


class DraftOptions(BaseModel):
    model: Optional[str] = None
    effort: Literal["low", "medium", "high"] = "medium"
    judge_model: Optional[str] = None
    score: bool = True
    allow_not_ready: bool = Field(default=False, description="If false (default) and the completeness check says the draft would come back not_ready, the service refuses with 422 before any model call.")
    enrich: bool = Field(default=False, description="Web enrichment: search the employer's public web presence (restricted to company.website when given) for about/values/locations/published benefits; cited in `sources`. Never pay or legal statements. Adds one model call and up to `max_searches` web searches.")
    max_searches: int = Field(default=3, ge=1, le=5)


class DraftRequest(BaseModel):
    brief: HiringBrief
    options: DraftOptions = Field(default_factory=DraftOptions)


class DraftJobRequest(DraftRequest):
    callback_url: Optional[str] = Field(default=None, description="If set, the service POSTs {job_id, status, result, error} here when the job finishes (best effort).")


class DraftJob(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    status_url: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[dict] = Field(default=None, description="The /v1/drafts response once status is done")
    error: Optional[str] = None


class ModelCall(BaseModel):
    model: str
    usage: dict
    latency_s: float
    prompt_version: str


class ScoreMeta(BaseModel):
    judge: Optional[ModelCall] = None
    spec: str


class ScoreResponse(BaseModel):
    scorecard: Scorecard
    meta: ScoreMeta


class EnrichmentMeta(BaseModel):
    model: str
    searches: int
    facts: int
    usage: dict
    latency_s: float
    prompt_version: str
    notes: str


class DraftMeta(BaseModel):
    request_id: str
    drafter: ModelCall
    judge: Optional[ModelCall] = None
    enrichment: Optional[EnrichmentMeta] = None
    spec: str
    brief_schema: str


class WebSource(BaseModel):
    id: str
    url: str
    facts: list[str]


class Rendered(BaseModel):
    markdown: str = Field(description="The ad as Markdown — headings, bullets, bold. Deterministic from `ad`; convert to HTML or paste into an editor.")
    text: str = Field(description="The ad as plain text, as a candidate would read it")


class DraftResponse(BaseModel):
    ad: JobAd = Field(description="The structured ad: the source of truth. Score, edit and publish from this.")
    rendered: Rendered
    scorecard: Optional[Scorecard] = None
    brief_feedback: Completeness
    sources: list[WebSource] = Field(default_factory=list, description="Web-sourced employer facts the drafter was allowed to use, by URL. Show them for the recruiter to confirm.")
    meta: DraftMeta


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = str(uuid.uuid4())
    request.state.request_id = rid
    resp = await call_next(request)
    resp.headers["x-request-id"] = rid
    return resp


@app.exception_handler(anthropic.APIError)
async def upstream_error(request: Request, exc: anthropic.APIError):
    return JSONResponse(status_code=502, content={"error": "upstream", "status": getattr(exc, "status_code", None), "message": str(exc)})


@app.get("/healthz")
def healthz():
    return {"ok": True, "versions": {"spec": spec.version, "judge_prompt": JUDGE_PROMPT_VERSION, "drafter_prompt": DRAFTER_PROMPT_VERSION, "brief_schema": BRIEF_SCHEMA_VERSION},
            "features": {"enrichment": ENRICH_ENABLED, "jobs_store": store.backend}, "spend": {"today_usd": round(spend_cap.today(), 4), "daily_cap_usd": DAILY_CAP_USD}}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _record(d, mode: str) -> float:
    """Metrics + spend for one completed draft; returns estimated USD."""
    usd = usage_cost_usd(d.model, d.usage)
    u = d.usage.model_dump() if hasattr(d.usage, "model_dump") else dict(d.usage)
    TOKENS.labels(d.model, "input").inc(u.get("input_tokens", 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)); TOKENS.labels(d.model, "output").inc(u.get("output_tokens", 0))
    SPEND.labels(d.model).inc(usd)
    if d.judge:
        JUDGE_CALLS.inc(); jusd = usage_cost_usd(d.judge.model, d.judge.usage); SPEND.labels(d.judge.model).inc(jusd); usd += jusd
        ju = d.judge.usage.model_dump(); TOKENS.labels(d.judge.model, "input").inc(ju.get("input_tokens", 0) + (ju.get("cache_read_input_tokens") or 0)); TOKENS.labels(d.judge.model, "output").inc(ju.get("output_tokens", 0))
    if d.enrichment:
        eusd = usage_cost_usd(d.enrichment.model, d.enrichment.usage) + 0.01 * d.enrichment.searches; SPEND.labels("web_search").inc(eusd); usd += eusd
    spend_cap.add(usd); DRAFTS.labels("done", mode).inc(); LATENCY.observe(d.latency_s + (d.judge.latency_s if d.judge else 0))
    log.info("draft", extra={"extra": {"mode": mode, "model": d.model, "composite": d.scorecard.composite if d.scorecard else None, "level": d.scorecard.standard.level if d.scorecard else None, "usd": round(usd, 4), "latency_s": round(d.latency_s, 1), "prompt_version": d.prompt_version}})
    return usd


def _check_cap() -> None:
    if not spend_cap.allow():
        CAP_REFUSALS.inc()
        raise HTTPException(status_code=429, detail={"error": "daily_spend_cap", "message": f"Daily spend cap of ${DAILY_CAP_USD:.2f} reached (${spend_cap.today():.2f} today). Resets at midnight UTC; raise DAILY_SPEND_CAP_USD to change."})


def _preflight(req: DraftRequest) -> "Completeness":
    if req.options.enrich and not ENRICH_ENABLED:
        raise HTTPException(status_code=400, detail={"error": "enrichment_disabled", "message": "Web enrichment is switched off on this deployment. Drafts use the brief only."})
    completeness = check(req.brief)
    if completeness.would_be_not_ready and not req.options.allow_not_ready:
        raise HTTPException(status_code=422, detail={"error": "brief_not_ready", "message": "This brief would produce an ad that is not ready to publish; fix the brief or pass options.allow_not_ready=true.",
                                                     "not_ready_reasons": completeness.not_ready_reasons, "suggestions": [s.model_dump() for s in completeness.suggestions[:5]]})
    _check_cap()
    return completeness


def _build_response(d, completeness, request_id: str, brief: HiringBrief) -> "DraftResponse":
    web_sources = []
    if d.enrichment:
        by_url: dict[str, list[str]] = {}
        for f in d.enrichment.facts:
            by_url.setdefault(f.url, []).append(f.text)
        web_sources = [WebSource(id=s.id, url=s.text.split("\n", 1)[0].replace("Source URL: ", ""), facts=by_url.get(s.text.split("\n", 1)[0].replace("Source URL: ", ""), [])) for s in d.sources]
    return DraftResponse(
        ad=d.ad, rendered=Rendered(markdown=render_markdown(d.ad), text=render_ad(d.ad)), scorecard=d.scorecard, brief_feedback=completeness, sources=web_sources,
        meta=DraftMeta(request_id=request_id,
                       drafter=ModelCall(model=d.model, usage=_usage(d.usage), latency_s=d.latency_s, prompt_version=d.prompt_version),
                       judge=ModelCall(model=d.judge.model, usage=_usage(d.judge.usage), latency_s=d.judge.latency_s, prompt_version=JUDGE_PROMPT_VERSION) if d.judge else None,
                       enrichment=EnrichmentMeta(model=d.enrichment.model, searches=d.enrichment.searches, facts=len(d.enrichment.facts), usage=d.enrichment.usage, latency_s=d.enrichment.latency_s,
                                                 prompt_version=d.enrichment.prompt_version, notes=d.enrichment.notes) if d.enrichment else None,
                       spec=spec.version, brief_schema=brief.schema_version),
    )


@app.get("/v1/spec")
def get_spec():
    return spec.model_dump()


def _usage(u) -> dict:
    return u.model_dump() if hasattr(u, "model_dump") else dict(u)


@app.post("/v1/scores", response_model=ScoreResponse, response_model_by_alias=True)
def post_scores(req: ScoreRequest):
    if not req.judge:
        return ScoreResponse(scorecard=score_deterministic(req.ad, req.context), meta=ScoreMeta(judge=None, spec=spec.version))
    sc, j = score(req.ad, req.context, client=client(), judge_model=req.judge_model)
    return ScoreResponse(scorecard=sc, meta=ScoreMeta(judge=ModelCall(model=j.model, usage=_usage(j.usage), latency_s=j.latency_s, prompt_version=JUDGE_PROMPT_VERSION), spec=spec.version))


class BriefCheckRequest(BaseModel):
    brief: HiringBrief


class ExtractRequest(BaseModel):
    description: str = Field(min_length=20, max_length=20000, description="The role in the author's own words: duties, requirements, pay, team, process, anything they know")
    company_name: Optional[str] = Field(default=None, description="Usually known to the client; overrides anything the text says")
    jurisdiction: str = "ZA"
    hosted_apply: bool = False
    designated_employer: Optional[bool] = None


class ExtractResponse(BaseModel):
    brief: Optional[HiringBrief] = Field(description="A valid brief, ready for /v1/drafts — or null when required fields are missing")
    brief_partial: dict = Field(description="Everything extracted, in HiringBrief shape, even when incomplete; pre-fill the form with it")
    missing_required: list[str] = Field(description="Required fields the description did not supply (title, company.name, responsibilities, must_have)")
    questions: list[str] = Field(description="Up to five questions to ask the author for the most valuable missing facts")
    completeness: Optional[Completeness] = Field(description="The /v1/briefs/check result for the extracted brief, when it is valid")
    meta: dict


@app.post("/v1/briefs/extract", response_model=ExtractResponse)
def post_brief_extract(req: ExtractRequest):
    """Free-text role description → HiringBrief (verbatim, nothing invented) + what is missing + questions to ask. One cheap model call."""
    x = extract(req.description, company_name=req.company_name, jurisdiction=req.jurisdiction, hosted_apply=req.hosted_apply, designated_employer=req.designated_employer, client=client())
    return ExtractResponse(brief=x.brief, brief_partial=x.brief_partial, missing_required=x.missing_required, questions=x.questions,
                           completeness=check(x.brief) if x.brief else None,
                           meta={"model": x.model, "usage": _usage(x.usage), "latency_s": x.latency_s, "prompt_version": EXTRACT_PROMPT_VERSION, "brief_schema": BRIEF_SCHEMA_VERSION})


@app.post("/v1/briefs/check", response_model=Completeness)
def post_brief_check(req: BriefCheckRequest):
    """Free, instant: which metrics this brief can satisfy, the composite ceiling, and which fields to add first. Call it before paying for a draft."""
    return check(req.brief)


@app.post("/v1/drafts", response_model=DraftResponse, response_model_by_alias=True, responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}, "description": "JSON by default; `?format=markdown` returns only the rendered ad as text/markdown (headers carry x-request-id and x-composite)."}})
def post_drafts(req: DraftRequest, request: Request, format: Literal["json", "markdown"] = "json"):
    completeness = _preflight(req)
    d = draft(req.brief, client=client(), model=req.options.model, effort=req.options.effort, do_score=req.options.score, judge_model=req.options.judge_model,
              do_enrich=req.options.enrich, max_searches=req.options.max_searches)
    _record(d, "sync")
    if format == "markdown":
        headers = {"x-composite": str(d.scorecard.composite) if d.scorecard else "", "x-standard": d.scorecard.standard.level if d.scorecard else "", "x-drafter-prompt": d.prompt_version, "x-spec": spec.version}
        return PlainTextResponse(render_markdown(d.ad), media_type="text/markdown; charset=utf-8", headers=headers)
    return _build_response(d, completeness, request.state.request_id, req.brief)


def _job_view(j: dict) -> DraftJob:
    return DraftJob(job_id=j["job_id"], status=j["status"], status_url=f"/v1/draft-jobs/{j['job_id']}", created_at=j["created_at"], started_at=j.get("started_at"), finished_at=j.get("finished_at"), result=j.get("result"), error=j.get("error"))


@app.post("/v1/draft-jobs", response_model=DraftJob, status_code=202)
def post_draft_job(req: DraftJobRequest, request: Request):
    """Asynchronous drafting: returns 202 with a job id immediately; poll status_url (or receive callback_url) for the /v1/drafts response."""
    completeness = _preflight(req)
    rid = request.state.request_id
    brief = req.brief

    def work() -> dict:
        d = draft(brief, client=client(), model=req.options.model, effort=req.options.effort, do_score=req.options.score, judge_model=req.options.judge_model,
                  do_enrich=req.options.enrich, max_searches=req.options.max_searches)
        _record(d, "job")
        return _build_response(d, completeness, rid, brief).model_dump(by_alias=True, mode="json")

    job = runner.submit({"brief": brief.model_dump(mode="json"), "options": req.options.model_dump()}, work, req.callback_url)
    return _job_view(job)


@app.get("/v1/draft-jobs/{job_id}", response_model=DraftJob)
def get_draft_job(job_id: str):
    j = runner.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "message": "Unknown or expired job id (jobs are kept for 24 hours)."})
    return _job_view(j)
