"""Author-written Indian finance Q/A — income tax, deductions, ITR, capital gains, GST, TDS (part 1 of 3).

Rows: (topic, question, answer, source_note). Facts follow the rates in backend/app/finance_rules.yaml (FY 2026-27
new-regime slabs = Finance Act 2025 rates, checked 2026-10-22) so the model and the calculator tools agree.
Worked numbers were computed with the project's own EMI/SIP/tax formulas before being written down.
"""
from __future__ import annotations

ROWS: list[tuple[str, str, str, str]] = [
    # ── income-tax regimes and slabs ───────────────────────────────────────
    ("tax_regime", "What are the income-tax slabs under the new regime?",
     "Under the new regime (section 115BAC, the default) the slabs for FY 2025-26 / FY 2026-27 are: up to ₹4 lakh nil; "
     "₹4–8 lakh 5%; ₹8–12 lakh 10%; ₹12–16 lakh 15%; ₹16–20 lakh 20%; ₹20–24 lakh 25%; above ₹24 lakh 30%. Add 4% health "
     "and education cess on the tax. Salaried people also get a ₹75,000 standard deduction, and the section 87A rebate "
     "(up to ₹60,000) makes the tax zero when taxable income is ₹12 lakh or less.",
     "Finance Act 2025 slabs; incometax.gov.in tax-slab page (carried into FY 2026-27 per app finance_rules.yaml)"),
    ("tax_regime", "What are the old-regime income-tax slabs?",
     "Old regime (for individuals below 60): up to ₹2.5 lakh nil; ₹2.5–5 lakh 5%; ₹5–10 lakh 20%; above ₹10 lakh 30%, plus "
     "4% cess. The 87A rebate of up to ₹12,500 applies if taxable income is ₹5 lakh or less, and the standard deduction "
     "for salaried people is ₹50,000. Its advantage is that deductions like 80C, 80D, HRA and home-loan interest still apply.",
     "Income-tax Act s.115BAC vs normal rates; incometax.gov.in"),
    ("tax_regime", "Is the new tax regime the default?",
     "Yes. Since FY 2023-24 the new regime is the default; you opt for the old regime when you file (salaried people can "
     "switch every year, people with business income can switch back only once). Your employer deducts TDS as per the "
     "new regime unless you declare otherwise.",
     "Finance Act 2023, s.115BAC(6)"),
    ("tax_regime", "I earn 12 LPA, which tax regime is better?",
     "Almost certainly the new regime. On a ₹12 lakh salary the new regime gives a ₹75,000 standard deduction, so taxable "
     "income is ₹11.25 lakh; the slab tax is ₹52,500 but the section 87A rebate wipes it out, so you pay ₹0. In the old "
     "regime, even with ₹1.5 lakh of 80C and the ₹50,000 standard deduction, taxable income is ₹10 lakh and tax is "
     "₹1,12,500 + 4% cess = ₹1,17,000. You would need enormous deductions (HRA plus home-loan interest plus 80C) for "
     "the old regime to win.",
     "Computed from Finance Act 2025 slabs with the app's income_tax_estimate tool"),
    ("tax_regime", "How much tax on a 15 lakh salary in the new regime?",
     "Taxable income = ₹15,00,000 − ₹75,000 standard deduction = ₹14,25,000. Slab tax: ₹4–8 lakh at 5% = ₹20,000; "
     "₹8–12 lakh at 10% = ₹40,000; ₹12–14.25 lakh at 15% = ₹33,750. Total ₹93,750, plus 4% cess ₹3,750 = ₹97,500 for the year "
     "(about ₹8,125 a month). No 87A rebate because taxable income exceeds ₹12 lakh.",
     "Computed from Finance Act 2025 slabs"),
    ("tax_regime", "At 15 LPA, how much deduction do I need for the old regime to beat the new one?",
     "New-regime tax on ₹15 lakh is ₹97,500. In the old regime the tax equals that when taxable income is about ₹9.06 lakh, "
     "so you need roughly ₹5.9 lakh of total deductions (including the ₹50,000 standard deduction) — for example HRA of "
     "₹2 lakh, 80C ₹1.5 lakh, home-loan interest ₹2 lakh. With only 80C + 80D + standard deduction (about ₹2.25 lakh) the "
     "old-regime tax is ₹1.95 lakh, so the new regime wins.",
     "Break-even computed from both slab tables (Finance Act 2025)"),
    ("tax_regime", "Tax on 20 lakh salary, new regime?",
     "Taxable income ₹19,25,000 after the ₹75,000 standard deduction. Tax: 5% on ₹4 lakh = ₹20,000; 10% on ₹4 lakh = ₹40,000; "
     "15% on ₹4 lakh = ₹60,000; 20% on ₹3.25 lakh = ₹65,000. Total ₹1,85,000 + 4% cess ₹7,400 = ₹1,92,400 a year.",
     "Computed from Finance Act 2025 slabs"),
    ("tax_regime", "Tax on 24 lakh salary under the new regime?",
     "Taxable income ₹23,25,000. Tax = ₹20,000 + ₹40,000 + ₹60,000 + ₹80,000 (16–20 lakh at 20%) + 25% of ₹3.25 lakh "
     "(₹81,250) = ₹2,81,250; add 4% cess ₹11,250 → ₹2,92,500 a year, roughly ₹24,400 a month.",
     "Computed from Finance Act 2025 slabs"),
    ("tax_regime", "Do I pay zero tax on 12.75 lakh salary?",
     "Yes, in the new regime. ₹12.75 lakh minus the ₹75,000 standard deduction leaves ₹12 lakh taxable; the slab tax of "
     "₹60,000 is fully covered by the section 87A rebate (max ₹60,000), so the tax is nil. This is why '₹12.75 lakh tax-free' "
     "was the Budget 2025 headline for salaried people.",
     "Finance Act 2025, s.87A rebate ₹60,000 up to ₹12 lakh taxable income"),
    ("tax_regime", "I earn 13 lakh — do I lose the whole rebate?",
     "No, marginal relief protects you. Taxable income is ₹12.25 lakh (after the ₹75,000 standard deduction); normal slab "
     "tax would be ₹63,750, but the law caps the tax at the income above ₹12 lakh, i.e. ₹25,000, plus 4% cess = ₹26,000. "
     "Marginal relief fades out around ₹12.75 lakh of taxable income, after which the full slab tax applies.",
     "s.87A marginal relief (Finance Act 2025)"),
    ("tax_regime", "What is the standard deduction?",
     "A flat deduction from salary or pension income that needs no bills: ₹75,000 in the new regime (raised from ₹50,000 by "
     "Budget 2024) and ₹50,000 in the old regime. It is applied automatically by your employer when computing TDS.",
     "s.16(ia) Income-tax Act; Finance (No. 2) Act 2024"),
    ("tax_regime", "Which deductions are still allowed in the new regime?",
     "Very few: the ₹75,000 standard deduction, the employer's NPS contribution under 80CCD(2) (up to 14% of basic + DA), "
     "the employer's EPF share, interest on a home loan for a let-out property (set off against rent), family-pension "
     "deduction, and deductions for Agniveer contributions. 80C, 80D, HRA, LTA and 24(b) on a self-occupied house are not "
     "available.",
     "s.115BAC(2) Income-tax Act"),
    ("tax_regime", "Can I switch between old and new regime every year?",
     "Salaried individuals (no business income) can choose either regime each year when filing the return. If you have "
     "business or professional income you can opt out of the new regime once (Form 10-IEA) and switch back only once in "
     "your lifetime.",
     "s.115BAC(6); Form 10-IEA"),
    ("tax_regime", "How is surcharge applied on income tax?",
     "Surcharge is a tax on the tax for high incomes: 10% if total income exceeds ₹50 lakh, 15% above ₹1 crore, 25% above "
     "₹2 crore, and 37% above ₹5 crore in the old regime (capped at 25% in the new regime). The 4% cess is then charged on "
     "tax plus surcharge. Marginal relief ensures the extra tax never exceeds the income above the threshold.",
     "Finance Act surcharge schedule; s.115BAC caps surcharge at 25%"),
    ("tax_regime", "What is the 4% cess on income tax?",
     "The Health and Education Cess is 4% charged on your income tax (plus surcharge, if any). For example, a slab tax of "
     "₹93,750 attracts cess of ₹3,750, so the final liability is ₹97,500.",
     "Finance Act 2018 onwards"),
    ("tax_regime", "What is taxable income vs gross income?",
     "Gross total income is everything you earned in the year — salary, house property, capital gains, business income, "
     "other sources. Taxable income is what remains after exemptions (like HRA) and deductions (standard deduction, 80C, "
     "80D in the old regime). Slabs apply to taxable income, not gross.",
     "Income-tax Act ss.14–80U structure"),
    ("tax_regime", "How is a senior citizen taxed in the old regime?",
     "For residents aged 60–79 the old-regime basic exemption is ₹3 lakh (₹5 lakh for 80 and above); the remaining slabs are "
     "the same (5% up to ₹5 lakh, 20% to ₹10 lakh, 30% above). Seniors also get 80TTB (₹50,000 on deposit interest) and a "
     "higher 80D limit of ₹50,000. In the new regime the slabs are the same for everyone.",
     "Finance Act rate schedule for senior / super-senior citizens"),
    ("tax_regime", "What is section 87A rebate?",
     "A rebate that cancels the tax for low and middle incomes. New regime: taxable income up to ₹12 lakh gets a rebate of up "
     "to ₹60,000 (so tax is nil), with marginal relief just above ₹12 lakh. Old regime: taxable income up to ₹5 lakh gets up "
     "to ₹12,500. The rebate does not cover special-rate income such as capital gains on listed shares.",
     "s.87A Income-tax Act, Finance Act 2025"),
    ("tax_regime", "Is income from a side freelance gig taxed differently from salary?",
     "It is taxed at the same slab rates but reported under 'profits and gains of business or profession'. You can deduct "
     "genuine expenses (laptop depreciation, internet, software) or use presumptive taxation under 44ADA (declare 50% of "
     "receipts as income, no books needed, receipts up to ₹50 lakh, or ₹75 lakh if cash receipts are ≤ 5%). Having business "
     "income means you file ITR-3 or ITR-4, not ITR-1.",
     "s.44ADA; ITR form eligibility rules"),
    ("tax_regime", "What is advance tax and when is it due?",
     "If your total tax after TDS exceeds ₹10,000 in a year you must pay it in instalments: 15% by 15 June, 45% by 15 "
     "September, 75% by 15 December and 100% by 15 March. Missing instalments costs 1% a month interest under sections 234B "
     "and 234C. Resident senior citizens without business income are exempt. Presumptive-scheme taxpayers can pay it all by "
     "15 March.",
     "ss.208, 211, 234B, 234C Income-tax Act"),
    ("tax_regime", "What is Form 16?",
     "Form 16 is the TDS certificate your employer must give you by 15 June for the previous financial year. Part A shows "
     "tax deducted and deposited quarter by quarter; Part B shows the salary break-up, exemptions, deductions and the tax "
     "computation. It is the main document for filing ITR-1, and it must match Form 26AS / AIS.",
     "Rule 31 Income-tax Rules; TRACES"),
    ("tax_regime", "What are Form 26AS and AIS?",
     "Form 26AS is your annual tax statement: TDS/TCS deducted, advance tax and self-assessment tax paid, and refunds. The "
     "Annual Information Statement (AIS) is broader — it also lists interest, dividends, share and mutual-fund transactions, "
     "rent and high-value purchases reported by third parties. Reconcile both with your return before filing; you can give "
     "feedback on wrong AIS entries on the e-filing portal.",
     "incometax.gov.in e-filing portal (AIS/TIS)"),
    ("tax_regime", "How is HRA exemption calculated?",
     "In the old regime the exempt HRA is the least of: (1) actual HRA received, (2) rent paid minus 10% of salary "
     "(basic + DA), (3) 50% of salary in Delhi, Mumbai, Kolkata or Chennai, else 40%. Example: basic ₹50,000/month, HRA "
     "₹20,000/month, rent ₹18,000/month in Bengaluru → (1) ₹2.4 lakh, (2) ₹2.16 lakh − ₹0.6 lakh = ₹1.56 lakh, (3) ₹2.4 lakh; "
     "exempt HRA = ₹1.56 lakh a year. Rent above ₹1 lakh a year needs the landlord's PAN.",
     "s.10(13A), Rule 2A"),
    ("tax_regime", "Can I claim HRA if I live with my parents?",
     "Yes, if you genuinely pay rent to them: transfer the rent to their bank account, keep a rent agreement and receipts, "
     "and they must show it as rental income in their return (they can claim the 30% standard deduction on it). You cannot "
     "claim HRA for a house you own yourself.",
     "s.10(13A); tax-department scrutiny practice"),
    ("tax_regime", "What is section 24(b)?",
     "Deduction for interest on a home loan. For a self-occupied house you can deduct up to ₹2 lakh of interest a year "
     "(old regime only); for a let-out property the full interest is deductible against rent, with the overall house-property "
     "loss set-off capped at ₹2 lakh a year. Pre-construction interest is claimed in five equal instalments after possession.",
     "s.24(b) Income-tax Act"),
    ("tax_regime", "What is section 80E?",
     "Deduction (old regime) for the interest paid on an education loan for yourself, spouse, children or a student you are "
     "legal guardian of, from a bank or approved institution. There is no upper limit, but it is available for 8 years from "
     "the year you start repaying. Only interest qualifies, not principal.",
     "s.80E Income-tax Act"),

    # ── deductions: 80C / 80D / 80CCD and friends ───────────────────────────
    ("deductions", "How does 80C work?",
     "Section 80C lets you deduct up to ₹1.5 lakh a year of eligible investments and expenses from taxable income in the "
     "old regime. Eligible items include EPF and VPF, PPF, ELSS mutual funds (3-year lock-in), life-insurance premiums, "
     "5-year tax-saver bank FDs, NSC, Sukanya Samriddhi, home-loan principal repayment, and tuition fees for up to two "
     "children. At the 30% slab, a full ₹1.5 lakh saves ₹46,800 of tax (including cess). It is not available in the new regime.",
     "s.80C Income-tax Act"),
    ("deductions", "Which investments qualify for 80C?",
     "EPF/VPF, PPF, Sukanya Samriddhi Yojana, NSC, 5-year tax-saver FD or post-office time deposit, ELSS mutual funds, life "
     "insurance premium (own, spouse, children), ULIPs, NPS Tier 1 (via 80CCD(1)), Senior Citizen Savings Scheme, home-loan "
     "principal, stamp duty on a house purchase, and tuition fees. The combined cap across 80C, 80CCC and 80CCD(1) is "
     "₹1.5 lakh.",
     "ss.80C, 80CCC, 80CCD(1), 80CCE"),
    ("deductions", "What is the lock-in for ELSS?",
     "Three years from the date of each investment — the shortest among 80C options (PPF is 15 years, tax-saver FD 5 years). "
     "For SIPs, each instalment has its own 3-year lock-in. After that, gains are long-term capital gains: 12.5% above "
     "₹1.25 lakh of equity LTCG a year.",
     "SEBI ELSS guidelines; s.80C(2)(xiii)"),
    ("deductions", "What is section 80D?",
     "Deduction (old regime) for health-insurance premiums: up to ₹25,000 for yourself, spouse and children, plus another "
     "₹25,000 for parents — ₹50,000 if they are senior citizens (and ₹50,000 for yourself if you are a senior). Up to ₹5,000 of "
     "preventive health check-ups fits inside these limits. Premiums must be paid by any mode other than cash.",
     "s.80D Income-tax Act"),
    ("deductions", "Maximum 80D deduction for a family with senior-citizen parents?",
     "₹75,000: ₹25,000 for your own family's policy plus ₹50,000 for senior-citizen parents. If you are also a senior citizen "
     "the total can reach ₹1 lakh. A senior parent with no insurance can claim actual medical expenses up to ₹50,000 instead.",
     "s.80D limits"),
    ("deductions", "What is 80CCD(1B)?",
     "An additional ₹50,000 deduction for your own contribution to NPS Tier 1, over and above the ₹1.5 lakh 80C limit — so "
     "old-regime taxpayers can deduct up to ₹2 lakh of NPS + 80C investments. At the 30% slab the extra ₹50,000 saves "
     "₹15,600 of tax. It is not available in the new regime.",
     "s.80CCD(1B) Income-tax Act"),
    ("deductions", "Is employer NPS contribution tax-free?",
     "Yes, under 80CCD(2): the employer's contribution to your NPS is deductible up to 14% of basic + DA (in the new regime "
     "and for government employees; 10% for private-sector employees in the old regime). This is one of the few deductions "
     "that survives in the new regime. Note the overall cap: employer EPF + NPS + superannuation above ₹7.5 lakh a year is "
     "taxable.",
     "s.80CCD(2); s.17(2)(vii)"),
    ("deductions", "What is 80TTA?",
     "Deduction of up to ₹10,000 a year on interest from savings bank accounts (not FDs) for individuals below 60 in the old "
     "regime. Senior citizens instead get 80TTB: up to ₹50,000 on interest from savings accounts and fixed deposits.",
     "ss.80TTA, 80TTB"),
    ("deductions", "Can I claim both 80C and 80CCD(1B) for NPS?",
     "Yes. Your own NPS contribution first counts under 80CCD(1) inside the ₹1.5 lakh 80C ceiling; any extra up to ₹50,000 "
     "goes under 80CCD(1B). Many people fill 80C with EPF/PPF/ELSS and use the ₹50,000 80CCD(1B) slot purely for NPS.",
     "ss.80CCD(1), 80CCD(1B), 80CCE"),
    ("deductions", "What is section 80G?",
     "Deduction for donations to approved charities and funds (old regime). Some funds like the PM National Relief Fund give "
     "100% deduction; most registered NGOs give 50%, sometimes limited to 10% of your adjusted gross income. Cash donations "
     "above ₹2,000 do not qualify; the donee must file Form 10BD and give you a certificate (Form 10BE).",
     "s.80G Income-tax Act"),
    ("deductions", "Do tuition fees qualify for 80C?",
     "Yes — tuition fees (not donations, development fees or transport) paid to any school, college or university in India "
     "for up to two children, inside the ₹1.5 lakh 80C limit. Both parents can claim separately for different children.",
     "s.80C(2)(xvii)"),
    ("deductions", "Does home-loan principal count under 80C?",
     "Yes, the principal portion of your home-loan EMIs (and stamp duty/registration charges in the year of purchase) is "
     "deductible under 80C within ₹1.5 lakh. The interest portion is claimed separately under 24(b) up to ₹2 lakh. If you sell "
     "the house within 5 years of possession the 80C claims are reversed.",
     "s.80C(2)(xviii), s.24(b)"),
    ("deductions", "What is Sukanya Samriddhi Yojana?",
     "A government small-savings scheme for a girl child under 10: deposit ₹250 to ₹1.5 lakh a year for 15 years, the "
     "account matures 21 years after opening (or on her marriage after 18). Interest is 8.2% a year (reviewed quarterly), "
     "and it is EEE — deposits under 80C, interest and maturity tax-free. ₹1.5 lakh a year for 15 years grows to roughly "
     "₹72 lakh at 8.2%.",
     "SSY rules; India Post / NSI rate table (8.2% for 2025-26)"),
    ("deductions", "What is NSC?",
     "National Savings Certificate: a 5-year post-office investment with a fixed rate (7.7% for 2025-26), compounded annually "
     "and paid at maturity. The investment qualifies for 80C, and the yearly accrued interest is deemed reinvested, so it "
     "also counts under 80C except in the final year. Interest is taxable at slab rates.",
     "National Savings Certificate (VIII Issue) rules; NSI rate table"),
    ("deductions", "Is life-insurance premium deductible?",
     "Under 80C, yes (old regime), provided the premium is no more than 10% of the sum assured for policies issued after "
     "1 April 2012. Maturity proceeds are tax-free under 10(10D) only if that 10% condition holds, and for policies issued "
     "after 1 April 2023 the aggregate annual premium must be ≤ ₹5 lakh (₹2.5 lakh for ULIPs).",
     "s.80C, s.10(10D) Income-tax Act"),
    ("deductions", "What is section 80DDB?",
     "Deduction (old regime) for the cost of treating specified serious illnesses (cancer, chronic kidney failure, "
     "Parkinson's, etc.) of yourself or a dependant: up to ₹40,000, or ₹1 lakh for a senior citizen, reduced by any "
     "insurance reimbursement. You need a prescription from the relevant specialist.",
     "s.80DDB, Rule 11DD"),
    ("deductions", "What is a tax-saver FD?",
     "A 5-year fixed deposit with a bank or post office that qualifies for 80C (up to ₹1.5 lakh). No premature withdrawal "
     "or loan against it. Interest is fully taxable at your slab and TDS applies, so the post-tax return is lower than "
     "PPF or ELSS for 30%-slab taxpayers.",
     "Bank Term Deposit Scheme 2006"),
    ("deductions", "What is LTA and how is it exempt?",
     "Leave Travel Allowance covers the travel fare (not hotels or food) for you and your family on holiday within India. It "
     "is exempt under 10(5) for two journeys in a block of four calendar years (current block 2026–29), limited to economy "
     "air fare or AC first-class rail fare by the shortest route. Old regime only; you must submit tickets to your employer.",
     "s.10(5), Rule 2B"),
    ("deductions", "How does deduction for a disabled dependant work (80DD)?",
     "If you maintain a dependant with at least 40% disability you can deduct a flat ₹75,000 (₹1.25 lakh for severe, 80%+ "
     "disability) regardless of actual spending, with a medical certificate in Form 10-IA. Section 80U gives the same flat "
     "amounts to a taxpayer who is themselves disabled. Old regime only.",
     "ss.80DD, 80U"),
    ("deductions", "Can I claim a deduction for rent without HRA?",
     "Yes, section 80GG (old regime): if you do not receive HRA and do not own a house where you live, you can deduct the "
     "least of ₹5,000 a month, 25% of total income, or rent paid minus 10% of total income. File Form 10BA with the return.",
     "s.80GG"),
    ("deductions", "What tax benefit does an electric-vehicle loan get?",
     "Section 80EEB allowed up to ₹1.5 lakh a year of interest on a loan for an electric vehicle, but only for loans "
     "sanctioned between 1 April 2019 and 31 March 2023. New loans get no such deduction; EVs still attract a lower GST of 5%.",
     "s.80EEB sunset 31 March 2023"),
    ("deductions", "What is the maximum tax I can save with all common old-regime deductions?",
     "A typical salaried stack: standard deduction ₹50,000, 80C ₹1.5 lakh, 80CCD(1B) ₹50,000, 80D ₹25,000 (₹75,000 with senior "
     "parents), 24(b) home-loan interest ₹2 lakh, plus HRA (varies). Excluding HRA that is about ₹5–5.5 lakh of deductions; at "
     "the 30% slab with cess, each ₹1 lakh of deduction saves ₹31,200.",
     "Sum of section limits; 30% slab × 1.04 cess"),
    ("deductions", "Is EPF withdrawal taxable?",
     "Not if you have five years of continuous service (periods with previous employers count if the balance was "
     "transferred). Withdrawing earlier makes the employer's contribution and all interest taxable, reverses the 80C "
     "benefit on your own contributions, and attracts 10% TDS if the amount exceeds ₹50,000 (20% without PAN).",
     "s.10(12), Rule 8 Part A Fourth Schedule; s.192A"),

    # ── ITR forms and filing ────────────────────────────────────────────────
    ("itr", "Which ITR form should a salaried person use?",
     "ITR-1 (Sahaj) if you are a resident individual with total income up to ₹50 lakh from salary or pension, one house "
     "property, other sources (interest, dividends) and agricultural income up to ₹5,000; from AY 2025-26 it also allows "
     "long-term capital gains on listed equity up to ₹1.25 lakh. If you have more than one house, foreign assets, unlisted "
     "shares, capital gains beyond that, or you are a company director, use ITR-2.",
     "ITR-1 eligibility notes, incometax.gov.in; CBDT notification for AY 2025-26 forms"),
    ("itr", "ITR-1 vs ITR-2 — what is the difference?",
     "ITR-1 is the simple form for resident individuals with salary, one house property and other-source income up to ₹50 lakh. "
     "ITR-2 is for individuals and HUFs without business income who have anything more complex: capital gains (beyond the "
     "small LTCG allowed in ITR-1), more than one house property, foreign income or assets, income above ₹50 lakh, "
     "directorships, unlisted shares, or losses to carry forward.",
     "ITR form eligibility, incometax.gov.in"),
    ("itr", "Who should file ITR-3?",
     "Individuals and HUFs with income from a business or profession that is not under the presumptive schemes — including "
     "freelancers keeping books, partners in firms, and anyone with futures-and-options or intraday trading income (these "
     "count as business income). ITR-3 also covers salary, house property and capital gains alongside.",
     "ITR-3 instructions, incometax.gov.in"),
    ("itr", "ITR-3 kiske liye hai?",
     "ITR-3 un individuals/HUF ke liye hai jinki income business ya profession se aati hai aur jo presumptive scheme (44AD/44ADA) "
     "nahi le rahe — jaise books rakhne wale freelancers, firm ke partners, aur F&O ya intraday traders (yeh business income "
     "maani jaati hai). Salary, house property aur capital gains bhi isi form mein report hote hain.",
     "ITR-3 instructions, incometax.gov.in"),
    ("itr", "What is ITR-4 (Sugam)?",
     "ITR-4 is for resident individuals, HUFs and partnership firms (not LLPs) with total income up to ₹50 lakh who declare "
     "business or professional income on a presumptive basis: 44AD (small business, 8% of turnover or 6% for digital receipts), "
     "44ADA (professionals, 50% of receipts) or 44AE (goods vehicles). From AY 2025-26 it also allows listed-equity LTCG up to "
     "₹1.25 lakh.",
     "ITR-4 eligibility; ss.44AD/44ADA/44AE"),
    ("itr", "Which ITR for salary plus capital gains from shares?",
     "ITR-2, unless the only capital gain is long-term gain on listed equity/equity funds of ₹1.25 lakh or less (then ITR-1 "
     "works from AY 2025-26). Any short-term capital gain, LTCG above ₹1.25 lakh, or losses to carry forward require ITR-2. "
     "If you also trade F&O or intraday, it becomes ITR-3.",
     "ITR-1/ITR-2 eligibility (AY 2025-26 changes)"),
    ("itr", "Which ITR form should a freelancer use?",
     "ITR-4 if you opt for presumptive taxation under 44ADA (gross receipts up to ₹50 lakh, or ₹75 lakh with ≤ 5% cash "
     "receipts; 50% of receipts deemed profit). If you want to deduct actual expenses or your receipts are higher, keep books "
     "and file ITR-3.",
     "s.44ADA; ITR-3/ITR-4 eligibility"),
    ("itr", "What is the due date for filing ITR?",
     "31 July after the end of the financial year for individuals who do not need an audit (for AY 2025-26 the CBDT extended "
     "it to mid-September 2025); 31 October for audit cases. A belated or revised return can be filed until 31 December of the "
     "assessment year, with a late fee of ₹5,000 (₹1,000 if total income is up to ₹5 lakh) and loss of carry-forward of most losses.",
     "s.139(1), s.139(4)/(5), s.234F"),
    ("itr", "Can I file a return after the deadline?",
     "Yes — a belated return under 139(4) until 31 December of the assessment year, with the 234F late fee (₹1,000 or ₹5,000) "
     "and interest under 234A on unpaid tax; business and capital losses cannot be carried forward. After that, an updated "
     "return (ITR-U) can be filed within 48 months of the end of the assessment year by paying 25% to 70% additional tax, but "
     "it cannot reduce tax or claim a refund.",
     "ss.139(4), 139(8A), 234F; Finance Act 2025 extended ITR-U to 48 months"),
    ("itr", "What is a revised return?",
     "If you discover a mistake after filing (missed income, wrong bank account, unclaimed deduction) you can file a revised "
     "return under 139(5) any number of times up to 31 December of the assessment year or before the assessment is completed. "
     "The revised return replaces the original.",
     "s.139(5)"),
    ("itr", "Do I need to file a return if my income is below the taxable limit?",
     "Not mandatory below the basic exemption, but you must file if you deposited ₹1 crore+ in current accounts (₹50 lakh in "
     "savings), spent ₹2 lakh+ on foreign travel or ₹1 lakh+ on electricity, had TDS/TCS of ₹25,000+ (₹50,000 for seniors), "
     "have foreign assets, or want a refund or to carry forward losses. Filing also helps with loans and visas.",
     "s.139(1) seventh proviso; Rule 12AB"),
    ("itr", "How do I e-verify my ITR?",
     "Within 30 days of filing: Aadhaar OTP, net-banking, bank-account or demat EVC, or a Digital Signature Certificate. "
     "Alternatively sign the ITR-V acknowledgement and post it to CPC Bengaluru. An unverified return is treated as not filed.",
     "CBDT notification 05/2022 (30-day verification window)"),
    ("itr", "What happens if I don't file ITR at all?",
     "The department can issue notices, levy the 234F late fee, charge 234A interest, and in serious cases prosecute. You lose "
     "refunds of excess TDS, cannot carry forward losses, and face higher TDS/TCS rates as a 'non-filer' under 206AB. Loan "
     "and visa applications usually ask for the last 2–3 years of ITRs.",
     "ss.234A, 234F, 206AB, 276CC"),
    ("itr", "What is Form 10-IEA?",
     "The form a person with business or professional income files to opt out of the new tax regime (or to re-enter it, which "
     "is allowed only once). It must be filed before the ITR due date. Salaried people without business income do not need "
     "it — they just pick the regime in the ITR.",
     "Rule 21AGA; s.115BAC(6)"),
    ("itr", "What is TDS mismatch and how do I fix it?",
     "If the TDS in your return does not match Form 26AS, CPC will reduce your credit. Fix it by asking the deductor (employer, "
     "bank) to revise their TDS return so the correct amount shows in 26AS, then file a rectification under 154 or a revised "
     "return. Always reconcile Form 16/16A with 26AS and AIS before filing.",
     "s.154; TRACES correction process"),
    ("itr", "How long does an income-tax refund take?",
     "Usually 2–6 weeks after e-verification once CPC processes the return, credited to a pre-validated bank account. Refunds "
     "earn 0.5% a month interest under 244A from 1 April (if the return was filed on time). Check status on the e-filing portal "
     "or NSDL's refund tracker.",
     "s.244A; e-filing portal refund status"),
    ("itr", "What is the presumptive scheme under 44AD?",
     "Small businesses with turnover up to ₹2 crore (₹3 crore if cash receipts are ≤ 5%) can declare 8% of turnover (6% for "
     "digital receipts) as profit without maintaining books or getting audited. Once opted, you should stay in it for 5 years; "
     "opting out early forces books and audit for the next 5 years. Not available for commission agents or professionals.",
     "s.44AD Income-tax Act"),
    ("itr", "When is a tax audit required?",
     "Under 44AB when business turnover exceeds ₹1 crore (₹10 crore if cash receipts and payments are each ≤ 5%), or "
     "professional receipts exceed ₹50 lakh, or when you declare profit below the presumptive rate while income exceeds the "
     "basic exemption. The audit report (Form 3CA/3CB-3CD) is due by 30 September; the ITR by 31 October.",
     "s.44AB"),
    ("itr", "Is F&O trading income business income?",
     "Yes — futures and options are treated as non-speculative business income, so you file ITR-3, can deduct expenses, and "
     "can carry forward losses for 8 years (set off against any business income). Intraday equity is speculative business "
     "(losses only against speculative gains, carried 4 years). Turnover for audit is computed from absolute profit and loss.",
     "s.43(5) proviso; ICAI guidance note on tax audit"),
    ("itr", "What is Form 15G / 15H?",
     "Self-declarations given to banks so that no TDS is deducted on interest when your total tax liability is nil: 15G for "
     "people under 60 (total income within the exemption limit and interest below it), 15H for senior citizens. Submit at the "
     "start of each financial year; the bank reports them to the department.",
     "s.197A; Rule 29C"),
    ("itr", "What are the consequences of a wrong HRA or 80C claim?",
     "If a claim cannot be backed by rent receipts, landlord PAN or investment proofs, the department can add the amount back, "
     "charge interest, and levy a penalty of 50% (under-reporting) or 200% (misreporting) of the tax evaded under 270A. The "
     "e-filing portal now cross-checks rent claims against the landlord's reported income.",
     "s.270A"),
    ("itr", "Can I file ITR myself for free?",
     "Yes. The incometax.gov.in e-filing portal is free: log in with PAN, pick the form, use the pre-filled data from AIS/26AS, "
     "check and submit, then e-verify. Most salaried people with Form 16 can finish ITR-1 in under an hour. Paid tools and CAs "
     "help when you have capital gains, business income or foreign assets.",
     "incometax.gov.in"),
    ("itr", "What is the difference between financial year and assessment year?",
     "The financial year (FY) is when you earn the income — 1 April to 31 March. The assessment year (AY) is the following "
     "year in which that income is assessed and the return is filed. Income earned in FY 2025-26 is reported in AY 2026-27.",
     "s.2(9) Income-tax Act"),
    ("itr", "Do I pay tax on gifts?",
     "Gifts above ₹50,000 in a year from non-relatives are taxed as 'income from other sources' at your slab (the whole "
     "amount, not just the excess). Gifts from relatives (spouse, parents, siblings, children, lineal ancestors/descendants "
     "and their spouses), at marriage, by will or inheritance are exempt. Cash gifts of ₹2 lakh or more are separately "
     "penalised under 269ST.",
     "s.56(2)(x); s.269ST"),

    # ── capital gains ───────────────────────────────────────────────────────
    ("capital_gains", "How is LTCG on equity taxed now?",
     "For listed shares and equity mutual funds held more than 12 months, long-term capital gains above ₹1.25 lakh a year are "
     "taxed at 12.5% (plus cess) since 23 July 2024; the first ₹1.25 lakh is exempt. Gains up to 31 January 2018 are "
     "grandfathered. Securities transaction tax must have been paid on the sale.",
     "s.112A as amended by Finance (No. 2) Act 2024"),
    ("capital_gains", "What is STCG tax on shares?",
     "Short-term capital gains on listed shares and equity funds (held 12 months or less) are taxed at 20% plus cess since "
     "23 July 2024 (15% before that). There is no exemption limit, but the gains can be set off against short-term or "
     "long-term capital losses.",
     "s.111A as amended by Finance (No. 2) Act 2024"),
    ("capital_gains", "LTCG on ₹2 lakh gains in equity — how much tax?",
     "Only ₹75,000 is taxable (₹2,00,000 − ₹1,25,000 exemption). Tax = 12.5% of ₹75,000 = ₹9,375, plus 4% cess ₹375 = ₹9,750. "
     "If you also had long-term capital losses, they reduce the gain first.",
     "s.112A computation"),
    ("capital_gains", "How are debt mutual funds taxed?",
     "Debt funds bought on or after 1 April 2023 (equity ≤ 35%) are 'specified mutual funds': all gains are taxed at your slab "
     "rate whatever the holding period, with no indexation. Units bought before April 2023 and sold after 23 July 2024 get "
     "12.5% without indexation if held over 24 months.",
     "s.50AA; Finance Act 2023 / Finance (No. 2) Act 2024"),
    ("capital_gains", "How is property capital gain taxed?",
     "A house sold after 24 months is long-term: 12.5% without indexation for sales from 23 July 2024; residents who bought "
     "before that date may instead pay 20% with indexation if it is lower. Short-term gains (≤ 24 months) are taxed at slab. "
     "You can save the tax by reinvesting in another house (section 54, up to ₹10 crore) or in 54EC bonds (₹50 lakh within "
     "6 months).",
     "ss.112, 54, 54EC; Finance (No. 2) Act 2024 grandfathering"),
    ("capital_gains", "What is indexation?",
     "Adjusting the purchase price for inflation using the Cost Inflation Index so that only real gains are taxed. Since "
     "23 July 2024 indexation has largely been removed (flat 12.5% LTCG), surviving only as an option for land and buildings "
     "bought before that date by resident individuals and HUFs.",
     "s.48 second proviso; CII notified yearly by CBDT"),
    ("capital_gains", "Can capital losses be carried forward?",
     "Yes, for 8 assessment years, provided you file the return by the due date. Short-term losses can offset short- or "
     "long-term gains; long-term losses only offset long-term gains. Losses cannot be set off against salary or other income.",
     "ss.70, 74, 80"),
    ("capital_gains", "How are crypto gains taxed in India?",
     "Virtual digital assets are taxed at a flat 30% plus cess on gains, with no deduction except the cost of acquisition, no "
     "set-off of losses against other income or other crypto, and 1% TDS on each transfer above ₹10,000 (₹50,000 for small "
     "taxpayers). Gifts of crypto are taxable for the receiver.",
     "s.115BBH, s.194S"),
    ("capital_gains", "What is the tax on gold?",
     "Physical gold, gold ETFs and gold funds sold after 24 months are long-term: 12.5% without indexation (since July 2024); "
     "within 24 months, gains are added to income at slab rates. Sovereign Gold Bonds are tax-free if held to the 8-year "
     "maturity; interest of 2.5% a year is taxable. Buying gold above ₹2 lakh in cash is barred; 3% GST applies on purchase.",
     "s.112; SGB scheme notification"),
    ("capital_gains", "Is dividend income taxable?",
     "Yes, since FY 2020-21 dividends are taxed in your hands at slab rates under 'income from other sources'. Companies and "
     "mutual funds deduct 10% TDS once dividends exceed ₹10,000 in a year (threshold raised in Budget 2025). Interest on a "
     "loan taken to buy the shares is deductible up to 20% of the dividend.",
     "s.56; s.194 / s.194K"),
    ("capital_gains", "How is an SIP taxed when I redeem?",
     "Each SIP instalment is a separate purchase, redeemed first-in-first-out. Units older than 12 months (equity) are "
     "long-term — 12.5% above the ₹1.25 lakh annual exemption; younger units are short-term at 20%. Your fund house's capital "
     "gains statement does this FIFO calculation for you.",
     "s.111A/112A; FIFO rule in s.45(2A)"),
    ("capital_gains", "Does section 54 apply to a flat under construction?",
     "Yes — to claim 54 exemption you must buy a residential house within 1 year before or 2 years after the sale, or complete "
     "construction within 3 years. Money not used by the ITR due date must be parked in a Capital Gains Account Scheme "
     "deposit. The exemption is capped at ₹10 crore of gains.",
     "s.54; CGAS 1988"),

    # ── GST ─────────────────────────────────────────────────────────────────
    ("gst", "What are the GST slabs?",
     "Since 22 September 2025 (the 'GST 2.0' rationalisation decided at the 56th GST Council meeting) India has two main rates: "
     "5% for merit goods and services and 18% as the standard rate, plus a 40% rate for sin and luxury items (tobacco, pan "
     "masala, aerated drinks, large cars). Many essentials — UHT milk, paneer, Indian breads, life and health insurance — are "
     "exempt. Special rates remain for gold/silver (3%) and rough diamonds (0.25%). The old 12% and 28% slabs were removed.",
     "GST Council 56th meeting recommendations (3 Sept 2025), effective 22 Sept 2025"),
    ("gst", "How do GST input tax credits work?",
     "Input tax credit (ITC) lets a registered business subtract the GST it paid on purchases from the GST it collects on "
     "sales, so tax applies only on value added. Conditions (section 16): a valid tax invoice, goods or services actually "
     "received, the supplier has paid the tax and reported the invoice (it appears in your GSTR-2B), you file your return, "
     "and you pay the supplier within 180 days. Example: ₹18,000 output GST − ₹11,000 ITC = ₹7,000 payable.",
     "CGST Act s.16; Rule 36(4)"),
    ("gst", "Which ITC is blocked under GST?",
     "Section 17(5) blocks credit on motor vehicles with up to 13 seats (unless used for transport business, driving schools "
     "or resale), food and beverages, outdoor catering, club and gym memberships, personal consumption, goods lost or given as "
     "free samples, works-contract and construction of immovable property for own use, and anything used for exempt supplies.",
     "CGST Act s.17(5)"),
    ("gst", "Who must register for GST?",
     "Businesses with aggregate turnover above ₹40 lakh for goods (₹20 lakh for services; ₹20 lakh / ₹10 lakh in special "
     "category north-eastern and hill states). Registration is compulsory regardless of turnover for inter-state suppliers of "
     "goods, e-commerce sellers (with some relief for small intra-state sellers), casual taxable persons, those liable under "
     "reverse charge, and input service distributors.",
     "CGST Act ss.22, 24; Notification 10/2019-CT"),
    ("gst", "What is the GST composition scheme?",
     "A simplified scheme for small businesses with turnover up to ₹1.5 crore (₹75 lakh in special-category states): pay a "
     "flat 1% of turnover (manufacturers and traders), 5% for restaurants, or 6% for service providers up to ₹50 lakh. You "
     "cannot collect GST from customers, cannot claim ITC, cannot sell inter-state, and file CMP-08 quarterly plus GSTR-4 "
     "annually.",
     "CGST Act s.10; Notification 2/2019-CT (Rate) for services"),
    ("gst", "What is the difference between CGST, SGST and IGST?",
     "On a sale within a state the GST is split equally into CGST (to the Centre) and SGST (to the state) — 18% becomes 9% + "
     "9%. On an inter-state sale or import the whole 18% is charged as IGST, collected by the Centre and shared. ITC of IGST "
     "can be used against IGST, CGST and SGST, but CGST credit cannot be used for SGST or vice versa.",
     "CGST, SGST and IGST Acts 2017"),
    ("gst", "GST at 18% on ₹45,000 — what is the total?",
     "GST = 18% × ₹45,000 = ₹8,100 (₹4,050 CGST + ₹4,050 SGST within a state, or ₹8,100 IGST inter-state). Invoice total = "
     "₹53,100. If a price is quoted GST-inclusive, the base is price ÷ 1.18: ₹53,100 ÷ 1.18 = ₹45,000.",
     "Arithmetic on the 18% standard rate"),
    ("gst", "What is reverse charge under GST?",
     "Normally the seller collects and pays GST; under reverse charge mechanism (RCM) the buyer pays it directly. It applies "
     "to notified cases such as goods transport agencies, legal services from advocates, sponsorship, security services from "
     "non-corporates, imported services, and some purchases from unregistered suppliers (e.g. by builders). RCM tax must be "
     "paid in cash and can then be claimed as ITC if eligible.",
     "CGST Act s.9(3)/(4); Notification 13/2017-CT (Rate)"),
    ("gst", "What is GSTR-1, GSTR-3B and GSTR-9?",
     "GSTR-1 reports your outward supplies invoice by invoice (monthly by the 11th, or quarterly under QRMP). GSTR-3B is the "
     "monthly summary return where you declare output tax, claim ITC and pay (by the 20th, or 22nd/24th for QRMP). GSTR-9 is "
     "the annual return due 31 December (GSTR-9C reconciliation if turnover exceeds ₹5 crore). GSTR-2B is the auto-drafted ITC "
     "statement you reconcile against.",
     "CGST Rules 59, 61, 80"),
    ("gst", "What is e-invoicing and who needs it?",
     "Businesses with aggregate turnover above ₹5 crore (in any year since 2017-18) must report B2B invoices to the Invoice "
     "Registration Portal, which returns an IRN and QR code; an invoice without it is invalid and the buyer cannot claim ITC. "
     "Invoices must be uploaded within 30 days for turnover above ₹10 crore.",
     "Notification 10/2023-CT; GSTN advisory on the 30-day limit"),
    ("gst", "What is an e-way bill?",
     "A document generated on the e-way bill portal before moving goods worth more than ₹50,000 (per invoice/consignment), "
     "containing the consignor, consignee, goods and vehicle details. Valid for 1 day per 200 km. Moving goods without it "
     "attracts a penalty of 200% of the tax or detention of the vehicle.",
     "CGST Rule 138"),
    ("gst", "What is the GST rate on restaurant bills?",
     "5% without input tax credit for standalone restaurants and food delivery (the delivery app collects it on restaurant "
     "orders); 18% with ITC in restaurants inside hotels with room tariff above ₹7,500. Service charge added by the restaurant "
     "is optional and not a tax.",
     "Notification 11/2017-CT (Rate) as amended; CCPA guidelines on service charge"),
    ("gst", "GST on restaurant bills?",
     "Most restaurant and food-delivery bills carry 5% GST (no input credit for the restaurant). Restaurants in hotels where "
     "rooms cost more than ₹7,500 a night charge 18%. Any 'service charge' is a restaurant tip, not GST, and can be refused.",
     "Notification 11/2017-CT (Rate); CCPA guidelines 2022"),
    ("gst", "Is GST charged on health insurance?",
     "Not any more for individuals: from 22 September 2025 premiums on individual life insurance (term, ULIP, endowment) and "
     "individual health insurance (including family floater and senior-citizen plans) are exempt from GST. Group policies "
     "bought by companies still attract 18%.",
     "GST Council 56th meeting decision, effective 22 Sept 2025"),
    ("gst", "What is GSTIN?",
     "A 15-character GST identification number: the first 2 digits are the state code, the next 10 are the PAN, the 13th is "
     "the entity number for that PAN in the state, the 14th is 'Z' by default and the 15th is a checksum. Always verify a "
     "supplier's GSTIN on the GST portal before claiming ITC.",
     "GST registration rules; gst.gov.in search taxpayer"),
    ("gst", "What is the penalty for late GST filing?",
     "Late fee of ₹50 a day (₹25 CGST + ₹25 SGST), or ₹20 a day for a nil return, capped per return based on turnover; plus "
     "interest at 18% a year on tax paid late (24% on wrongly claimed ITC). Non-filing for six months can lead to cancellation "
     "of registration, and GSTR-1 is blocked if GSTR-3B is pending.",
     "CGST Act ss.47, 50"),
    ("gst", "Can a freelancer claim GST input credit on a laptop?",
     "Yes, if the freelancer is GST-registered and the laptop is used for the taxable business: the 18% GST on the invoice "
     "(which must carry your GSTIN) can be claimed as ITC against the GST you charge clients. If you also use it personally, "
     "claim proportionately. Composition dealers cannot claim ITC.",
     "CGST Act ss.16, 17(1)"),
    ("gst", "Is GST applicable on exports of services?",
     "Exports are zero-rated: you can export under a Letter of Undertaking without charging GST and claim a refund of the ITC "
     "on your inputs, or pay IGST and claim it back. A service counts as an export only if the recipient is outside India, "
     "payment arrives in convertible foreign exchange (or INR where RBI permits) and the place of supply is outside India.",
     "IGST Act ss.2(6), 16"),
    ("gst", "What is the GST on a flat purchase?",
     "Under-construction homes: 5% without ITC (1% for affordable housing — up to ₹45 lakh and 60/90 sq m carpet area). "
     "Ready-to-move flats with a completion certificate, and resale flats, attract no GST (only stamp duty and registration).",
     "Notification 3/2019-CT (Rate)"),
    ("gst", "Do I need GST registration to sell on Amazon or Flipkart?",
     "Generally yes for sellers of goods — marketplaces require a GSTIN and deduct 0.5% TCS. Since October 2023, small "
     "intra-state sellers below the threshold can sell without registration using an enrolment number, but they cannot sell "
     "across states.",
     "CGST Act s.24(ix); Notification 34/2023-CT"),
    ("gst", "What is TCS under GST for e-commerce?",
     "E-commerce operators collect tax at source at 0.5% (0.25% CGST + 0.25% SGST, reduced from 1% in July 2024) on the net "
     "value of sales made through their platform and deposit it in GSTR-8. The seller sees it in their electronic cash ledger "
     "and can use it to pay GST.",
     "CGST Act s.52; Finance (No. 2) Act 2024 rate cut"),
    ("gst", "What is HSN / SAC code?",
     "HSN (Harmonised System of Nomenclature) codes classify goods and SAC codes classify services for GST rates and "
     "reporting. Businesses with turnover up to ₹5 crore must show 4-digit HSN on B2B invoices; above ₹5 crore, 6 digits. The "
     "code decides which rate applies, so a wrong HSN can mean a wrong tax rate.",
     "Notification 78/2020-CT"),
    ("gst", "Is GST payable on a UPI payment or bank transfer?",
     "No — GST is on the supply of goods or services, not on the mode of payment. UPI transactions themselves are free for "
     "consumers. The invoice amount already includes any GST the seller charges; paying by UPI, card or cash does not change it.",
     "GST levy is on supply (CGST Act s.9); NPCI UPI pricing"),
    ("gst", "What is the GST rate on mobile phones and laptops?",
     "Since the September 2025 rate rationalisation, mobile phones stay at 18% and laptops/computers at 18%. Earlier phones "
     "were at 12% before 2020 and 18% since; TVs up to 32 inches moved to 18% and larger TVs dropped from 28% to 18% in 2025.",
     "GST rate schedule as notified after the 56th Council meeting"),
    ("gst", "What are the GST rates on cars?",
     "After 22 September 2025 small cars (petrol up to 1,200 cc / diesel up to 1,500 cc, under 4 m) are taxed at 18% (down "
     "from 28% plus cess); larger cars, SUVs and luxury vehicles are at the 40% rate with no separate cess. Electric vehicles "
     "remain at 5%.",
     "GST Council 56th meeting rate schedule"),
    ("gst", "What is GST on gold jewellery?",
     "3% GST on the value of gold plus 5% GST on making charges (if billed separately). Buying gold worth ₹2 lakh or more in "
     "cash is prohibited under income-tax rules, and jewellers must note PAN for purchases above ₹2 lakh.",
     "GST rate schedule (3% on gold); s.269ST"),
    ("gst", "What is the time of supply under GST?",
     "The point when GST becomes payable. For goods it is the earlier of invoice date or delivery; for services the earlier "
     "of invoice (if issued within 30 days) or payment. Under reverse charge it is the earlier of payment or 60 days from "
     "invoice. This decides which month's GSTR-3B must include the tax.",
     "CGST Act ss.12, 13"),
    ("gst", "What is a credit note under GST?",
     "A document a supplier issues to reduce the value or tax on an earlier invoice (returns, discounts, errors). It is reported "
     "in GSTR-1 and reduces output tax, provided the buyer reverses the matching ITC and it is issued by 30 November following "
     "the financial year.",
     "CGST Act s.34"),
    ("gst", "What is the QRMP scheme?",
     "Quarterly Return, Monthly Payment: taxpayers with turnover up to ₹5 crore can file GSTR-1 and GSTR-3B quarterly while "
     "paying tax monthly through a challan (35% of the previous quarter's tax or self-assessed). The Invoice Furnishing Facility "
     "lets them upload B2B invoices monthly so buyers get ITC without delay.",
     "CBIC Notification 84/2020-CT"),
    ("gst", "Can I claim ITC on GST paid on office rent?",
     "Yes — rent for business premises is a taxable service at 18%, and a registered business can claim the ITC provided the "
     "landlord issues a proper tax invoice with your GSTIN and reports it. Residential property rented to a registered person "
     "for business falls under reverse charge, where you pay the GST and then claim it.",
     "CGST Act s.16; Notification 05/2022-CT (Rate) on residential rent RCM"),
    ("gst", "What is the GST refund process for excess ITC?",
     "Refunds arise mainly for exports/zero-rated supplies and inverted duty structure (inputs taxed higher than outputs). "
     "File RFD-01 within two years with invoices and a CA certificate above ₹2 lakh; 90% provisional refund for exporters "
     "within 7 days, final within 60 days, with interest at 6% if delayed.",
     "CGST Act ss.54, 56"),
    ("gst", "Do small businesses below the GST threshold need to issue tax invoices?",
     "No — an unregistered business cannot charge or collect GST and simply issues a bill of supply/normal invoice. Charging "
     "GST without registration is an offence. Many small firms still register voluntarily to claim ITC and to work with "
     "corporate clients who require a GSTIN.",
     "CGST Act ss.25(3), 32"),
    ("gst", "What is aggregate turnover for GST?",
     "The all-India total of taxable, exempt, export and inter-state supplies of all businesses under one PAN, excluding GST "
     "itself and inward supplies under reverse charge. It decides registration (₹40/20 lakh), the composition limit "
     "(₹1.5 crore), e-invoicing (₹5 crore) and annual-return thresholds.",
     "CGST Act s.2(6)"),

    # ── TDS / TCS ───────────────────────────────────────────────────────────
    ("tds", "What is TDS on FD interest?",
     "Banks deduct 10% TDS once the interest on all your deposits with that bank exceeds ₹50,000 in a financial year "
     "(₹1 lakh for senior citizens) — thresholds raised from ₹40,000/₹50,000 by Budget 2025. Without PAN the rate is 20%. The "
     "interest is still taxed at your slab; TDS is only an advance. Submit 15G/15H if your total income is below the "
     "taxable limit.",
     "s.194A as amended by Finance Act 2025"),
    ("tds", "What is TDS on FD?",
     "If a bank pays you more than ₹50,000 of interest in a year (₹1 lakh if you are a senior citizen) it deducts 10% as TDS "
     "and reports it in your 26AS. You then pay the balance tax at your slab (or claim a refund) when filing. Give Form 15G/15H "
     "to stop TDS if you have no tax liability.",
     "s.194A thresholds (Finance Act 2025)"),
    ("tds", "What is TDS on rent?",
     "Individuals and HUFs paying more than ₹50,000 a month of rent must deduct 2% TDS under 194-IB (reduced from 5% in "
     "October 2024), once a year, and deposit it with Form 26QC. Businesses deduct 10% under 194-I once annual rent crosses "
     "₹6 lakh (₹50,000 a month, raised in Budget 2025).",
     "ss.194-I, 194-IB"),
    ("tds", "TDS on professional fees?",
     "Section 194J: 10% on fees for professional services (CA, lawyer, doctor, consultant) and 2% on technical services, "
     "call-centre work and royalties for films, once payments to one person exceed ₹50,000 in the year (raised from ₹30,000 in "
     "Budget 2025). Individuals not subject to tax audit do not need to deduct.",
     "s.194J (Finance Act 2025 thresholds)"),
    ("tds", "What is TDS on contractor payments?",
     "Section 194C: 1% if the contractor is an individual or HUF, 2% otherwise, on a single payment above ₹30,000 or annual "
     "payments above ₹1 lakh. Deposit by the 7th of the next month and file quarterly Form 26Q; the contractor gets Form 16A.",
     "s.194C"),
    ("tds", "What is TCS on foreign remittance?",
     "Under the Liberalised Remittance Scheme banks collect 20% TCS on remittances above ₹10 lakh a year (threshold raised "
     "from ₹7 lakh in Budget 2025) for investments, gifts and tour packages; education and medical remittances above ₹10 lakh "
     "attract 5%, and education funded by a bank loan attracts no TCS. TCS is credited in 26AS and adjustable against your tax.",
     "s.206C(1G) as amended by Finance Act 2025"),
    ("tds", "What is TDS on salary and how is it computed?",
     "Under 192 the employer estimates your annual tax (in the regime you declare), subtracts tax already deducted, and "
     "deducts the balance evenly from monthly salary. Declare investments and rent early in the year; proofs are collected "
     "around January–February, and any shortfall is recovered in the last months.",
     "s.192; CBDT annual circular on salary TDS"),
    ("tds", "What is Form 16A?",
     "The TDS certificate for non-salary payments — bank interest, professional fees, rent, commission — issued quarterly by "
     "the deductor from TRACES. Match it with Form 26AS before claiming the credit in your return.",
     "s.203; Rule 31"),
    ("tds", "What is the TDS rate without PAN?",
     "If you do not provide a PAN, TDS is deducted at the higher of the normal rate or 20% under section 206AA (5% for "
     "194-O/194-Q cases), and you cannot claim the credit easily because it is not mapped to you. Always link PAN and Aadhaar "
     "— an inoperative PAN also triggers the 20% rate.",
     "s.206AA; CBDT circular on inoperative PAN"),
    ("tds", "Is TDS deducted on mutual fund redemptions?",
     "No TDS for resident investors on capital gains from mutual-fund redemptions; you pay the tax yourself. TDS of 10% applies "
     "only to dividend (IDCW) payouts above ₹10,000 a year under 194K. NRIs do face TDS on redemptions.",
     "s.194K; s.195 for non-residents"),
    ("tds", "What is TDS on buying property?",
     "If you buy immovable property worth ₹50 lakh or more you must deduct 1% TDS from the seller's payment under 194-IA, "
     "deposit it through Form 26QB within 30 days of the month-end, and give the seller Form 16B. Agricultural land is exempt; "
     "NRI sellers fall under section 195 instead (higher rates, TAN needed).",
     "s.194-IA"),
    ("tds", "What is TDS on cash withdrawals?",
     "Section 194N: banks deduct 2% TDS on cash withdrawals above ₹1 crore in a year from all accounts with that bank; for "
     "people who have not filed returns for 3 years the thresholds are ₹20 lakh (2%) and ₹1 crore (5%). It is adjustable "
     "against your tax.",
     "s.194N"),
    ("tds", "What is TDS on online gaming winnings?",
     "Net winnings from online games are taxed at a flat 30% under 115BBJ and the platform deducts 30% TDS under 194BA at "
     "withdrawal or year-end, with no threshold. Lottery, crossword and TV-show winnings are also taxed at 30% with TDS above "
     "₹10,000 per transaction.",
     "ss.115BBJ, 194BA, 194B"),
]
