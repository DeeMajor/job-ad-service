"""Web enrichment (Phase 2): public employer context from the web, cited, as extra SOURCE blocks for the drafter and judge.

Rule: the web may supply public employer context — about/mission, values, locations, benefits the employer itself publishes,
culture and awards. It may NEVER supply pay or legal statements (EE, POPIA, accessibility); those come only from the brief.
Everything returned carries the URL it came from so the recruiter can confirm it.

Implementation: one Sonnet call with Anthropic's server-side web_search tool (restricted to the employer's domain when known)
and a structured output. Server tools may pause the turn after 10 internal iterations; we resume up to MAX_CONTINUATIONS times.

Tool version: the basic `web_search_20250305`, deliberately. The `web_search_20260209` "dynamic filtering" variant runs search
inside a code sandbox; with a small max_uses the model's filtering code exhausts the cap, gets "server tool use limit exceeded",
and loops on retries (observed: 67k–121k input tokens per call and zero facts despite successful searches). The basic tool
returns results directly in one pass.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import anthropic
from pydantic import BaseModel, Field

from ..metrics.types import Source
from .brief import HiringBrief

ENRICH_PROMPT_VERSION = "0.1.1"
WEB_SEARCH_TOOL = "web_search_20250305"
MAX_CONTINUATIONS = 3


class Fact(BaseModel):
    text: str = Field(description="One factual sentence about the employer, in the employer's own terms, as published")
    url: str = Field(description="The page it came from")
    kind: str = Field(description="about | values | locations | benefits | culture | awards | other")


class EmployerFacts(BaseModel):
    facts: list[Fact] = Field(description="Only facts the pages state. Empty if nothing reliable was found.")
    notes: str = Field(description="One sentence on what was searched and how confident the result is")


ENRICH_SYSTEM = """You research an employer's public web presence to give a job-ad writer accurate context. Return only facts that the pages you read actually state, each with its URL.

Collect, if published: what the company does and for whom; its mission or values in its own words; office locations; benefits and perks it lists for employees; culture statements; notable awards or certifications.

Never collect: salaries or pay ranges, Employment Equity / affirmative-action statements, POPIA or privacy notices, accessibility statements, or anything about a specific vacancy. Those come from the hiring team only.

Prefer the employer's own site over third parties. Do not infer or embellish. If a page is a job board or an unrelated company with a similar name, ignore it. Keep facts to one sentence each; at most 12 facts.

You have a small, fixed number of searches. Plan them (about us; careers or benefits; values or awards), run them once each, then write up what the results contain. Do not retry a search that returns an error; use what you have."""


def _domain(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    u = website if re.match(r"^https?://", website) else f"https://{website}"
    host = urlparse(u).hostname or ""
    return host[4:] if host.startswith("www.") else host or None


@dataclass
class Enrichment:
    facts: list[Fact]
    sources: list[Source]
    notes: str
    searches: int
    usage: Any
    latency_s: float
    model: str
    prompt_version: str = ENRICH_PROMPT_VERSION
    continuations: int = 0


def enrich(brief: HiringBrief, *, client: Optional[anthropic.Anthropic] = None, model: str = "claude-sonnet-5", max_searches: int = 3) -> Enrichment:
    client = client or anthropic.Anthropic()
    domain = _domain(getattr(brief.company, "website", None))
    tool: dict = {"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches}
    if domain:
        tool["allowed_domains"] = [domain]
    query = f"Employer: {brief.company.name}" + (f" (website {domain})" if domain else "") + (f". Location of this role: {brief.location}" if brief.location else "") + ". Find public employer context for a job advertisement."
    messages: list[dict] = [{"role": "user", "content": query}]
    t0 = time.time()
    continuations = 0
    usage_total: dict[str, int] = {}
    while True:
        res = client.messages.parse(
            model=model, max_tokens=2500,  # hard cap: a misbehaving search loop must not run up the bill
            tools=[tool], output_format=EmployerFacts,
            system=[{"type": "text", "text": ENRICH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        for k, v in res.usage.model_dump().items():
            if isinstance(v, int):
                usage_total[k] = usage_total.get(k, 0) + v
        if res.stop_reason == "pause_turn" and continuations < MAX_CONTINUATIONS:
            messages = [messages[0], {"role": "assistant", "content": res.content}]
            continuations += 1
            continue
        break
    latency = time.time() - t0
    parsed: EmployerFacts | None = res.parsed_output
    facts = parsed.facts if parsed else []
    # drop anything that smells like pay or a legal statement even if the model slipped
    banned = re.compile(r"\b(salary|salaries|pay range|per month|per annum|R\s?\d{2,3}[ ,]?\d{3}|employment equity|affirmative action|designated group|POPIA|personal information|accommodation)\b", re.I)
    facts = [f for f in facts if not banned.search(f.text)]
    if domain:
        facts = [f for f in facts if domain in (urlparse(f.url).hostname or "")] or facts  # prefer on-domain; keep all if none on-domain
    by_url: dict[str, list[str]] = {}
    for f in facts:
        by_url.setdefault(f.url, []).append(f"[{f.kind}] {f.text}")
    sources = [Source(id=f"web:{i + 1}", text=f"Source URL: {url}\n" + "\n".join(lines)) for i, (url, lines) in enumerate(by_url.items())]
    searches = usage_total.get("server_tool_use", 0) if isinstance(usage_total.get("server_tool_use"), int) else 0
    try:
        searches = res.usage.server_tool_use.web_search_requests if res.usage.server_tool_use else searches
    except AttributeError:
        pass
    return Enrichment(facts=facts, sources=sources, notes=parsed.notes if parsed else "", searches=searches, usage=usage_total, latency_s=latency, model=res.model, continuations=continuations)


def render_sources(sources: list[Source]) -> str:
    """Extra SOURCE blocks appended to the drafter's input (the brief stays SOURCE 'brief')."""
    return "\n\n".join(f'<SOURCE id="{s.id}">\n{s.text}\n</SOURCE>' for s in sources)
