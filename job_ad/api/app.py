"""Headless job-ad service (FastAPI). No UI.

    PORT=4310 .venv/bin/uvicorn job_ad.api.app:app --host 127.0.0.1 --port 4310

  GET  /healthz                 → { ok, versions }
  GET  /v1/spec                 → the metric spec
  POST /v1/scores  { ad, context?, judge?, judge_model? }   → { scorecard, meta }   judge=false is free (deterministic only)
  POST /v1/drafts  { brief, options? }                      → { ad, scorecard, meta } one Opus call + one judge call
OpenAPI at /docs and /openapi.json. Errors: 422 validation (FastAPI), 502 upstream model API, 500.
"""
from __future__ import annotations

import os
import uuid
from typing import Literal, Optional

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

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

spec = load_spec()
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
    return {"ok": True, "versions": {"spec": spec.version, "judge_prompt": JUDGE_PROMPT_VERSION, "drafter_prompt": DRAFTER_PROMPT_VERSION, "brief_schema": BRIEF_SCHEMA_VERSION}, "features": {"enrichment": ENRICH_ENABLED}}


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
    if req.options.enrich and not ENRICH_ENABLED:
        raise HTTPException(status_code=400, detail={"error": "enrichment_disabled", "message": "Web enrichment is switched off on this deployment. Drafts use the brief only."})
    completeness = check(req.brief)
    if completeness.would_be_not_ready and not req.options.allow_not_ready:
        raise HTTPException(status_code=422, detail={"error": "brief_not_ready", "message": "This brief would produce an ad that is not ready to publish; fix the brief or pass options.allow_not_ready=true.",
                                                     "not_ready_reasons": completeness.not_ready_reasons, "suggestions": [s.model_dump() for s in completeness.suggestions[:5]]})
    d = draft(req.brief, client=client(), model=req.options.model, effort=req.options.effort, do_score=req.options.score, judge_model=req.options.judge_model,
              do_enrich=req.options.enrich, max_searches=req.options.max_searches)
    web_sources = []
    if d.enrichment:
        by_url: dict[str, list[str]] = {}
        for f in d.enrichment.facts:
            by_url.setdefault(f.url, []).append(f.text)
        web_sources = [WebSource(id=s.id, url=s.text.split("\n", 1)[0].replace("Source URL: ", ""), facts=by_url.get(s.text.split("\n", 1)[0].replace("Source URL: ", ""), [])) for s in d.sources]
    if format == "markdown":
        headers = {"x-composite": str(d.scorecard.composite) if d.scorecard else "", "x-standard": d.scorecard.standard.level if d.scorecard else "", "x-drafter-prompt": d.prompt_version, "x-spec": spec.version}
        return PlainTextResponse(render_markdown(d.ad), media_type="text/markdown; charset=utf-8", headers=headers)
    return DraftResponse(
        ad=d.ad, rendered=Rendered(markdown=render_markdown(d.ad), text=render_ad(d.ad)), scorecard=d.scorecard, brief_feedback=completeness, sources=web_sources,
        meta=DraftMeta(request_id=request.state.request_id,
                       drafter=ModelCall(model=d.model, usage=_usage(d.usage), latency_s=d.latency_s, prompt_version=d.prompt_version),
                       judge=ModelCall(model=d.judge.model, usage=_usage(d.judge.usage), latency_s=d.judge.latency_s, prompt_version=JUDGE_PROMPT_VERSION) if d.judge else None,
                       enrichment=EnrichmentMeta(model=d.enrichment.model, searches=d.enrichment.searches, facts=len(d.enrichment.facts), usage=d.enrichment.usage, latency_s=d.enrichment.latency_s,
                                                 prompt_version=d.enrichment.prompt_version, notes=d.enrichment.notes) if d.enrichment else None,
                       spec=spec.version, brief_schema=req.brief.schema_version),
    )
