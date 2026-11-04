"""Platform registry: what each publishing channel accepts. Limits are either `hard` (the platform rejects beyond it)
or `recommended` (performance guidance). Where a platform publishes no exact figure we use a conservative default
and say so in `notes` — treat those as ours to confirm, not the platform's word."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Fmt = Literal["html", "text", "markdown", "json_ld"]


class Limit(BaseModel):
    field: str
    max: int
    unit: Literal["chars", "words"] = "chars"
    kind: Literal["hard", "recommended"] = "hard"


class Platform(BaseModel):
    id: str
    name: str
    kind: Literal["job_board", "social", "careers_site", "feed"]
    region: str = Field(description="ZA, global, …")
    description_format: Fmt
    allowed_html_tags: list[str] = Field(default_factory=list)
    limits: list[Limit] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list, description="publish extras the client must supply, e.g. category, apply_url")
    supports_salary: bool = True
    supports_remote_flag: bool = True
    word_band: Optional[tuple[int, int]] = Field(default=None, description="recommended description length in words (matches the scorer's channel override)")
    notes: str = ""


SAFE_HTML = ["p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "h2", "h3"]

PLATFORMS: dict[str, Platform] = {p.id: p for p in [
    Platform(id="linkedin", name="LinkedIn Jobs", kind="job_board", region="global", description_format="text",
             limits=[Limit(field="title", max=200), Limit(field="description", max=300, unit="words", kind="recommended"), Limit(field="description", max=10000, kind="hard")],
             requires=["apply_url"], word_band=(150, 300),
             notes="Description is plain text; LinkedIn's own study: 1–300 words performed best. Company must be a LinkedIn Page."),
    Platform(id="indeed", name="Indeed", kind="job_board", region="global", description_format="html", allowed_html_tags=SAFE_HTML,
             limits=[Limit(field="title", max=100, kind="recommended"), Limit(field="description", max=2000, unit="words", kind="recommended"), Limit(field="description", max=20000, kind="hard")],
             requires=["apply_url"], word_band=(700, 2000),
             notes="Indeed rewards fuller descriptions (700–2000 words). Title: no ALL CAPS, no symbols, no salary in title. Hard char cap is our conservative default."),
    Platform(id="pnet", name="PNet", kind="job_board", region="ZA", description_format="html", allowed_html_tags=SAFE_HTML,
             limits=[Limit(field="title", max=120), Limit(field="description", max=8000, kind="hard")],
             requires=["category", "apply_url"], word_band=(300, 800),
             notes="Requires a PNet job category and SA province. Limits are conservative defaults pending PNet's partner spec."),
    Platform(id="careers24", name="Careers24", kind="job_board", region="ZA", description_format="html", allowed_html_tags=SAFE_HTML,
             limits=[Limit(field="title", max=120), Limit(field="description", max=8000, kind="hard")],
             requires=["category", "apply_url"], word_band=(300, 800),
             notes="Requires a Careers24 sector/category. Limits are conservative defaults pending partner spec."),
    Platform(id="careerjunction", name="CareerJunction", kind="job_board", region="ZA", description_format="html", allowed_html_tags=SAFE_HTML,
             limits=[Limit(field="title", max=120), Limit(field="description", max=8000, kind="hard")],
             requires=["category", "apply_url"], word_band=(300, 800),
             notes="Requires a category. Limits are conservative defaults pending partner spec."),
    Platform(id="careers_site", name="Own careers site (schema.org JobPosting)", kind="careers_site", region="global", description_format="json_ld", allowed_html_tags=SAFE_HTML,
             limits=[Limit(field="title", max=200, kind="recommended")], requires=["apply_url"], word_band=(300, 650),
             notes="HTML page + JobPosting JSON-LD so Google for Jobs indexes it. validThrough from the closing date; datePosted set at publish time."),
    Platform(id="social_teaser", name="Social post (LinkedIn/Facebook/X/WhatsApp)", kind="social", region="global", description_format="text",
             limits=[Limit(field="teaser", max=280, kind="recommended"), Limit(field="teaser", max=2000, kind="hard")],
             requires=["apply_url"], supports_salary=True, supports_remote_flag=False, word_band=None,
             notes="A one- to three-sentence teaser plus the link. 280 chars keeps it X-safe; others allow more."),
    Platform(id="generic_text", name="Plain text (email, WhatsApp broadcast, print)", kind="feed", region="global", description_format="text",
             limits=[], requires=[], word_band=(300, 650), notes="The full ad as plain text."),
]}
