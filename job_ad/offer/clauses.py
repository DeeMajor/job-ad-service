"""Clause library: fixed wording with slots, one plain-language explanation per clause (BCEA s29(3)).

TEMPLATE WORDING — to be reviewed once by a labour practitioner before any real contract is issued (planning pack, 02 §"What a person
must do once"). The model (Phase 1) fills and explains these clauses; it does not write new ones. Identity is placeholders only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..drafter.brief import HiringBrief
from .rules import annual_equivalent, consecutive_leave_days, hourly_equivalent, load_rules
from .terms import OfferRequest, Terms

CLAUSES_VERSION = "0.1.0"
PLACEHOLDERS = ["employee.full_name", "employee.id_number", "employee.address", "employer.signatory", "date_signed"]


@dataclass
class Clause:
    id: str
    heading: str
    text: str
    particular: Optional[str] = None       # BCEA s29 reference this clause satisfies
    explanation: str = ""                  # plain language, s29(3)
    source: str = "template"               # template | model


def _d(x: date) -> str:
    return x.strftime("%-d %B %Y")


def _money(v: float, cur: str = "ZAR") -> str:
    return f"{'R' if cur == 'ZAR' else cur + ' '}{v:,.2f}"


def _period_word(p: str) -> str:
    return {"hour": "per hour", "day": "per day", "week": "per week", "month": "per month", "year": "per year"}[p]


def _notice_ladder() -> str:
    return ("one week if the employee has been employed for six months or less; two weeks if employed for more than six months but not more "
            "than one year; four weeks if employed for more than one year")


def build_contract_clauses(req: OfferRequest, threshold_applies: bool) -> list[Clause]:
    t, b = req.terms, req.brief
    R = load_rules()
    co = b.company.name
    hourly = hourly_equivalent(t)
    C: list[Clause] = []

    C.append(Clause("parties", "Parties", f"This contract of employment is entered into between {co}" + (f" (registration number {t.employer.registration_number})" if t.employer.registration_number else "") +
                    f", of {t.employer.address or '[employer address — required]'} (the Employer), and {{{{employee.full_name}}}}, identity number {{{{employee.id_number}}}}, of {{{{employee.address}}}} (the Employee).",
                    "s29(1)(a)-(b)", f"This contract is between {co} and you."))
    C.append(Clause("position", "Position and duties", f"The Employer appoints the Employee as {b.title}. The Employee's duties include: " + "; ".join(b.responsibilities) +
                    ". The Employer may reasonably require the Employee to perform other duties consistent with the position.", "s29(1)(c)",
                    f"Your job title is {b.title}. Your main duties are listed here; you may be asked to do other reasonable work that fits the job."))
    if t.contract_type == "fixed_term":
        reason = f" The contract is for a fixed term because: {t.fixed_term.justification}." if t.fixed_term.justification else ""
        C.append(Clause("term", "Commencement and duration", f"Employment commences on {_d(t.start_date)} and terminates automatically on {_d(t.fixed_term.end_date)}, without notice from either party.{reason}"
                        " The Employee has no expectation of renewal or of permanent employment beyond that date.", "s29(1)(e),(n)",
                        f"You start on {_d(t.start_date)}. The job ends on {_d(t.fixed_term.end_date)}; nobody has to give notice for it to end." + (f" The reason it is a fixed term: {t.fixed_term.justification}." if t.fixed_term.justification else "")))
    else:
        kind = {"permanent": "on a permanent basis", "part_time": "on a permanent part-time basis", "temporary": "on a temporary basis", "learnership": "under a learnership agreement", "internship": "as an intern"}[t.contract_type]
        C.append(Clause("term", "Commencement", f"Employment commences on {_d(t.start_date)} {kind}.", "s29(1)(e)", f"You start on {_d(t.start_date)}."))
    if t.probation_months:
        C.append(Clause("probation", "Probation", f"The first {t.probation_months} month(s) of employment are a probationary period during which the Employer will assess the Employee's performance against the requirements of the position and give reasonable evaluation, instruction, training, guidance or counselling where needed. "
                        "Confirmation, extension or termination at the end of probation will follow a fair procedure.", None,
                        f"For the first {t.probation_months} month(s) you are on probation. You will get feedback and support; a decision to confirm, extend or end your employment must follow a fair process."))
    C.append(Clause("place_of_work", "Place of work", f"The Employee's place of work is {t.place_of_work}." + (" The Employee may be required to work at other places of business of the Employer from time to time." if t.various_places else ""),
                    "s29(1)(d)", f"You work at {t.place_of_work}." + (" You may sometimes be asked to work at other company sites." if t.various_places else "")))
    hrs = f"The Employee's ordinary hours of work are {t.hours.per_week:g} hours per week, {t.hours.daily:g} hours per day over {t.hours.days_per_week} days per week" + (f" ({t.hours.schedule})" if t.hours.schedule else "") + "."
    meal = f" A meal interval of {t.hours.meal_interval_min} minutes is taken after no more than five hours of continuous work." if t.hours.meal_interval_min else " A meal interval of at least 60 minutes is taken after no more than five hours of continuous work."
    if threshold_applies:
        hrs += meal + " The Employee is entitled to a daily rest period of at least 12 consecutive hours and a weekly rest period of at least 36 consecutive hours."
        expl = f"You work {t.hours.per_week:g} hours a week over {t.hours.days_per_week} days, with a meal break and guaranteed daily and weekly rest."
    else:
        hrs += " The Employee's remuneration exceeds the earnings threshold published under section 6(3) of the Basic Conditions of Employment Act; the provisions of that Act regulating ordinary hours, overtime, meal intervals and Sunday and public-holiday pay accordingly do not apply, and the hours above are the agreed hours."
        expl = f"You work {t.hours.per_week:g} hours a week over {t.hours.days_per_week} days. Because your pay is above the legal earnings threshold, the law's limits on hours and overtime pay do not apply; the hours here are what we have agreed."
    C.append(Clause("hours", "Hours of work", hrs, "s29(1)(f)", expl))
    pay = f"The Employee will be paid {_money(t.pay.amount, t.pay.currency)} {_period_word(t.pay.period)}" + (f" ({t.pay.basis})" if t.pay.basis else "") + f", equivalent to {_money(hourly)} per ordinary hour, payable {t.pay.period}ly" + (f" on the {t.pay.pay_day}" if t.pay.pay_day else "") + (f" by {t.pay.method}" if t.pay.method else "") + "."
    pay += (" Other cash payments: " + "; ".join(t.pay.other_payments) + ".") if t.pay.other_payments else " No other cash payments are payable."
    pay += (" Payments in kind: " + "; ".join(f"{p.description} (value {_money(p.value_zar) if p.value_zar is not None else '[value required]'})" for p in t.pay.payments_in_kind) + ".") if t.pay.payments_in_kind else " No payments in kind are made."
    C.append(Clause("remuneration", "Remuneration", pay, "s29(1)(g),(i),(j),(k)", f"You earn {_money(t.pay.amount, t.pay.currency)} {_period_word(t.pay.period)}, paid {t.pay.period}ly" + (f" on the {t.pay.pay_day}" if t.pay.pay_day else "") + ". " +
                    ("You also get: " + "; ".join(t.pay.other_payments) + "." if t.pay.other_payments else "There are no extra cash payments.")))
    if threshold_applies:
        ot = t.pay.overtime_rate if t.pay.overtime_rate is not None else 1.5
        C.append(Clause("overtime", "Overtime", f"Overtime is worked only by agreement and may not exceed ten hours in any week. Overtime is paid at {ot:g} times the Employee's ordinary hourly wage, or, by agreement, compensated with paid time off. Work on a Sunday is paid at double the ordinary wage (or one and a half times if the Employee ordinarily works on Sundays), and work on a public holiday at double the ordinary wage.",
                        "s29(1)(h)", f"Overtime is voluntary and limited to 10 hours a week. You are paid {ot:g} times your normal hourly rate for it, or you can agree to take paid time off instead. Sundays and public holidays pay double."))
    ded = ("The following deductions will be made from the Employee's remuneration: " + "; ".join(t.deductions) + ".") if t.deductions else "No deductions other than those required by law will be made from the Employee's remuneration."
    ded += " No other deduction will be made without the Employee's written agreement in respect of a specific debt, or as required by law, a court order or an arbitration award."
    C.append(Clause("deductions", "Deductions", ded, "s29(1)(l)", ("These amounts come off your pay: " + "; ".join(t.deductions) + ". " if t.deductions else "Only deductions the law requires come off your pay. ") + "Nothing else can be deducted unless you agree in writing to a specific debt, or a court or arbitrator orders it."))
    cons = consecutive_leave_days(t)
    annual_txt = (f"{t.leave.annual_days:g} {t.leave.annual_basis.replace('_', ' ')} of paid annual leave per annual leave cycle of 12 months" if t.leave.annual_days is not None else "paid annual leave of 21 consecutive days per annual leave cycle of 12 months")
    leave = (f"The Employee is entitled to {annual_txt}, to be taken at a time agreed with the Employer and not later than six months after the end of the cycle. "
             f"Sick leave: {t.leave.sick_cycle_days if t.leave.sick_cycle_days is not None else (36 if t.hours.days_per_week >= 6 else 30):g} days' paid sick leave in every 36-month cycle (during the first six months, one day for every 26 days worked); a medical certificate may be required for absences of more than two consecutive days or on more than two occasions in eight weeks. "
             f"Maternity leave: at least {t.leave.maternity_months if t.leave.maternity_months is not None else 4:g} consecutive months. Parental leave: {t.leave.parental_days if t.leave.parental_days is not None else 10:g} consecutive days. Adoption and commissioning parental leave as provided in the Act. "
             f"Family responsibility leave: {t.leave.family_responsibility_days if t.leave.family_responsibility_days is not None else 3:g} days' paid leave per year once employed for longer than four months and for at least four days a week.")
    C.append(Clause("leave", "Leave", leave, "s29(1)(m)", f"You get {annual_txt}. You get paid sick leave, maternity leave of at least four months, parental leave of ten days, and family responsibility leave for family emergencies. The exact amounts are in this clause."))
    if t.contract_type != "fixed_term":
        if t.notice.statutory_ladder or t.notice.weeks is None:
            nt = f"Either party may terminate this contract on written notice of {_notice_ladder()}."
            ne = "To end the contract, you or the company must give written notice: one week in your first six months, two weeks up to one year, and four weeks after a year."
        else:
            nt = f"Either party may terminate this contract on {t.notice.weeks:g} weeks' written notice, which is not less than the notice required by the Basic Conditions of Employment Act."
            ne = f"To end the contract, you or the company must give {t.notice.weeks:g} weeks' written notice."
        nt += " Notice may not be given during any period of leave. Nothing in this clause prevents the Employer from terminating employment summarily for a fair reason following a fair procedure, or the parties from agreeing to waive notice."
        C.append(Clause("termination", "Termination and notice", nt, "s29(1)(n)", ne + " Notice cannot be given while you are on leave."))
    council = (f"The Employer's business falls within the registered scope of the {t.bargaining_council}, whose collective agreements apply to this employment." if t.bargaining_council else
               (f"The Employer's business is covered by the sectoral determination for the {t.sector.replace('_', ' ')} sector, whose provisions apply where they are more favourable than this contract." if t.sector != "none" else
                "No bargaining council agreement or sectoral determination applies to the Employer's business."))
    C.append(Clause("council_or_sd", "Bargaining council or sectoral determination", council, "s29(1)(o)",
                    "Some industries have extra rules from a bargaining council or a sectoral determination. " + ("This one applies to you: " + (t.bargaining_council or t.sector.replace("_", " ")) + "." if (t.bargaining_council or t.sector != "none") else "None applies to this job.")))
    if t.prior_service:
        C.append(Clause("prior_service", "Prior service", f"The following period of employment with a previous employer counts towards the Employee's period of employment with the Employer: {t.prior_service}.", "s29(1)(p)", f"This earlier service counts towards your years of service here: {t.prior_service}."))
    if t.clauses.confidentiality:
        C.append(Clause("confidentiality", "Confidentiality", "The Employee will not, during or after employment, disclose or use any confidential information of the Employer, its clients or suppliers, except as required to perform the Employee's duties or by law.", None,
                        "You must keep company and client information private, during and after your employment, unless your job or the law requires you to share it."))
    if t.clauses.ip_assignment:
        C.append(Clause("ip_assignment", "Intellectual property", "All intellectual property created by the Employee in the course and scope of employment vests in the Employer, and the Employee will sign any document reasonably required to give effect to this.", None,
                        "Work you create as part of your job belongs to the company."))
    r = t.clauses.restraint_of_trade
    if r:
        C.append(Clause("restraint_of_trade", "Restraint of trade", f"For {r.months} month(s) after termination of employment, the Employee will not" + (f", within {r.area}," if r.area else "") +
                        " be employed by or hold an interest in any business that competes with the Employer in the business in which the Employee was engaged, nor solicit the Employer's clients or employees with whom the Employee dealt in the last twelve months of employment. The Employee acknowledges this restraint protects the Employer's confidential information and client connections and is reasonable in duration and area.", None,
                        f"For {r.months} month(s) after you leave" + (f", in {r.area}," if r.area else "") + " you may not work for a direct competitor or approach the company's clients or staff you dealt with."))
    if t.clauses.retirement_age:
        C.append(Clause("retirement", "Retirement", f"The Employee's normal retirement age is {t.clauses.retirement_age}, on reaching which this contract terminates.", None, f"Your normal retirement age is {t.clauses.retirement_age}."))
    docs = ("The following documents form part of this contract and copies may be obtained from the Employer's human resources office: " + "; ".join(t.documents) + ".") if t.documents else "No other documents form part of this contract."
    C.append(Clause("documents", "Other documents", docs, "s29(1)(q)", ("These other documents are part of your contract; HR can give you copies: " + "; ".join(t.documents) + "." if t.documents else "No other documents form part of this contract.")))
    C.append(Clause("general", "General", "This contract records the whole agreement between the parties on its subject; any amendment must be in writing and signed by both parties. Where any term is less favourable to the Employee than the Basic Conditions of Employment Act or an applicable sectoral determination or collective agreement, the more favourable provision applies. The Employer will keep these particulars for three years after termination and will explain them to the Employee on request.", "s29(3)-(4)",
                    "This document is the whole agreement; changes must be in writing. If any part gives you less than the law does, the law wins. You can ask to have anything in it explained."))
    C.append(Clause("signatures", "Signatures", "Signed at ____________ on {{date_signed}}.\n\nFor the Employer: {{employer.signatory}}  ____________________\n\nThe Employee: {{employee.full_name}}  ____________________", None,
                    "Both you and the company's representative sign and date the contract."))
    return C


def build_offer_clauses(req: OfferRequest) -> list[Clause]:
    t, b, o = req.terms, req.brief, req.offer
    C: list[Clause] = []
    C.append(Clause("opening", "Offer of employment", f"Dear {{{{employee.full_name}}}},\n\n{b.company.name} is pleased to offer you the position of {b.title}, starting on {_d(t.start_date)}" +
                    (f" for a fixed term ending {_d(t.fixed_term.end_date)}" if t.fixed_term else "") + f", based at {t.place_of_work}.", None, "This letter offers you the job."))
    C.append(Clause("terms", "Key terms", f"Remuneration: {_money(t.pay.amount, t.pay.currency)} {_period_word(t.pay.period)}" + (f" ({t.pay.basis})" if t.pay.basis else "") + ". " +
                    f"Hours: {t.hours.per_week:g} per week" + (f", {t.hours.schedule}" if t.hours.schedule else "") + ". " +
                    (f"Probation: {t.probation_months} month(s). " if t.probation_months else "") +
                    (f"Annual leave: {t.leave.annual_days:g} {t.leave.annual_basis.replace('_', ' ')}. " if t.leave.annual_days is not None else "") +
                    (("Other benefits: " + "; ".join(t.pay.other_payments) + ". ") if t.pay.other_payments else "") +
                    "Full particulars are in the attached contract of employment.", None, "The main points of the offer; the contract has all the details."))
    cond = "This offer is conditional on " + ("; ".join(f"your providing {d}" for d in o.documents_required) if o.documents_required else "the signing of the attached contract") + "."
    if o.expires:
        cond += f" Please accept in writing by {_d(o.expires)}, after which the offer lapses."
    if o.contact:
        cond += f" Questions: {o.contact}."
    C.append(Clause("conditions", "Conditions and acceptance", cond, None, "What you need to send us and by when."))
    C.append(Clause("sign", "Acceptance", "I accept this offer on the terms set out above and in the attached contract.\n\n{{employee.full_name}}  ____________________  Date: {{date_signed}}", None, "Sign here to accept."))
    return C


def render_markdown(title: str, clauses: list[Clause]) -> str:
    out = [f"# {title}", ""]
    for i, c in enumerate(clauses, 1):
        out += [f"## {i}. {c.heading}", "", c.text, ""]
    return "\n".join(out).strip() + "\n"
