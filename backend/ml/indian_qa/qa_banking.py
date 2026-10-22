"""Author-written Indian finance Q/A — UPI, EPF/PPF/NPS, credit score, loans & EMI, deposits, RBI (part 2 of 3).

Rows: (topic, question, answer, source_note). EMI / FD / RD / PPF numbers were computed with the standard formulas
(the same ones in backend/app/agent/tools/calculators.py) before being written down.
"""
from __future__ import annotations

ROWS: list[tuple[str, str, str, str]] = [
    # ── UPI limits and failed transactions ──────────────────────────────────
    ("upi", "What is the UPI transaction limit per day?",
     "For person-to-person payments NPCI caps a single UPI transaction at ₹1 lakh and most banks cap the day at ₹1 lakh "
     "(some allow only ₹5,000–25,000 in the first 24 hours after you register a new device). Verified merchant categories "
     "have higher caps — up to ₹2 lakh for several, and ₹5 lakh per transaction for hospitals, education, IPO applications, "
     "tax payments, insurance, capital-market and credit-card bill payments after NPCI's September 2025 revision (with daily "
     "caps of ₹6–10 lakh in those categories). Your bank or app may apply lower limits.",
     "NPCI UPI limit circulars (incl. Sept 2025 P2M revision); bank-specific limits apply"),
    ("upi", "UPI limit per day?",
     "Typically ₹1 lakh per day for sending money to people (₹1 lakh per transaction), set by NPCI and your bank; new devices "
     "are often restricted for the first 24 hours. Paying merchants in categories like hospitals, education, taxes, IPOs and "
     "insurance can go up to ₹5 lakh per transaction. Check your bank app for its own cap.",
     "NPCI UPI limits; bank app settings"),
    ("upi", "What is the UPI Lite limit?",
     "UPI Lite is an on-device wallet for small payments without a PIN: ₹1,000 per transaction and a wallet balance of up to "
     "₹5,000 (raised by RBI in December 2024), with ₹5,000 of daily top-ups. UPI Lite X also works offline between two phones "
     "via NFC.",
     "RBI circular Dec 2024 on UPI Lite; NPCI UPI Lite product note"),
    ("upi", "What happens if a UPI payment fails but money is debited?",
     "Usually the bank reverses it automatically. RBI's turnaround-time rule says a failed UPI transaction where the "
     "beneficiary was not credited must be auto-reversed within one working day (T+1); if not, the bank owes you ₹100 per day "
     "of delay. Check the transaction status in your UPI app first (it can show 'pending' for up to 48 hours), then raise a "
     "dispute in the app or with your bank, and escalate to the RBI Ombudsman at cms.rbi.org.in if it is not resolved in "
     "30 days.",
     "RBI circular DPSS.CO.PD No.629 (19 Sept 2019) on TAT and compensation"),
    ("upi", "Money debited but UPI failed, what now?",
     "Wait for the status to settle (many 'pending' payments complete or reverse within hours), then raise a complaint in "
     "the UPI app ('report an issue' on that transaction) quoting the UPI reference number. The bank must auto-reverse within "
     "T+1 working day or pay ₹100 per day compensation. If nothing happens in 30 days, complain to the RBI Integrated "
     "Ombudsman at cms.rbi.org.in.",
     "RBI TAT harmonisation circular (2019); RBI Integrated Ombudsman Scheme 2021"),
    ("upi", "I sent money to the wrong UPI ID — can I get it back?",
     "A successful UPI payment cannot be reversed by the bank without the receiver's consent. Immediately contact your bank or "
     "the UPI app and ask them to request the receiver's bank; also call the NPCI/bank helpline. If the receiver refuses, you "
     "can complain to the RBI Ombudsman and file a police complaint, but recovery is not guaranteed — always verify the name "
     "shown before paying.",
     "NPCI dispute process; RBI Ombudsman"),
    ("upi", "What is UPI AutoPay?",
     "A recurring e-mandate on UPI for subscriptions, SIPs, EMIs and bills. You approve the mandate once with your PIN; "
     "debits up to ₹15,000 then run without a PIN (₹1 lakh for mutual funds, insurance premiums and credit-card bills), with "
     "a pre-debit notification 24 hours earlier. You can pause or revoke the mandate in the app.",
     "RBI e-mandate framework; NPCI UPI AutoPay limits"),
    ("upi", "Is UPI free?",
     "Yes for customers — banks and apps cannot charge you for UPI payments from a bank account. Since April 2023 an "
     "interchange of up to 1.1% applies to merchant payments above ₹2,000 made from prepaid wallets, but it is paid by the "
     "merchant, not the payer.",
     "NPCI circular on PPI interchange (March 2023); RBI/DoR zero-MDR policy"),
    ("upi", "What is a UPI PIN and VPA?",
     "The Virtual Payment Address (VPA, e.g. name@bank) is the alias that hides your account number; the UPI PIN is the 4- or "
     "6-digit secret you set with your debit card and use to authorise each payment. Never share the PIN — you only enter it "
     "to send money, never to receive it.",
     "NPCI UPI product overview; RBI safety advisories"),
    ("upi", "How do I link a credit card to UPI?",
     "RuPay credit cards can be linked in UPI apps (BHIM, PhonePe, Google Pay, Paytm) to pay merchants by scanning QR codes; "
     "Visa/Mastercard credit cards are not supported for UPI except some bank-specific pilots. Merchant payments above ₹2,000 "
     "may carry a fee for the merchant; cash-back/reward rules follow the card.",
     "NPCI RuPay credit card on UPI (2022)"),
    ("upi", "What is UPI Circle?",
     "A delegated-payments feature where a primary user lets a trusted secondary user (child, parent, staff) make UPI "
     "payments from their account, either with full delegation (up to ₹15,000 a month, ₹5,000 per transaction) or with "
     "partial delegation where each payment needs the primary user's approval.",
     "NPCI UPI Circle launch note (Aug 2024)"),
    ("upi", "What should I do if I get a fraudulent UPI request?",
     "Decline it — you never need to enter your PIN to receive money. Report the ID in the app, and if you did lose money "
     "call the national cyber helpline 1930 or file on cybercrime.gov.in within the 'golden hour'; also inform your bank so "
     "the money can be frozen in the receiver's account. Banks must limit your liability if you report within 3 days.",
     "RBI circular on limited customer liability (July 2017); MHA cyber helpline 1930"),
    ("upi", "Why does my bank show a different UPI limit from my friend's?",
     "NPCI sets ceilings, but each bank sets its own per-transaction and daily limits within them (and lower limits for new "
     "devices, newly added accounts or high-risk patterns). Apps like Google Pay also apply their own caps (e.g. 20 "
     "transactions a day). Check 'UPI limits' in the app or your bank's FAQ.",
     "NPCI UPI operating guidelines; bank limit pages"),
    ("upi", "What is IMPS and its limit?",
     "Immediate Payment Service: instant 24×7 bank-to-bank transfer using account number + IFSC or mobile + MMID. NPCI allows "
     "up to ₹5 lakh per transaction; banks may charge ₹2.5–15 plus GST (free in many apps). Unlike UPI it does not need a VPA.",
     "NPCI IMPS product page (limit raised to ₹5 lakh in 2014)"),
    ("upi", "NEFT vs RTGS — what is the difference?",
     "NEFT settles in half-hourly batches, 24×7, with no minimum or maximum (banks may cap online transfers), and is free for "
     "online transactions. RTGS is real-time, 24×7, for amounts of ₹2 lakh and above, with no upper limit, usually used for "
     "large payments like property deals. Both need the beneficiary's account number and IFSC.",
     "RBI NEFT and RTGS FAQs"),
    ("upi", "What is the time limit for a bank to resolve a failed card/ATM transaction?",
     "For ATM cash-not-dispensed cases the bank must reverse within 5 days (T+5) or pay ₹100 a day; for failed card payments "
     "at merchants (money debited, merchant not paid) auto-reversal is within T+5 days; for failed UPI/IMPS T+1. These "
     "timelines and the ₹100/day compensation come from RBI's 2019 turnaround-time circular.",
     "RBI circular DPSS.CO.PD No.629 (2019)"),
    ("upi", "What is the daily limit for mobile banking NEFT transfers?",
     "RBI sets no NEFT limit, but banks set their own daily online caps (often ₹10–25 lakh for retail net banking, lower in "
     "apps and for newly added beneficiaries — for example ₹50,000 in the first 24 hours). Visit a branch or raise the limit "
     "in net banking for larger transfers.",
     "RBI NEFT FAQ; bank-specific limit policies"),
    ("upi", "Can I pay income tax or GST through UPI?",
     "Yes. The income-tax e-filing portal's e-Pay Tax accepts UPI (and net banking, cards, RTGS/NEFT); UPI tax payments "
     "enjoy a higher cap (₹5 lakh per transaction). GST challans can be paid via UPI through the GST portal's e-payment "
     "options depending on the bank.",
     "incometax.gov.in e-Pay Tax; NPCI UPI category limits"),
    ("upi", "What is the UPI chargeback or dispute process for a merchant payment?",
     "If you paid but did not receive goods/services, first contact the merchant; then raise a dispute in the UPI app on that "
     "transaction (within 30 days ideally). The payer bank raises a chargeback through NPCI's dispute system; the merchant's "
     "bank must respond in the set timelines. Unresolved cases go to the RBI Ombudsman.",
     "NPCI UPI dispute resolution (URCS); RBI Ombudsman"),
    ("upi", "What is 'UPI number'?",
     "A UPI number is a numeric alias (your mobile number or a 8–9 digit number you choose) mapped to your VPA so people can "
     "pay you without typing an ID, and it works across apps. You can create it in the UPI app profile and link it to the "
     "bank account you prefer.",
     "NPCI UPI Numeric ID feature (2023)"),

    # ── EPF / PPF / NPS ─────────────────────────────────────────────────────
    ("epf", "How does EPF work?",
     "Employees' Provident Fund is mandatory for establishments with 20+ employees (and for wages up to ₹15,000; above that "
     "it is optional but almost universal). You contribute 12% of basic + DA and your employer matches 12% — of which 8.33% "
     "(capped at ₹1,250 a month) goes to the Employees' Pension Scheme and 3.67% to your EPF account. EPFO credits interest "
     "yearly (8.25% for FY 2024-25). Your contribution qualifies for 80C; interest and withdrawal after 5 years are tax-free.",
     "EPF & MP Act 1952; EPFO interest-rate notification (8.25% for 2024-25)"),
    ("epf", "EPF interest rate and how it's credited",
     "EPFO announces the rate each year (8.25% for FY 2024-25, the same as the previous year) after the Finance Ministry "
     "approves it. Interest is computed monthly on the running balance but credited once a year, usually a few months after "
     "the year ends, which is why your passbook shows interest late. Interest on your own contributions above ₹2.5 lakh a year "
     "is taxable.",
     "EPFO circulars; s.10(11) proviso (₹2.5 lakh rule, Finance Act 2021)"),
    ("epf", "How is EPF interest calculated?",
     "Interest is calculated on the monthly running balance: each month's closing balance × (annual rate ÷ 12). Example at "
     "8.25%: a balance of ₹2,00,000 earns about ₹1,375 that month. Contributions made during the month earn interest from the "
     "next month. The total is credited to the account at year end.",
     "EPFO interest computation rules (Para 60, EPF Scheme 1952)"),
    ("epf", "What is UAN?",
     "The Universal Account Number is a 12-digit ID EPFO gives every member; it stays the same across employers and links all "
     "your PF member IDs. Activate it on the EPFO portal with Aadhaar, mobile and bank KYC to view the passbook, transfer "
     "balances when you change jobs, and file online withdrawal claims.",
     "EPFO Unified Member Portal"),
    ("epf", "When can I withdraw my EPF fully?",
     "At retirement (58), or after two months of continuous unemployment, or on moving abroad permanently. You can take 75% "
     "of the balance after one month of unemployment and the rest after two. Withdrawing before 5 years of total service "
     "makes it taxable (10% TDS above ₹50,000). Transferring the balance to the new employer keeps the tax benefit and the "
     "service continuity.",
     "EPF Scheme 1952 Para 69; s.192A"),
    ("epf", "Can I withdraw EPF partially for a house or medical emergency?",
     "Yes, EPFO allows advances: up to 36 months' basic + DA (or 90% of balance) for buying/constructing a house after "
     "5 years of membership; 6 months' basic or the full employee share for medical treatment (no service minimum); 50% of "
     "your share for marriage or education after 7 years. Advances are not loans — nothing is repaid, and they are tax-free.",
     "EPF Scheme 1952 Para 68B–68N"),
    ("epf", "What is VPF?",
     "Voluntary Provident Fund: contributing more than the mandatory 12% (up to 100% of basic + DA) into your EPF account. It "
     "earns the same EPF interest (8.25%), qualifies for 80C, and the employer does not match it. Interest on your own "
     "contributions above ₹2.5 lakh a year (EPF + VPF) is taxable.",
     "EPF Scheme 1952 Para 26(6); Finance Act 2021 ₹2.5 lakh rule"),
    ("epf", "What is EPS pension and how much will I get?",
     "The Employees' Pension Scheme is funded by the employer's 8.33% (on wages up to ₹15,000). After 10 years of service you "
     "get a monthly pension from 58: pensionable salary × pensionable service ÷ 70. With the ₹15,000 wage cap and 35 years' "
     "service the maximum is ₹7,500 a month; early pension from 50 is reduced 4% a year. Members with less than 10 years can "
     "withdraw the EPS amount instead.",
     "EPS 1995 Para 12"),
    ("epf", "What is EDLI?",
     "Employees' Deposit Linked Insurance comes free with EPF: if a member dies in service, the nominee gets a lump sum of up "
     "to ₹7 lakh (minimum ₹2.5 lakh after one year of continuous service), funded by the employer's 0.5% contribution. No "
     "separate enrolment is needed.",
     "EDLI Scheme 1976 (benefit raised to ₹7 lakh in 2021)"),
    ("epf", "How do I transfer EPF when I change jobs?",
     "Give your UAN to the new employer; then file Form 13 online on the EPFO member portal ('One Member – One EPF Account'). "
     "Since 2025 most transfers are auto-processed without employer attestation. Transferring keeps your service continuous "
     "(important for the 5-year tax-free rule and EPS pension).",
     "EPFO Form 13 online transfer; EPFO circulars 2025"),
    ("epf", "What is PPF and who can open it?",
     "Public Provident Fund is a 15-year government-backed savings scheme at a bank or post office. Any resident individual can "
     "open one (also for a minor child); HUFs and NRIs cannot open new accounts. Deposit ₹500 to ₹1.5 lakh a year in up to 12 "
     "instalments. It is EEE: deposits qualify for 80C, and interest and maturity are tax-free.",
     "PPF Scheme 2019"),
    ("epf", "What is the PPF interest rate?",
     "7.1% a year, compounded annually and credited on 31 March — unchanged since April 2020 (the government reviews small-"
     "savings rates every quarter). Interest for a month is computed on the lowest balance between the 5th and the end of the "
     "month, so deposit before the 5th to earn that month's interest.",
     "Ministry of Finance quarterly small-savings rate notifications; PPF Scheme 2019 Para 5"),
    ("epf", "PPF maturity rules",
     "PPF matures 15 financial years after the year of opening. You can withdraw the whole balance tax-free, extend without "
     "deposits (keep earning interest, one withdrawal a year), or extend with deposits in 5-year blocks (apply within a year "
     "of maturity; withdrawals limited to 60% of the balance at the start of the block).",
     "PPF Scheme 2019 Paras 10–11"),
    ("epf", "How much will PPF of ₹1.5 lakh a year become in 15 years?",
     "At 7.1% with the deposit made at the start of each year, 15 deposits of ₹1.5 lakh (₹22.5 lakh invested) grow to about "
     "₹40.7 lakh, all tax-free. ₹1 lakh a year gives about ₹27.1 lakh and ₹50,000 a year about ₹13.6 lakh. Extending for 5 more "
     "years at ₹1.5 lakh takes the corpus to roughly ₹66.6 lakh.",
     "Computed: annuity-due at 7.1% compounded yearly"),
    ("epf", "Can I withdraw from PPF before 15 years?",
     "Partial withdrawal is allowed from the 7th financial year: up to 50% of the balance at the end of the 4th year preceding "
     "the withdrawal year or the previous year, whichever is lower, once a year. Premature closure after 5 years is allowed "
     "only for serious illness, higher education or change of residency status, with a 1% interest penalty. A loan is "
     "available in years 3–6 at 1% interest.",
     "PPF Scheme 2019 Paras 9, 12, 13"),
    ("epf", "PPF vs NPS — which is better?",
     "PPF is a guaranteed 7.1% tax-free debt product with a 15-year lock-in and a ₹1.5 lakh cap — safe but inflation-tight. NPS "
     "invests in equity and bonds (historically 9–12% long-term in equity-heavy choices), has an extra ₹50,000 80CCD(1B) "
     "deduction in the old regime and employer benefits in both regimes, but locks money till 60 and forces 40% into an "
     "annuity that is taxable. Many people use PPF for the safe part and NPS for the growth part of retirement savings.",
     "PFRDA NPS returns history; PPF Scheme rules"),
    ("epf", "What is NPS?",
     "The National Pension System is a PFRDA-regulated retirement account open to all Indian citizens aged 18–70. You invest "
     "regularly in a mix of equity (E), corporate bonds (C), government bonds (G) and alternatives (A) via pension fund "
     "managers at very low cost. At 60 you take up to 60% tax-free as a lump sum and use at least 40% to buy an annuity. Tax "
     "breaks: 80CCD(1), extra ₹50,000 under 80CCD(1B), and the employer's contribution under 80CCD(2).",
     "PFRDA Act 2013; NPS Trust FAQs"),
    ("epf", "NPS tax benefit under 80CCD(1B)",
     "Your own contribution to NPS Tier I gets an extra deduction of up to ₹50,000 under 80CCD(1B), on top of the ₹1.5 lakh "
     "80C/80CCD(1) limit — available only in the old regime. At the 30% slab that is a saving of ₹15,600 a year. Tier II "
     "contributions get no deduction (except for central-government employees).",
     "s.80CCD(1B) Income-tax Act"),
    ("epf", "What is NPS Tier 1 vs Tier 2?",
     "Tier I is the pension account: tax benefits, locked until 60 (limited partial withdrawals), mandatory annuity at exit. "
     "Tier II is an optional savings account on top of an active Tier I: no lock-in, withdraw any time, same fund choices "
     "and low costs, but no tax deduction and gains are taxed like any investment.",
     "PFRDA NPS architecture"),
    ("epf", "How is NPS taxed at withdrawal?",
     "At 60, up to 60% of the corpus withdrawn as a lump sum is tax-free; at least 40% must buy an annuity, and the annuity "
     "income is taxed at slab rates each year. Partial withdrawals (up to 25% of your own contributions, max three times after "
     "three years) are tax-free. If the corpus is ₹5 lakh or less you can withdraw all of it.",
     "s.10(12A), s.10(12B); PFRDA exit regulations"),
    ("epf", "What is the equity limit in NPS?",
     "Under Active Choice you can put up to 75% in equity (Scheme E) until age 50, tapering to 50% by 60; alternatives (A) are "
     "capped at 5%. Auto Choice lifecycle funds (Aggressive LC75, Moderate LC50, Conservative LC25) reduce equity "
     "automatically as you age.",
     "PFRDA investment guidelines for NPS subscribers"),
    ("epf", "Can I exit NPS before 60?",
     "Yes, after 5 years (3 years for those who joined after 60): you must put at least 80% into an annuity and can take 20% as "
     "lump sum — unless the corpus is ₹2.5 lakh or less, in which case the whole amount can be withdrawn. Partial withdrawals "
     "for specific needs (education, marriage, house, illness) are allowed from year three.",
     "PFRDA (Exits and Withdrawals) Regulations"),
    ("epf", "What is the Unified Pension Scheme (UPS)?",
     "An option under NPS for central-government employees from 1 April 2025: after 25 years of service it guarantees a "
     "pension of 50% of the average basic pay of the last 12 months (proportionate for 10–25 years, minimum ₹10,000 a month), "
     "with inflation indexation and 60% family pension. Employees contribute 10%; the government 18.5%.",
     "Ministry of Finance notification 24 Jan 2025 (UPS)"),
    ("epf", "What is NPS Vatsalya?",
     "An NPS account for minors launched in September 2024: parents or guardians invest at least ₹1,000 a year in the child's "
     "name; at 18 it converts to a regular NPS Tier I account. Budget 2025 extended the 80CCD(1B) ₹50,000 deduction (old regime) "
     "to contributions in a child's Vatsalya account.",
     "PFRDA NPS Vatsalya scheme; Finance Act 2025"),
    ("epf", "Is EPF or NPS mandatory?",
     "EPF is mandatory for eligible employees in covered establishments (and voluntary above the ₹15,000 wage threshold if you "
     "opted in at joining). NPS is mandatory only for central-government employees who joined after 1 January 2004 (and many "
     "state employees); for everyone else it is voluntary.",
     "EPF & MP Act 1952; PFRDA Act 2013"),
    ("epf", "What is gratuity and how is it calculated?",
     "Gratuity is a lump sum an employer pays after at least 5 years of continuous service (also on death/disability): "
     "15 days' last-drawn basic + DA for every completed year, i.e. (basic + DA) × 15/26 × years. Example: ₹50,000 and 10 years "
     "→ ₹50,000 × 15/26 × 10 ≈ ₹2,88,462. Tax-free up to ₹20 lakh.",
     "Payment of Gratuity Act 1972; s.10(10)"),
    ("epf", "What is the Senior Citizen Savings Scheme?",
     "A post-office/bank scheme for residents aged 60+ (55+ for some retirees): deposit up to ₹30 lakh for 5 years (extendable "
     "3 years) at 8.2% a year, paid quarterly. The deposit qualifies for 80C; interest is taxable, with TDS above ₹1 lakh "
     "(80TTB gives ₹50,000 deduction).",
     "SCSS 2019 rules; rate table 2025-26"),
    ("epf", "What is the Atal Pension Yojana?",
     "A government pension scheme for 18–40-year-olds (not income-tax payers, since Oct 2022): contribute a fixed monthly amount "
     "based on age and the pension you choose (₹1,000 to ₹5,000 a month from 60), with the spouse getting the same pension and "
     "the nominee the corpus. Contributions qualify under 80CCD(1).",
     "PFRDA APY scheme guidelines"),

    # ── credit score ────────────────────────────────────────────────────────
    ("credit_score", "How is a credit score calculated?",
     "Bureaus (CIBIL, Experian, Equifax, CRIF High Mark) score you from 300 to 900 using your credit history: payment history "
     "(roughly 35% weight — any late EMI or card payment hurts most), credit utilisation (about 30% — keep card balances under "
     "30% of the limit), length of history (15%), credit mix of secured and unsecured loans (10%) and recent hard enquiries "
     "(10%). No loans or cards means no score ('NA/NH'), not a bad one.",
     "TransUnion CIBIL methodology notes; RBI credit information regulations"),
    ("credit_score", "Is 750 a good credit score?",
     "Yes — 750 and above is what most banks treat as 'good': you qualify for most loans and cards and often get the best "
     "rates. 650–749 is fair (loans possible, maybe higher rates); below 650 lenders become cautious. Scores above 800 are "
     "excellent.",
     "Lender practice; CIBIL score bands"),
    ("credit_score", "What is CIBIL?",
     "TransUnion CIBIL is India's oldest credit bureau; 'CIBIL score' is its 3-digit score (300–900) summarising your loan and "
     "card repayment behaviour reported by lenders. Three other RBI-licensed bureaus — Experian, Equifax and CRIF High Mark — "
     "produce their own scores, which can differ slightly because lenders report to each separately.",
     "Credit Information Companies (Regulation) Act 2005; RBI"),
    ("credit_score", "How can I check my credit score for free?",
     "Every bureau must give you one free full credit report a year — use the CIBIL, Experian, Equifax and CRIF websites. Many "
     "apps (banks, Paytm, Google Pay, Paisabazaar) show free scores monthly; checking your own score is a soft enquiry and "
     "does not lower it.",
     "RBI circular on free annual credit report (2016)"),
    ("credit_score", "How do I improve my credit score?",
     "Pay every EMI and card bill in full and on time (set auto-pay), keep card utilisation below 30%, do not apply for many "
     "loans at once, keep old cards open to lengthen history, avoid settling loans for less than owed, and check your report "
     "for errors. Improvement usually shows within 3–6 months; bureaus now receive updates from lenders every fortnight.",
     "RBI directive on fortnightly reporting (effective Jan 2025); CIBIL guidance"),
    ("credit_score", "Does checking my own credit score reduce it?",
     "No. Checking your own score is a 'soft enquiry' and never affects it. Only 'hard enquiries' — when a lender pulls your "
     "report because you applied for credit — are recorded and can shave a few points if there are many in a short time.",
     "Bureau enquiry rules"),
    ("credit_score", "How long do defaults stay on a credit report?",
     "Repayment history, including late payments and defaults, stays on your report for up to 7 years from the date of the "
     "event. A loan 'settled' for less than the full amount is flagged as 'settled' and hurts for years; paying the full "
     "amount and getting it marked 'closed' is far better.",
     "CICRA regulations; bureau reporting practice"),
    ("credit_score", "What is credit utilisation ratio?",
     "The share of your total credit-card limit you are using: ₹30,000 outstanding on a ₹1 lakh limit is 30%. Lenders prefer "
     "below 30%; above 50% signals stress and drags the score down even if you pay in full. Asking for a higher limit or "
     "splitting spend across cards reduces the ratio.",
     "Credit bureau scoring factors"),
    ("credit_score", "Will closing a credit card improve my score?",
     "Usually the opposite: closing a card cuts your total limit (raising utilisation) and may shorten your credit history. "
     "Keep old, no-fee cards open with occasional small use; close a card only if it has a high annual fee or you cannot "
     "control spending.",
     "Credit bureau scoring factors"),
    ("credit_score", "What is a hard enquiry?",
     "A lender's check of your credit report when you apply for a loan or card. Each one is listed and too many in a short "
     "period (say 4–5 in a few months) lowers your score because it looks like credit hunger. Shop for loans within a short "
     "window and avoid applying to many lenders at once.",
     "Credit bureau enquiry rules"),
    ("credit_score", "How can a student or first-job person build a credit score?",
     "Start with a secured credit card against a fixed deposit (₹10,000+), use it for small spends and pay in full every month; "
     "or take a small consumer-durable EMI and repay on time. In 6–12 months you will have a score. Being an authorised user "
     "on a parent's card also helps. Avoid instant BNPL apps piling up enquiries.",
     "Lender products (FD-backed cards); bureau guidance"),
    ("credit_score", "What if there is an error in my credit report?",
     "Raise a dispute online with the bureau; it must respond within 30 days after checking with the lender. Under RBI's "
     "October 2023 directions, credit institutions and bureaus that fail to resolve a complaint within 30 days must pay you "
     "₹100 per day of delay. Keep loan closure letters and NOCs to prove your case.",
     "RBI circular on strengthening customer service by CICs (Oct 2023)"),
    ("credit_score", "Do EMI delays of a few days affect the credit score?",
     "Lenders generally report the days-past-due status at month end; a payment a few days late that is cleared within the "
     "same cycle often is not reported, but anything 30+ days past due certainly is and stays for years. Late fees and penal "
     "charges apply regardless, so always pay by the due date.",
     "Bureau DPD reporting conventions"),
    ("credit_score", "What is a credit card minimum amount due?",
     "Usually 5% of the outstanding balance (plus any EMIs and over-limit amounts). Paying only the minimum keeps the card active "
     "but the rest attracts 3–3.75% interest a month (36–45% a year) and you lose the interest-free period on new purchases. "
     "Always try to pay the total amount due.",
     "Card issuer terms; RBI credit-card directions 2022"),
    ("credit_score", "How does the credit card interest-free period work?",
     "Purchases made during a billing cycle are interest-free until the payment due date — typically 20 to 50 days depending on "
     "when in the cycle you buy — provided you pay the full statement amount. If you carry any balance, interest is charged "
     "from the transaction date on all purchases. Cash withdrawals never get a free period.",
     "RBI Master Direction on credit and debit cards (2022)"),
    ("credit_score", "What is the real cost of revolving ₹50,000 on a credit card?",
     "At 3.5% a month, carrying ₹50,000 for a year costs about ₹25,500 in interest (compounded monthly ≈ 51% effective), plus "
     "GST at 18% on the interest. A personal loan at 14% would cost about ₹7,000 for the same year — so converting card debt "
     "to EMIs or a loan is almost always cheaper.",
     "Computed: 1.035^12 − 1 on ₹50,000"),
    ("credit_score", "What is a credit card billing cycle?",
     "The roughly 30-day period over which spends are collected into one statement; the due date falls about 15–25 days after "
     "the statement date. Buying right after the statement date gives you the longest interest-free stretch (up to ~50 days). "
     "RBI lets you change the cycle once to suit your salary date.",
     "RBI Master Direction on credit cards (2022)"),
    ("credit_score", "Does a co-applicant's score matter for a loan?",
     "Yes — banks check both applicants, and the weaker score can lead to a higher rate or rejection. A co-applicant with a "
     "good score and income helps you qualify for a bigger loan, but both are equally liable and the loan appears on both "
     "credit reports.",
     "Lender underwriting practice"),
    ("credit_score", "What is a 'no-cost EMI'?",
     "The retailer or brand pays the interest (as a discount to the bank), so you pay the price in equal instalments. There is "
     "still interest on the bank's books — the product discount is simply adjusted — and GST applies on that interest; some "
     "cards also charge a processing fee. Check that the total paid equals the sticker price.",
     "RBI circular on zero-percent EMI schemes (2013); card issuer terms"),
    ("credit_score", "What is BNPL and how does it affect credit?",
     "Buy-now-pay-later lets you defer small purchases for 15–45 days or convert them to EMIs through an NBFC partner. Most "
     "BNPL lines are reported to bureaus as loans, so missed repayments damage your score; many small open lines can also "
     "lower it. Use at most one and clear it on time.",
     "RBI digital lending guidelines 2022; bureau reporting"),

    # ── loans and EMI maths ─────────────────────────────────────────────────
    ("loans", "How is EMI calculated?",
     "EMI = P × r × (1 + r)^n ÷ ((1 + r)^n − 1), where P is the principal, r the monthly rate (annual rate ÷ 12 ÷ 100) and n the "
     "number of months. Example: ₹10 lakh at 9% for 5 years → r = 0.0075, n = 60 → EMI ≈ ₹20,758; total paid ₹12.46 lakh, "
     "interest ₹2.46 lakh. Early EMIs are mostly interest; later ones mostly principal.",
     "Standard amortisation formula (used by the app's emi tool)"),
    ("loans", "EMI on 10 lakh at 9% for 5 years",
     "About ₹20,758 a month. Total repayment ₹12,45,501 over 60 months, of which ₹2,45,501 is interest. (Monthly rate 0.75%, "
     "n = 60.)",
     "Computed with the amortisation formula"),
    ("loans", "EMI for 25 lakh home loan at 8.5% for 20 years",
     "₹21,696 a month. Over 240 months you repay ₹52.07 lakh, i.e. ₹27.07 lakh of interest on the ₹25 lakh borrowed. Shorter "
     "tenures cost less overall: 15 years → EMI ₹24,618 (interest ₹19.3 lakh); 10 years → ₹30,996 (interest ₹12.2 lakh).",
     "Computed with the amortisation formula"),
    ("loans", "EMI on 50 lakh at 8% for 20 years?",
     "₹41,822 a month; total repayment about ₹1.0 crore, so interest of roughly ₹50.4 lakh over 20 years. Each 0.25% change in "
     "rate moves this EMI by about ₹800.",
     "Computed with the amortisation formula"),
    ("loans", "EMI on 5 lakh personal loan at 11% for 3 years",
     "₹16,369 a month; total ₹5,89,297, interest ₹89,297. Add the processing fee (usually 1–2% + GST) to compare offers.",
     "Computed with the amortisation formula"),
    ("loans", "EMI on 3 lakh at 14% for 3 years",
     "₹10,253 a month; total repayment ₹3,69,118, of which ₹69,118 is interest.",
     "Computed with the amortisation formula"),
    ("loans", "Car loan of 8 lakh at 10% for 7 years — EMI?",
     "₹13,281 a month. Total paid ₹11.16 lakh, so interest of ₹3.16 lakh. A 5-year tenure would raise the EMI to about ₹17,000 "
     "but cut interest to roughly ₹2.2 lakh.",
     "Computed with the amortisation formula"),
    ("loans", "EMI on 2 lakh bike loan at 11% for 3 years",
     "₹6,548 a month; you repay ₹2,35,719 in total, ₹35,719 of it interest.",
     "Computed with the amortisation formula"),
    ("loans", "EMI on 30 lakh at 9% for 15 years",
     "₹30,428 a month; total repayment ₹54.77 lakh, interest ₹24.77 lakh.",
     "Computed with the amortisation formula"),
    ("loans", "EMI for 40 lakh home loan at 8.75% for 25 years",
     "₹32,886 a month. Over 300 months you pay about ₹98.66 lakh — ₹58.66 lakh of interest, more than the loan itself, which is "
     "why prepaying a long loan early saves so much.",
     "Computed with the amortisation formula"),
    ("loans", "How does the tenure change my EMI and total interest?",
     "On ₹25 lakh at 8.5%: 10 years → EMI ₹30,996, interest ₹12.2 lakh; 15 years → ₹24,618, interest ₹19.3 lakh; 20 years → "
     "₹21,696, interest ₹27.1 lakh. A longer tenure lowers the EMI but roughly doubles the interest. Pick the shortest tenure "
     "whose EMI stays under about 40% of take-home pay.",
     "Computed with the amortisation formula"),
    ("loans", "How much does the interest rate matter on a 25 lakh, 20-year loan?",
     "At 8% the EMI is ₹20,911 (total interest ₹25.2 lakh); at 8.5% ₹21,696 (₹27.1 lakh); at 9% ₹22,493 (₹29.0 lakh). Each 0.5% "
     "costs about ₹1.9 lakh more over the loan — worth negotiating or transferring for.",
     "Computed with the amortisation formula"),
    ("loans", "What is the difference between flat and reducing-balance interest?",
     "Reducing-balance interest is charged only on the outstanding principal, which falls with every EMI — this is how bank "
     "home and personal loans work. A 'flat rate' charges interest on the original principal for the whole tenure, so a flat "
     "8% on a 3-year loan is equivalent to roughly 14–15% reducing. Always compare the reducing-balance (APR) rate.",
     "RBI fair-practice code on disclosure of annualised rates"),
    ("loans", "Are there prepayment charges on home loans?",
     "No foreclosure or part-prepayment charges may be levied on floating-rate loans to individuals (home, personal, etc.) — "
     "an RBI rule since 2012–14, extended to floating-rate business loans of micro and small enterprises from 1 January 2026. "
     "Fixed-rate loans can carry charges (typically 2–4% of the prepaid amount).",
     "RBI circulars 2012/2014; RBI Directions on foreclosure charges (June 2025)"),
    ("loans", "Should I prepay my home loan or invest the money?",
     "Compare the loan rate with the post-tax return you can reliably earn. At 8.5% a prepayment is a guaranteed 8.5% return; "
     "equity may average 10–12% but with risk, while FDs give 6–7%. Many people split: keep the 24(b)/80C benefits in the "
     "old regime, prepay partly each year (early prepayments save the most interest), and invest the rest. Keep an emergency "
     "fund before prepaying. This is general education, not personal advice.",
     "General trade-off; interest-rate comparison"),
    ("loans", "What is MCLR vs repo-linked rate?",
     "MCLR (marginal cost of funds based lending rate) is a bank's internal benchmark, reset every 6–12 months, so rate cuts "
     "reach you slowly. Since October 2019 new floating retail loans must be linked to an external benchmark — usually the RBI "
     "repo rate (EBLR/RLLR) — and reset at least every 3 months, so changes pass through quickly. You can switch an old MCLR "
     "loan to EBLR for a small fee.",
     "RBI circular on external benchmark lending rates (Sept 2019)"),
    ("loans", "What is the repo rate and why does it matter to my home loan?",
     "The repo rate is the rate at which RBI lends to banks; the Monetary Policy Committee reviews it every two months. "
     "Repo-linked floating home loans charge repo + a fixed spread, so a 0.25% repo cut lowers your rate within about three "
     "months — on a ₹25 lakh, 20-year loan each 0.25% is roughly ₹400 of EMI or about a year of tenure.",
     "RBI Monetary Policy framework; EBLR circular"),
    ("loans", "What is loan-to-value for a home loan?",
     "The maximum share of the property price a bank will lend: 90% for homes up to ₹30 lakh, 80% for ₹30–75 lakh and 75% "
     "above ₹75 lakh (RBI norms). The rest is your down payment; stamp duty and registration are usually not funded.",
     "RBI housing-loan LTV circular"),
    ("loans", "What is a home-loan balance transfer?",
     "Moving your outstanding loan to another lender offering a lower rate; the new lender pays off the old one. Worth it when "
     "the rate gap is 0.5% or more with several years left, after counting processing fees (0.25–1%) and legal/valuation "
     "charges. Alternatively ask your own bank to reset the spread for a small conversion fee.",
     "Lender practice; RBI permits switch to EBLR"),
    ("loans", "What is a top-up loan?",
     "An extra loan on top of an existing home loan from the same lender, usually at home-loan-like rates (slightly higher) and "
     "with minimal paperwork. Interest on a top-up used for home renovation can qualify under 24(b); if used for other "
     "purposes it gets no tax benefit.",
     "Lender products; s.24(b)"),
    ("loans", "What is a moratorium on an education loan?",
     "The repayment holiday during the course plus 6–12 months after it (or until you get a job, whichever is earlier). Simple "
     "interest accrues during the moratorium; paying it as you go keeps the principal from ballooning. The interest you pay "
     "later is deductible under 80E for 8 years.",
     "IBA model education loan scheme; s.80E"),
    ("loans", "How does a gold loan work?",
     "A secured loan against gold jewellery or coins: lenders give up to 75% of the gold's value (RBI LTV cap; up to 85% for "
     "small loans under the 2025 directions), at 9–18% interest, for 6–36 months with bullet or EMI repayment. Cheap and fast, "
     "but the gold is auctioned if you default.",
     "RBI Directions on lending against gold (June 2025)"),
    ("loans", "What is a processing fee and what else do loans charge?",
     "A one-time fee of about 0.5–2% of the loan (plus 18% GST) for appraisal. Other charges: legal/valuation fees for home "
     "loans, insurance pushed with the loan (optional), late-payment penal charges (RBI now bars penal 'interest'; only "
     "reasonable penal charges), and foreclosure charges on fixed-rate loans. Compare the APR, not just the headline rate.",
     "RBI circular on penal charges (Aug 2023); lender schedules of charges"),
    ("loans", "What EMI can I afford?",
     "A common rule is total EMIs (including cards) under 40% of take-home pay — banks compute a similar FOIR (fixed "
     "obligation to income ratio) of 40–55%. On a ₹80,000 take-home that means EMIs up to ₹32,000, which supports roughly a "
     "₹37 lakh home loan at 8.5% for 20 years. Keep 3–6 months of expenses as an emergency fund alongside.",
     "Lender FOIR practice; computed with the amortisation formula"),
    ("loans", "What is a credit-linked subsidy or PMAY benefit?",
     "Under PMAY-Urban 2.0 (2024–29) eligible first-time home buyers from EWS/LIG/MIG households can get an interest subsidy "
     "of up to ₹1.8 lakh on home loans up to ₹25 lakh for houses costing up to ₹35 lakh, credited to the loan account in "
     "instalments. Apply through the lender; eligibility depends on income and not owning a pucca house.",
     "PMAY-U 2.0 scheme guidelines (2024)"),
    ("loans", "What is the difference between secured and unsecured loans?",
     "Secured loans (home, car, gold, loan against FD/property) are backed by collateral, so rates are lower (7–12%) and "
     "tenures longer. Unsecured loans (personal loans, credit cards) rely only on your credit profile, so rates are higher "
     "(10–24% for personal loans, 36%+ on cards) and amounts smaller.",
     "Lender product structures"),
    ("loans", "Can I get a loan against my fixed deposit?",
     "Yes — banks lend 85–95% of the FD value as an overdraft or loan at FD rate + 1–2%, with no processing fee and no credit "
     "check, while the FD keeps earning interest. Useful for short-term needs instead of breaking the FD and losing interest.",
     "Bank loan-against-deposit products"),
    ("loans", "What is CIBIL's role in loan approval?",
     "Lenders pull your report from one or more bureaus; a score of 750+ usually means approval and the best rate, 650–749 "
     "may mean a higher rate or smaller amount, and below 650 often rejection. They also check recent enquiries, existing EMIs "
     "and any 'settled' or 'written-off' accounts.",
     "Lender underwriting practice"),

    # ── deposits, savings and banking ──────────────────────────────────────
    ("deposits", "How is FD interest calculated?",
     "Most banks compound quarterly: maturity = P × (1 + r/4)^(4 × years). ₹1 lakh at 7% for 3 years → ₹1,00,000 × (1.0175)^12 "
     "≈ ₹1,23,144. For 5 years at the same rate → about ₹1,41,478. Interest is taxable at your slab and TDS of 10% applies "
     "once a bank pays you more than ₹50,000 in a year (₹1 lakh for seniors).",
     "Quarterly compounding formula; s.194A"),
    ("deposits", "₹1 lakh FD at 7% for 3 years",
     "With quarterly compounding you get about ₹1,23,144 at maturity — ₹23,144 of interest. Simple interest would be only "
     "₹21,000, so compounding adds about ₹2,100.",
     "Computed with quarterly compounding"),
    ("deposits", "FD of 5 lakh at 7.5% for 5 years — maturity?",
     "About ₹7,24,974 with quarterly compounding (interest ₹2.25 lakh). At the 30% slab the post-tax interest is roughly "
     "₹1.57 lakh, so the effective return is about 5.3% a year.",
     "Computed with quarterly compounding"),
    ("deposits", "₹10 lakh FD at 7.25% for one year",
     "₹10,74,495 at maturity with quarterly compounding (interest ₹74,495; the bank will deduct ₹7,450 TDS at 10% unless you "
     "submit 15G/15H).",
     "Computed with quarterly compounding; s.194A"),
    ("deposits", "RD of ₹2,000 for 2 years at 6.5%",
     "You deposit ₹48,000 over 24 months and receive about ₹51,370 at maturity — roughly ₹3,370 of interest (banks compound RD "
     "interest quarterly on each instalment).",
     "Computed with quarterly compounding on each instalment"),
    ("deposits", "RD of 5,000 a month at 7% for 5 years",
     "₹3 lakh deposited grows to about ₹3,59,664 — ₹59,664 of interest, taxable at your slab.",
     "Computed with quarterly compounding"),
    ("deposits", "RD of ₹10,000 a month for 3 years at 6.8%",
     "₹3.6 lakh of deposits becomes roughly ₹4,00,118, i.e. about ₹40,118 of interest.",
     "Computed with quarterly compounding"),
    ("deposits", "What is a recurring deposit?",
     "A bank or post-office deposit where you pay a fixed amount every month for 6 months to 10 years and get the total plus "
     "interest (usually the FD rate for that tenure, compounded quarterly) at maturity. Good for disciplined saving towards a "
     "near-term goal; interest is taxable at slab and TDS rules are the same as for FDs.",
     "Bank RD product terms; s.194A"),
    ("deposits", "Is my bank deposit insured?",
     "Yes — DICGC (an RBI subsidiary) insures deposits up to ₹5 lakh per depositor per bank (principal + interest, across all "
     "accounts and branches of that bank), including cooperative banks. Spreading large sums across banks increases cover. "
     "Payouts are made within 90 days of a bank's moratorium or failure.",
     "DICGC Act; cover raised to ₹5 lakh in Feb 2020"),
    ("deposits", "What is a sweep-in FD?",
     "A savings account linked to FDs so that balances above a threshold are automatically moved into fixed deposits (earning "
     "FD rates) and broken in units when you need cash. You get near-FD returns with savings-account liquidity; broken "
     "deposits earn interest for the period held, sometimes with a small penalty.",
     "Bank auto-sweep product terms"),
    ("deposits", "What is the penalty for breaking an FD early?",
     "Banks pay interest for the period the deposit actually ran, at the rate applicable to that shorter tenure, minus a "
     "premature-withdrawal penalty of usually 0.5–1%. Some banks waive the penalty if you reinvest; tax-saver FDs cannot be "
     "broken within 5 years.",
     "RBI guidelines on premature withdrawal; bank terms"),
    ("deposits", "Do senior citizens get higher FD rates?",
     "Yes, most banks pay 0.25–0.5% extra to depositors aged 60+ (some 'super senior' slabs add more). Seniors also get the "
     "₹50,000 80TTB deduction on deposit interest and a higher TDS threshold of ₹1 lakh.",
     "Bank rate cards; ss.80TTB, 194A"),
    ("deposits", "What is the rule of 72?",
     "A quick estimate of doubling time: years to double ≈ 72 ÷ annual return. At 8% money doubles in about 9 years "
     "(₹1 lakh → ₹1,99,900 exactly), at 12% in 6 years, at 7.1% (PPF) in about 10 years. It also works backwards: to double in "
     "5 years you need about 14.4%.",
     "Mathematical approximation (ln 2 ≈ 0.693)"),
    ("deposits", "What is the difference between savings account and current account?",
     "Savings accounts are for individuals, earn interest (2.5–7% depending on the bank) and have transaction limits; current "
     "accounts are for businesses, pay no interest, allow unlimited transactions and overdrafts, and usually need a higher "
     "minimum balance. Savings interest up to ₹10,000 is deductible under 80TTA (old regime).",
     "Bank product terms; s.80TTA"),
    ("deposits", "What happens if I don't maintain the minimum balance?",
     "Banks may charge a non-maintenance fee (RBI requires it to be proportionate to the shortfall and notified in advance, "
     "and no charge may push the balance negative). Basic Savings Bank Deposit (zero-balance) accounts and Jan Dhan accounts "
     "have no minimum. Several public-sector banks dropped the charge in 2025.",
     "RBI circular on levy of charges for non-maintenance of minimum balance (2014)"),
    ("deposits", "What is a dormant or inoperative account?",
     "An account with no customer-initiated transaction for two years becomes 'inoperative'; the bank must not charge for "
     "non-maintenance and must try to contact you. Reactivate with a KYC update at the branch. Balances unclaimed for 10 years "
     "go to RBI's DEA Fund but can be reclaimed (search via RBI's UDGAM portal).",
     "RBI Master Direction on inoperative accounts (Jan 2024); UDGAM portal"),
    ("deposits", "What is a cheque bounce and its consequences?",
     "If a cheque is returned for insufficient funds or a signature mismatch, the bank charges a return fee; the payee can send "
     "a legal notice within 30 days and, if unpaid in 15 days, prosecute under section 138 of the Negotiable Instruments Act "
     "(up to 2 years' jail or twice the cheque amount). Repeated bounces also lead banks to close accounts and lenders to "
     "report defaults.",
     "Negotiable Instruments Act s.138"),
    ("deposits", "What is Positive Pay for cheques?",
     "A fraud check: before the cheque is presented, you confirm its details (number, date, payee, amount) to your bank through "
     "net banking or the app. RBI made it available for cheques of ₹50,000 and above, and banks may make it mandatory for "
     "₹5 lakh and above.",
     "RBI circular on Positive Pay System (Sept 2020)"),
    ("deposits", "Why should I add a nominee to my bank account?",
     "A nominee can receive the balance without a succession certificate when you die, which spares the family months of "
     "paperwork (the nominee holds it in trust for the legal heirs). The Banking Laws (Amendment) Act 2025 allows up to four "
     "nominees per account. Review nominees after marriage or other life events.",
     "Banking Regulation Act s.45ZA; Banking Laws (Amendment) Act 2025"),
    ("deposits", "What is a joint account 'either or survivor'?",
     "An operating mandate for joint accounts: either holder can transact alone, and on one holder's death the survivor keeps "
     "operating the account. 'Jointly' needs both signatures; 'former or survivor' lets only the first holder operate while "
     "alive. Choose the mandate at account opening; FDs follow the same mandates.",
     "Bank account-opening forms; RBI customer service guidelines"),

    # ── RBI and monetary basics ─────────────────────────────────────────────
    ("rbi", "What does the RBI do?",
     "The Reserve Bank of India (est. 1935 under the RBI Act 1934) is the central bank: it sets monetary policy (repo rate) to "
     "keep inflation near 4% (±2%), regulates banks, NBFCs and payment systems (UPI, NEFT, cards), manages the rupee and "
     "foreign-exchange reserves, issues currency, acts as the government's banker and runs the Ombudsman for customer "
     "complaints.",
     "RBI Act 1934; RBI 'About us'"),
    ("rbi", "What is the difference between SEBI and RBI?",
     "RBI regulates money and banking — banks, NBFCs, payments, forex and interest rates. SEBI (Securities and Exchange Board, "
     "1992) regulates the securities market — stock exchanges, brokers, mutual funds, IPOs, investment advisers and listed "
     "companies. Insurance is under IRDAI and pensions under PFRDA.",
     "RBI Act 1934; SEBI Act 1992"),
    ("rbi", "What are CRR and SLR?",
     "Cash Reserve Ratio is the share of deposits banks must keep as cash with RBI (3% after the cuts announced in 2025); "
     "Statutory Liquidity Ratio is the share they must hold in liquid assets like government bonds (18%). Lower ratios free "
     "money for lending and tend to lower interest rates.",
     "RBI monetary-policy statements; RBI Act s.42, Banking Regulation Act s.24"),
    ("rbi", "What is inflation and how does RBI target it?",
     "Inflation is the yearly rise in prices, measured by the Consumer Price Index. Under the 2016 framework RBI's Monetary "
     "Policy Committee (six members) must keep CPI inflation at 4% with a 2–6% tolerance band, mainly by raising the repo rate "
     "when inflation is high and cutting it when growth needs support.",
     "RBI Act Chapter IIIF (2016 amendment); MPC framework"),
    ("rbi", "What is the Monetary Policy Committee?",
     "A six-member body (three RBI members including the Governor, three government nominees) that votes on the repo rate "
     "six times a year. Decisions are by majority with the Governor's casting vote; minutes are published two weeks later.",
     "RBI Act s.45ZB"),
    ("rbi", "What is the RBI Ombudsman and how do I complain?",
     "A free grievance system for banks, NBFCs, payment operators and prepaid wallets. First complain to the institution; if "
     "unresolved in 30 days (or rejected), file at cms.rbi.org.in or call 14448. The Ombudsman can award up to ₹20 lakh "
     "compensation plus ₹1 lakh for harassment.",
     "RBI Integrated Ombudsman Scheme 2021"),
    ("rbi", "What is the difference between a bank and an NBFC?",
     "Banks hold a banking licence, can take demand deposits (savings/current), issue cheques and are part of the payment "
     "system; NBFCs (Bajaj Finance, Muthoot, fintech lenders) can lend and take some term deposits but cannot offer savings "
     "accounts or cheques, and NBFC deposits are not DICGC-insured. Both are RBI-regulated.",
     "RBI FAQs on NBFCs"),
    ("rbi", "What is a small finance bank or payments bank?",
     "Small finance banks (AU, Equitas, Ujjivan) are full banks focused on small loans; deposits are DICGC-insured and they "
     "often pay higher FD rates. Payments banks (Airtel, India Post, Fino) can take deposits up to ₹2 lakh per customer and "
     "offer payments, but cannot lend.",
     "RBI licensing guidelines for SFBs and payments banks"),
    ("rbi", "What is KYC and why do banks keep asking for it?",
     "Know Your Customer — identity and address verification (Aadhaar, PAN, passport) required under the PMLA rules before "
     "opening accounts and periodically after (every 2, 8 or 10 years depending on risk). Accounts can be frozen for missing "
     "re-KYC; RBI now allows updates through video, the app or a self-declaration if nothing changed.",
     "RBI Master Direction on KYC (2016, as amended)"),
    ("rbi", "What is the Liberalised Remittance Scheme?",
     "Under LRS resident individuals can send up to USD 250,000 abroad per financial year for education, travel, medical "
     "treatment, gifts, or investing in foreign stocks and property, without RBI approval. Banks collect TCS (20% above "
     "₹10 lakh, 5% for education/medical) which you can adjust against income tax.",
     "RBI LRS Master Direction; s.206C(1G)"),
    ("rbi", "What is the exchange rate and why does the rupee fall?",
     "The USD/INR rate is the price of a dollar in rupees, set in the forex market. The rupee weakens when India imports more "
     "than it exports, foreign investors pull money out, oil prices rise, or US interest rates go up; RBI intervenes with its "
     "reserves to smooth sharp moves. A weaker rupee makes imports (fuel, electronics, foreign education) costlier and "
     "exporters' earnings higher.",
     "RBI exchange-rate management; FEMA"),
    ("rbi", "What is CBDC or the e-rupee?",
     "The digital rupee is RBI's central bank digital currency — a legal-tender token in a bank-provided wallet, piloted since "
     "December 2022 for retail payments (including offline and via UPI QR codes). Unlike UPI it is money itself rather than a "
     "transfer of bank deposits, and unlike crypto it is issued and guaranteed by RBI.",
     "RBI CBDC concept note (Oct 2022); e₹-R pilot"),
]
