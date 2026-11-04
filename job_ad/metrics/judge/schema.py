"""Judge output. Counts and ratios are never asked for directly: the judge enumerates items and code does the
arithmetic. Pass/fail metrics use `pass`. No Optional/Union fields: the API caps union-typed parameters at 16."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PassFail(BaseModel):
    pass_: bool = Field(alias="pass")
    evidence: list[str] = Field(description="Short quoted spans from the ad that justify the verdict")
    reasoning: str = Field(description="One sentence")

    model_config = {"populate_by_name": True}


class Responsibilities(BaseModel):
    total: int = Field(description="Number of responsibility bullets in the ad")
    concrete: list[str] = Field(description="Bullets that contain BOTH a specific activity verb (prepare, reconcile, call, repair, approve…) AND a specific object (which report, which customers, which system). Category labels ('Customer Experience', 'Risk Management'), outcomes without activity ('Ensure compliance'), and vague verbs ('support', 'assist', 'contribute') are NOT concrete. Quote each concrete bullet.")
    reasoning: str


class SpecificRequirement(BaseModel):
    requirement: str = Field(description="The must-have, quoted")
    supporting_responsibility: str = Field(description='The stated responsibility that names the activity this requirement serves, quoted; "" if none does')


class SpecificRequirements(BaseModel):
    items: list[SpecificRequirement] = Field(description="Only SPECIFIC must-haves: named tools, systems, certifications, licences, languages, domain skills, regulatory prerequisites. EXCLUDE generic education levels (matric, FETC, degree, postgraduate), years-of-experience bands, and soft traits (attention to detail, communication) — those are measured elsewhere. Regulatory prerequisites the ad names as such (FAIS fit-and-proper, SANC registration) are supported by any duty in that regulated activity.")
    reasoning: str


class UnsupportedClaim(BaseModel):
    claim: str
    sentence: str


class Grounding(BaseModel):
    factual_claims_total: int = Field(description="Number of factual claims about employer, pay, benefits, location, work mode, team, process or legal status. 0 if no SOURCE blocks were provided.")
    unsupported_claims: list[UnsupportedClaim] = Field(description="Claims no SOURCE block states. Empty if no SOURCE blocks were provided.")
    reasoning: str


class ProxyRequirements(BaseModel):
    items: list[str] = Field(description="Requirements that would exclude a protected group (EEA s6: age, disability, family responsibility, language, origin, religion, gender, HIV status…) without being an inherent requirement of the work described: e.g. driving licence or own vehicle for a desk role, age ranges, a maximum years-of-experience ceiling, 'recent graduate', physical fitness for sedentary work, citizenship where no legal need is stated, a home language rather than a proficiency. NOT proxies: credit and criminal checks or FAIS fit-and-proper for regulated financial roles, a professional registration the work legally requires, a proficiency in a language the duties use. Quote each. Empty array if none.")
    reasoning: str


class TeamContext(BaseModel):
    reports_to: str = Field(description='The job title or role this person REPORTS TO, quoted from the ad (e.g. "Finance Supervisor", "Head of Retail Credit"); "" if the ad never states who the person reports to. Teams the person leads, works with or sits in do NOT count.')
    team_size: str = Field(description='A stated NUMBER of people in the immediate team this person joins or leads, quoted (e.g. "team of six", "12 consultants"); "" if no number is given. "Squads", "tribes", "DevOps team", "a team of consultants" without a number do NOT count.')
    reasoning: str


class WhyThisRole(BaseModel):
    role_specific_draw: str = Field(description='Quote the ONE sentence that tells the candidate what THEY get from THIS role: something they will own or be accountable for ("you will own the weekly payment run"), build or change ("build and grow the Islamic banking franchise"), LEARN or be trained in ("you will be trained and accredited as a financial adviser", "you learn the full claims cycle"), a qualification or accreditation they gain, or a path they grow into ("a path to team lead within two years"). Any ONE of these qualifies — learning and accreditation count as much as ownership. "" only if no sentence offers the candidate any of these. Sentences about the employer in general ("exciting opportunity", "dynamic environment", "make a difference", company history, values) do NOT qualify.')
    reasoning: str


class JudgeOutput(BaseModel):
    title_matches_content: PassFail = Field(description="PASS if the job title names the same occupation the responsibilities describe. FAIL if a reader of the title would expect materially different work (e.g. title 'Boilermaker', duties are accounts payable).")
    responsibilities: Responsibilities
    specific_requirements: SpecificRequirements
    pay_context_present: PassFail = Field(description="If pay is disclosed, the ad says what determines placement in the range. FAIL if no pay disclosed.")
    grounding: Grounding
    proxy_requirements: ProxyRequirements
    protected_grounds_ok: PassFail = Field(description="PASS if no stated or implied preference/exclusion on race, gender, sex, pregnancy, marital status, family responsibility, ethnic or social origin, colour, sexual orientation, age, disability, religion, HIV status, conscience, belief, political opinion, culture, language, birth, unless an inherent requirement is stated and justified. A lawful Employment Equity preference statement is PASS.")
    no_prohibited_requests: PassFail = Field(description="PASS if the ad does not ask applicants for HIV status, pregnancy, criminal record (unless inherent and stated), photograph, ID number, marital status, religion, or medical information at application stage")
    why_this_role: WhyThisRole
    evp_benefits_specific: PassFail = Field(description="Benefits are concrete (named items, amounts, days) rather than 'competitive' or 'market-related'")
    team_context: TeamContext
    evp_work_mode_clarity: PassFail = Field(description="Remote/hybrid/on-site and expected office days (if hybrid) are unambiguous")
    process_steps_and_timeline: PassFail = Field(description="Application steps, number or type of interview rounds, and a response or closing date are stated")


JUDGE_METRIC_IDS = [
    "structure.title_matches_content", "specific.responsibility_concreteness", "specific.requirement_traceability", "pay.context_present",
    "honesty.grounding", "inclusive.proxy_requirements", "compliance.protected_grounds", "compliance.no_prohibited_requests",
    "evp.why_this_role", "evp.benefits_specific", "evp.team_context", "evp.work_mode_clarity", "process.steps_and_timeline",
]
