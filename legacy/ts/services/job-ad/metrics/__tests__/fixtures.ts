import type { JobAd } from "../types.js";

export const GOOD_AD: JobAd = {
  title: "Accounts Payable Clerk",
  company: { name: "Mzansi Logistics", about: "We move freight for 400 retailers across Gauteng and KwaZulu-Natal. Our finance team of nine keeps 1,200 suppliers paid on time." },
  summary: "You will own the supplier payment cycle for our Durban depot. You will work with the depot manager and two buyers, and report to the Finance Supervisor.",
  team: "You join a team of three clerks reporting to the Finance Supervisor in Durban.",
  responsibilities: [
    "Capture and match about 300 supplier invoices a week against purchase orders in Sage",
    "Prepare the weekly payment run for the Finance Supervisor to approve",
    "Reconcile 40 supplier statements each month and resolve queries with buyers",
    "Keep the creditors age analysis under 45 days",
  ],
  must_have: [
    "Two or more years in an accounts payable or creditors role",
    "Working knowledge of Sage or a similar accounting package",
    "Comfortable with Excel lookups and pivot tables",
  ],
  nice_to_have: ["Experience in logistics or transport", "A bookkeeping certificate"],
  pay: { min: 18000, max: 22000, currency: "ZAR", period: "month", basis: "Placement in the range depends on years of creditors experience and Sage proficiency." },
  location: "Durban, KwaZulu-Natal",
  work_mode: "onsite",
  benefits: ["Medical aid contribution of 50%", "Provident fund with 7% employer contribution", "20 days annual leave", "Transport allowance of R1,500 a month"],
  process: "Apply with your CV by 30 November 2026. We review applications weekly. Shortlisted candidates do a 30-minute phone screen, then one on-site interview with the Finance Supervisor and a short Excel exercise. Everyone hears back within three weeks of applying.",
  closing_date: "30 November 2026",
  apply_contact: "Apply at https://jobs.mzansilogistics.example/ap-clerk or email careers@mzansilogistics.example",
  accessibility_statement: "If you need any accommodation during the application process, tell us and we will arrange it.",
  ee_statement: "Mzansi Logistics is a designated employer. Preference will be given to candidates from designated groups in line with our Employment Equity plan.",
  popia_notice: "We process your personal information under POPIA only for this recruitment. Read our privacy notice at the link above.",
};

export const BAD_AD: JobAd = {
  title: "Finance Rockstar Ninja (Grade 7) – Join Our Fast-Paced Family!!!",
  company: { name: "Acme", about: "We are a dynamic, fast-paced, world-class company with cutting-edge solutions and unlimited potential for the right go-getter who can hit the ground running and think outside the box while wearing many hats in a work hard play hard culture that is like a family and demands whatever it takes from passionate self-starters who thrive under pressure and go the extra mile every single day without exception because that is who we are." },
  summary: "The ideal candidate is a young, energetic, aggressive and competitive leader. He must be a self-starter. The successful applicant will be dominant and decisive.",
  responsibilities: ["Support the team", "Various duties", "Other tasks as required"],
  must_have: ["Degree", "15+ years experience", "Own car and driver's licence", "Matric", "Must be under 35", "Able-bodied", "Native English speaker", "Available immediately"],
  nice_to_have: [],
  pay: { min: 10000, max: 40000, currency: "ZAR", period: "month" },
  location: "Johannesburg",
  work_mode: "unspecified",
  benefits: ["Competitive salary", "Market-related benefits"],
  process: undefined,
  other: "Send ID copy, photo and proof of HIV status with application.",
};

export const EMPTY_AD: JobAd = { title: "", responsibilities: [], must_have: [], nice_to_have: [], benefits: [] };
