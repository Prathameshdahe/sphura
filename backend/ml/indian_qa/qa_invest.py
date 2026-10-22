"""Author-written Indian finance Q/A — mutual funds, SIP maths, markets/SEBI, insurance, business accounting
(part 3 of 3). Rows: (topic, question, answer, source_note). SIP / lump-sum figures were computed with the
annuity-due formula used by backend/app/agent/tools/calculators.py before being written down.
"""
from __future__ import annotations

ROWS: list[tuple[str, str, str, str]] = [
    # ── mutual fund basics and types ────────────────────────────────────────
    ("mutual_funds", "What is a mutual fund?",
     "A pool of money from many investors managed by a SEBI-registered asset management company, invested in stocks, bonds "
     "or both according to a stated objective. You buy units at the day's NAV; the fund charges an expense ratio for "
     "management. Returns come from the change in NAV (and IDCW payouts if you choose that option).",
     "SEBI (Mutual Funds) Regulations 1996; AMFI investor education"),
    ("mutual_funds", "What is NAV?",
     "Net Asset Value is the per-unit value of a mutual fund: (market value of all holdings − liabilities) ÷ units outstanding, "
     "declared every business day. A higher NAV does not mean an expensive fund — ₹10,000 buys the same exposure whether the "
     "NAV is ₹10 or ₹500; what matters is the percentage change.",
     "SEBI MF regulations (daily NAV disclosure)"),
    ("mutual_funds", "What are the main types of mutual funds?",
     "By SEBI's categorisation: equity funds (large-cap, mid-cap, small-cap, flexi/multi-cap, ELSS, sectoral/thematic, value, "
     "focused), debt funds (overnight, liquid, ultra-short, money market, short duration, corporate bond, gilt, dynamic bond, "
     "credit risk), hybrid funds (aggressive, conservative, balanced advantage, arbitrage, multi-asset), solution-oriented "
     "(retirement, children) and others (index funds, ETFs, fund of funds).",
     "SEBI circular on categorisation and rationalisation of MF schemes (Oct 2017)"),
    ("mutual_funds", "What is a large-cap, mid-cap and small-cap fund?",
     "AMFI ranks listed companies by market capitalisation every six months: the top 100 are large-cap, 101–250 mid-cap, and "
     "251 onwards small-cap. A large-cap fund must hold at least 80% in large-caps (steadier), mid-cap funds 65% in mid-caps, "
     "small-cap funds 65% in small-caps (higher growth, much higher volatility). Flexi-cap funds can mix freely.",
     "SEBI categorisation circular 2017; AMFI half-yearly lists"),
    ("mutual_funds", "What is an index fund?",
     "A fund that simply copies an index like the Nifty 50 or Sensex, holding the same stocks in the same weights. It cannot "
     "beat the index but charges very little (expense ratios of 0.1–0.3% for direct plans) and avoids fund-manager risk; the "
     "small gap versus the index is called tracking error.",
     "SEBI definition of index funds; AMFI"),
    ("mutual_funds", "Index fund vs active fund — which is better?",
     "Index funds give market returns at very low cost; active funds try to beat the market and charge 1–2%. In India's "
     "large-cap space most active funds have struggled to beat the Nifty after costs over 5–10 years, so index funds are a "
     "sound default there; in mid/small-cap and some categories active managers have added value more often. Many investors "
     "hold a low-cost index core plus a few active satellites. This is education, not a recommendation.",
     "SPIVA India scorecards (S&P Dow Jones Indices)"),
    ("mutual_funds", "What is an ETF?",
     "An exchange-traded fund is an index fund listed on the stock exchange: you buy and sell units through a demat account "
     "at live market prices (not end-of-day NAV). ETFs have the lowest expense ratios but need a demat account, and thinly "
     "traded ETFs can trade at a premium or discount to NAV. No SIP facility unless your broker offers one.",
     "SEBI ETF framework; NSE ETF list"),
    ("mutual_funds", "ETF vs mutual fund?",
     "Both can track the same index. An ETF trades on the exchange in real time via demat, usually with lower costs, but "
     "needs liquidity and brokerage; an index mutual fund is bought from the AMC at the day's NAV, supports SIPs and automatic "
     "reinvestment, and needs no demat. For small monthly investing the index fund is simpler; for large lump sums the ETF "
     "can be cheaper.",
     "AMFI; SEBI product structures"),
    ("mutual_funds", "What is ELSS?",
     "Equity Linked Savings Scheme: a diversified equity mutual fund with a 3-year lock-in that qualifies for the ₹1.5 lakh "
     "80C deduction (old regime). It has the shortest lock-in among 80C options and equity-like returns, but also equity-like "
     "volatility. Gains after the lock-in are LTCG: 12.5% above ₹1.25 lakh a year.",
     "SEBI ELSS guidelines; s.80C"),
    ("mutual_funds", "What is a liquid fund and when to use it?",
     "A debt fund investing in money-market instruments maturing within 91 days — very low risk, no exit load after 7 days, "
     "money back in one working day (some offer instant redemption up to ₹50,000). Typically yields a bit more than a "
     "savings account; good for an emergency fund or parking money for a few months. Gains are taxed at your slab.",
     "SEBI liquid-fund rules (91-day maturity, 7-day exit load); s.50AA"),
    ("mutual_funds", "What is a debt fund?",
     "A mutual fund that lends — it holds government bonds, corporate bonds, treasury bills and commercial paper and earns "
     "interest plus price changes. Categories differ by maturity (overnight to long duration) and credit quality (gilt, "
     "corporate bond, credit risk). Returns are steadier than equity but not guaranteed; since April 2023 gains are taxed at "
     "slab rates like FD interest.",
     "SEBI debt-fund categories; Finance Act 2023"),
    ("mutual_funds", "FD vs debt fund?",
     "Both are now taxed at slab rates, so the comparison is about returns and flexibility. FDs guarantee the rate and are "
     "DICGC-insured to ₹5 lakh; debt funds have market and credit risk but no lock-in, no premature penalty, and in falling-rate "
     "periods can outperform FDs. For money needed within a year a liquid/ultra-short fund or an FD both work; for guaranteed "
     "outcomes the FD wins.",
     "SEBI debt categories; s.50AA; DICGC"),
    ("mutual_funds", "What is a gilt fund?",
     "A debt fund that holds only central and state government securities, so there is no credit risk — but long-maturity "
     "gilts swing sharply when interest rates move (interest-rate risk). Suited to investors with a 3+ year horizon who can "
     "sit through volatility, or for tactical bets on falling rates.",
     "SEBI gilt-fund category (min 80% in G-secs)"),
    ("mutual_funds", "What is a balanced advantage fund?",
     "A hybrid fund that moves between equity and debt dynamically based on valuations (e.g. P/E or P/B models) — more "
     "equity when markets are cheap, less when expensive. It is usually taxed as an equity fund because the AMC keeps gross "
     "equity exposure above 65% using arbitrage positions. Less volatile than pure equity funds.",
     "SEBI dynamic asset allocation category"),
    ("mutual_funds", "What is an arbitrage fund?",
     "A hybrid fund that buys a stock in the cash market and sells its future simultaneously to lock in the price difference, "
     "so its returns resemble a liquid fund (6–7%) with very low risk — but it is taxed as an equity fund (20% STCG, 12.5% LTCG "
     "above ₹1.25 lakh), which makes it attractive for high-slab investors parking money for 3–12 months.",
     "SEBI arbitrage fund category; s.111A/112A"),
    ("mutual_funds", "What is a fund of funds?",
     "A mutual fund that invests in other funds — e.g. international FoFs that buy a Nasdaq-100 ETF, or multi-asset FoFs. "
     "Costs stack (the FoF's ratio plus the underlying funds'), and most FoFs are taxed like debt funds (slab rates) unless "
     "they invest at least 65% in domestic equity funds, with some relief from FY 2025-26 for equity-oriented FoFs.",
     "SEBI FoF rules; Finance (No. 2) Act 2024 / Finance Act 2025 taxation of FoFs"),
    ("mutual_funds", "What is the expense ratio?",
     "The annual fee a fund deducts from its assets for management, distribution and operating costs, expressed as a "
     "percentage of AUM and already reflected in the NAV. SEBI caps it (up to 2.25% for small equity funds, lower as AUM grows; "
     "index funds and ETFs up to 1%). On a ₹10,000 monthly SIP for 20 years at 12%, a 1% higher ratio costs roughly ₹11 lakh of "
     "the ₹1 crore final value.",
     "SEBI (MF) Regulations Reg. 52 TER limits; computed illustration"),
    ("mutual_funds", "Direct vs regular mutual fund plans?",
     "Same portfolio, different cost: regular plans pay a distributor commission inside the expense ratio (usually 0.5–1.5% a "
     "year more); direct plans, bought from the AMC, MF Central, or platforms like Zerodha Coin, Groww and Kuvera, skip it. "
     "Over 20 years that difference compounds to roughly 15–20% more money in direct plans. Choose regular only if you value "
     "an adviser's service.",
     "SEBI direct-plan mandate (Jan 2013)"),
    ("mutual_funds", "What is an exit load?",
     "A charge deducted when you redeem before a set period — commonly 1% if you exit an equity fund within 1 year; liquid "
     "funds charge a tiny graded load for 7 days; many debt and index funds have none. It discourages short-term churn and "
     "goes back into the scheme, not to the AMC.",
     "SEBI exit-load rules"),
    ("mutual_funds", "What is growth vs IDCW option?",
     "Growth reinvests all profits inside the fund, so you gain through NAV appreciation and pay tax only when you sell. IDCW "
     "(income distribution cum capital withdrawal, formerly 'dividend') pays part of the NAV out periodically — it is not extra "
     "income, the NAV drops by the payout, and it is taxed at your slab with 10% TDS above ₹10,000. Growth is more tax-efficient "
     "for most investors.",
     "SEBI circular renaming dividend option to IDCW (2021); s.194K"),
    ("mutual_funds", "What is rupee cost averaging?",
     "Investing a fixed amount regularly (an SIP) buys more units when prices are low and fewer when high, so your average "
     "cost per unit tends to be lower than the average price. It removes the need to time the market and suits salaried "
     "investors, though a lump sum invested early beats an SIP in a steadily rising market.",
     "AMFI 'Mutual Funds Sahi Hai' SIP education"),
    ("mutual_funds", "What is XIRR and why is it used for SIPs?",
     "XIRR is the annualised return of a series of cash flows at different dates — exactly what an SIP is. A simple 'total gain "
     "÷ total invested' understates returns because later instalments had less time to grow. Fund statements and apps show "
     "XIRR; compare it with the fund's and the index's returns over the same dates.",
     "Standard IRR/XIRR definition (Excel XIRR)"),
    ("mutual_funds", "What is CAGR?",
     "Compound annual growth rate — the constant yearly rate that takes a starting value to an ending value: (end ÷ start)^(1/years) − 1. "
     "₹1 lakh growing to ₹2.5 lakh in 6 years is a CAGR of 16.5%; ₹50,000 to ₹2 lakh in 10 years is 14.9%. Use CAGR for lump sums "
     "and XIRR for SIPs.",
     "Computed: (2.5)^(1/6) − 1; (4)^(1/10) − 1"),
    ("mutual_funds", "What is a step-up SIP?",
     "An SIP whose instalment rises by a fixed amount or percentage every year, tracking salary growth. ₹5,000 a month stepped "
     "up 10% a year for 15 years at 12% grows to about ₹43.4 lakh (₹19.1 lakh invested), versus about ₹25.2 lakh for a flat "
     "₹5,000 SIP (₹9 lakh invested).",
     "Computed with monthly compounding and yearly step-up"),
    ("mutual_funds", "What is an STP and an SWP?",
     "A Systematic Transfer Plan moves a fixed sum periodically from one fund to another (typically liquid → equity) to "
     "average into the market after a lump-sum windfall. A Systematic Withdrawal Plan redeems a fixed amount each month — "
     "e.g. ₹30,000 a month from a ₹50 lakh corpus earning 8% leaves about ₹70 lakh after 20 years, because growth exceeds the "
     "withdrawal. Each STP/SWP leg is a taxable redemption.",
     "AMFI product definitions; computed SWP illustration"),
    ("mutual_funds", "How are mutual funds taxed in India?",
     "Equity funds (≥ 65% Indian equity): short-term gains (≤ 12 months) 20%; long-term 12.5% above ₹1.25 lakh a year. Debt "
     "and most other funds bought after 1 April 2023: gains added to income at slab rates, any holding period. ELSS has a "
     "3-year lock-in. IDCW payouts are taxed at slab with 10% TDS above ₹10,000. No TDS on redemptions for residents.",
     "ss.111A, 112A, 50AA; s.194K"),
    ("mutual_funds", "What is the riskometer?",
     "A SEBI-mandated dial on every scheme document with six levels — Low, Low to Moderate, Moderate, Moderately High, High, "
     "Very High — computed monthly from the portfolio's actual holdings (equity market-cap, debt credit and duration, "
     "liquidity). Small-cap and sectoral funds are 'Very High'; liquid funds 'Low to Moderate'.",
     "SEBI circular on product labelling / riskometer (Oct 2020)"),
    ("mutual_funds", "What is KYC for mutual funds?",
     "One-time identity verification (PAN, Aadhaar/address proof, photo, in-person or video) registered with a KRA (CAMS, "
     "KFintech, CVL). Status must be 'KYC validated' with Aadhaar-linked PAN to invest across AMCs; check at cvlkra.com or "
     "any KRA site. Minors need the guardian's KYC.",
     "SEBI KYC/KRA regulations; AMFI"),
    ("mutual_funds", "What is a consolidated account statement (CAS)?",
     "A single monthly or half-yearly statement listing all your mutual-fund folios (and demat holdings) across AMCs, "
     "generated by depositories/RTAs on your PAN. Request it from CAMS/KFintech or MF Central; it is the easiest way to see "
     "every SIP, folio and the current value in one place.",
     "SEBI circular on CAS; MF Central"),
    ("mutual_funds", "What is an NFO?",
     "A New Fund Offer is the launch of a new mutual-fund scheme at a ₹10 face value for a few weeks. The ₹10 price is not "
     "'cheap' — returns depend on the portfolio. Unless the NFO offers something existing funds don't (a new index or theme), "
     "an established fund with a track record is usually the safer choice.",
     "SEBI NFO regulations; AMFI education"),
    ("mutual_funds", "What is a sectoral or thematic fund?",
     "An equity fund concentrated in one sector (banking, IT, pharma) or theme (infrastructure, manufacturing, ESG) with at "
     "least 80% in it. Returns are cyclical and volatile; these are satellite bets to be timed and sized small (5–10% of "
     "equity), not a core holding.",
     "SEBI categorisation circular 2017"),
    ("mutual_funds", "Can I invest in US stocks via Indian mutual funds?",
     "Yes, through international funds and FoFs (Nasdaq-100, S&P 500, global tech), subject to SEBI's industry-wide overseas "
     "investment limits (USD 7 billion for MFs, USD 1 billion for ETFs), which sometimes pause fresh inflows. Alternatively use "
     "LRS to buy US stocks/ETFs directly through a broker; gains in both routes are taxed like debt/foreign assets (slab or "
     "12.5% LTCG after 24 months).",
     "SEBI overseas investment limits; RBI LRS"),

    # ── SIP and compounding maths ───────────────────────────────────────────
    ("sip", "What is a SIP?",
     "A Systematic Investment Plan is a standing instruction to invest a fixed amount in a mutual fund at a regular interval, "
     "usually monthly, from as little as ₹100–500. It builds discipline, averages your purchase cost over time, and compounds: "
     "₹5,000 a month for 10 years at 12% grows to about ₹11.6 lakh on ₹6 lakh invested. You can pause, increase or stop it any time.",
     "AMFI SIP education; computed with monthly compounding"),
    ("sip", "SIP of ₹5,000 for 10 years at 12%",
     "About ₹11.62 lakh at the end of 10 years — ₹6 lakh invested and roughly ₹5.6 lakh of gains (assuming a constant 12% a "
     "year compounded monthly; real returns will vary).",
     "Computed: annuity-due at 1% a month for 120 months"),
    ("sip", "SIP of 10,000 at 12% for 20 years",
     "Roughly ₹99.9 lakh — about ₹1 crore — on ₹24 lakh invested; gains of about ₹76 lakh show how much of the result comes "
     "from compounding in the later years.",
     "Computed: annuity-due at 1% a month for 240 months"),
    ("sip", "SIP of 10,000 at 15% for 20 years",
     "About ₹1.52 crore on ₹24 lakh invested. Compare ₹99.9 lakh at 12% — three extra points of return add ₹52 lakh over "
     "20 years, which is why costs and asset allocation matter.",
     "Computed with monthly compounding"),
    ("sip", "How much will 5,000 a month become in 10 years at 12%?",
     "About ₹11.6 lakh (₹6 lakh invested). Over 20 years the same SIP becomes about ₹50 lakh (₹12 lakh invested), and over "
     "5 years about ₹4.1 lakh (₹3 lakh invested).",
     "Computed with monthly compounding"),
    ("sip", "SIP of ₹2,000 for 5 years at 10%",
     "About ₹1.56 lakh on ₹1.2 lakh invested — roughly ₹36,000 of gains. Short horizons show modest compounding; the same "
     "₹2,000 for 20 years at 10% would be about ₹15.3 lakh.",
     "Computed with monthly compounding"),
    ("sip", "SIP of 20,000 at 12% for 15 years",
     "About ₹1.01 crore on ₹36 lakh invested. At 10% it would be about ₹83 lakh; at 14% about ₹1.22 crore.",
     "Computed with monthly compounding"),
    ("sip", "How much ₹10,000 a month becomes in 25 years at 12%",
     "About ₹1.90 crore on ₹30 lakh invested — nearly double the 20-year figure (₹1 crore), because the last five years add "
     "the most.",
     "Computed with monthly compounding"),
    ("sip", "SIP of ₹1,000 for 30 years at 12%",
     "About ₹35.3 lakh on just ₹3.6 lakh invested. Starting early matters more than the amount: ₹1,000 for 30 years beats "
     "₹2,000 for 20 years (₹20 lakh).",
     "Computed with monthly compounding"),
    ("sip", "SIP of 15,000 at 14% for 10 years",
     "About ₹39.3 lakh on ₹18 lakh invested.",
     "Computed with monthly compounding"),
    ("sip", "SIP of 25,000 at 12% for 20 years",
     "About ₹2.5 crore on ₹60 lakh invested.",
     "Computed with monthly compounding"),
    ("sip", "SIP of ₹3,000 for 15 years at 12%",
     "About ₹15.1 lakh on ₹5.4 lakh invested.",
     "Computed with monthly compounding"),
    ("sip", "How much SIP do I need for a ₹1 crore corpus?",
     "At 12% a year: about ₹10,000 a month for 20 years, ₹20,000 a month for 15 years, ₹43,000 a month for 10 years, or "
     "₹5,300 a month for 25 years. At 10% you need roughly 30% more. Remember ₹1 crore in 20 years is worth about ₹31 lakh of "
     "today's money at 6% inflation.",
     "Computed with monthly compounding; inflation discount 1.06^20"),
    ("sip", "How does compounding work? Show an example",
     "Compounding earns returns on past returns. ₹1 lakh at 12% a year is ₹1.12 lakh after year 1, ₹1.25 lakh after year 2 "
     "(12% on ₹1.12 lakh), ₹3.1 lakh after 10 years and ₹9.65 lakh after 20 years — the second decade adds ₹6.5 lakh versus "
     "₹2.1 lakh in the first. Formula: FV = PV × (1 + r)^n.",
     "Computed: 1.12^10 and 1.12^20"),
    ("sip", "What will ₹5 lakh become in 10 years at 10%?",
     "About ₹12.97 lakh (₹5,00,000 × 1.10^10). At 8% it would be ₹10.8 lakh and at 12% ₹15.5 lakh.",
     "Computed with annual compounding"),
    ("sip", "₹10 lakh lump sum at 12% for 15 years",
     "About ₹54.7 lakh (₹10,00,000 × 1.12^15).",
     "Computed with annual compounding"),
    ("sip", "What is the real return after inflation?",
     "Real return = (1 + nominal) ÷ (1 + inflation) − 1. A 12% return with 6% inflation is a real return of about 5.66%, not 6%. "
     "A 7% FD with 6% inflation gives just 0.9% real — and after 30% tax it is negative. Plan goals in real terms.",
     "Fisher equation; computed"),
    ("sip", "SIP vs lump sum — which is better?",
     "If you already have the money, a lump sum invested immediately wins more often than not in a rising market because "
     "money is invested longer; an SIP (or an STP over 6–12 months) reduces the regret of investing right before a crash and "
     "suits monthly salary flows. Practically: invest salary via SIP, and stagger windfalls over a few months.",
     "AMFI education; general empirical finding on time in market"),
    ("sip", "Should I stop my SIP when the market falls?",
     "A falling market is exactly when an SIP buys more units for the same money, which lowers your average cost and "
     "improves returns when markets recover. Stopping locks in the pain. Review the fund's performance versus its benchmark, "
     "not the market level — and keep an emergency fund so you never have to redeem in a downturn. This is general education.",
     "Rupee-cost-averaging mechanics; AMFI"),
    ("sip", "What is the 50/30/20 rule?",
     "A simple budget: 50% of take-home pay for needs (rent, food, EMIs, utilities), 30% for wants, 20% for savings and "
     "investments. On ₹60,000 take-home that is ₹30,000 / ₹18,000 / ₹12,000. Adjust it — a high-rent city may need 60/20/20, "
     "and raising savings to 30% early in your career makes retirement far easier.",
     "Popularised by Elizabeth Warren ('All Your Worth'); common budgeting guidance"),
    ("sip", "What is an emergency fund and how big should it be?",
     "Cash set aside for job loss, medical bills or urgent repairs so you never break investments or borrow at high rates. "
     "Target 3–6 months of essential expenses (6–12 if your income is irregular), kept in a savings account, sweep-in FD or "
     "liquid fund. Build it before starting long-term SIPs.",
     "Standard personal-finance guidance"),
    ("sip", "What is the 4% rule?",
     "A retirement rule of thumb: if you withdraw 4% of your corpus in the first year and raise it with inflation, a balanced "
     "portfolio has historically lasted 30 years (based on US data). So you need about 25× your annual expenses — ₹6 lakh a "
     "year of expenses implies a ₹1.5 crore corpus. India's higher inflation argues for a more conservative 3–3.5%.",
     "Bengen (1994) / Trinity study; adapted for Indian inflation"),
    ("sip", "What is net worth and how do I calculate it?",
     "Net worth = everything you own (bank balances, FDs, mutual funds, stocks, EPF/PPF, property, gold at market value) minus "
     "everything you owe (home loan, car loan, card dues, personal loans). Track it yearly; a rising net worth, not income, is "
     "the real measure of financial progress.",
     "Standard definition"),
    ("sip", "What is asset allocation?",
     "How you split money between asset classes — equity for growth, debt for stability, gold/real estate for diversification "
     "— based on your goals, horizon and risk tolerance. A common starting point is equity share = 100 − age (a 30-year-old "
     "holds ~70% equity), rebalanced yearly. Allocation drives most of the long-term outcome, more than fund selection.",
     "Brinson et al. (1986); general portfolio theory"),

    # ── markets, SEBI and stock basics ──────────────────────────────────────
    ("markets", "What is a stock?",
     "A share of ownership in a company. Buying a share entitles you to a slice of profits (dividends) and voting rights, and "
     "its price moves with the company's prospects and market sentiment. In India shares trade on the NSE and BSE through a "
     "SEBI-registered broker and are held electronically in a demat account.",
     "SEBI investor education; Companies Act 2013"),
    ("markets", "What is the Nifty 50?",
     "NSE's benchmark index of the 50 largest, most liquid Indian companies, weighted by free-float market capitalisation and "
     "reviewed every six months. It represents roughly two-thirds of NSE's free-float market cap and is the base for most "
     "Indian index funds, ETFs and derivatives.",
     "NSE Indices methodology"),
    ("markets", "What is the Sensex?",
     "The S&P BSE Sensex is BSE's index of 30 large, well-established companies, weighted by free-float market cap, with a base "
     "of 100 in 1978-79. It is India's oldest stock index and moves closely with the Nifty 50.",
     "BSE / Asia Index methodology"),
    ("markets", "What is the difference between NSE and BSE?",
     "Both are SEBI-regulated stock exchanges in Mumbai where the same large companies are listed. NSE (1992) has far higher "
     "trading volumes and dominates derivatives; BSE (1875) is Asia's oldest and lists more small companies. Prices are nearly "
     "identical; brokers let you pick either, and shares bought on one can be sold on the other.",
     "NSE and BSE exchange profiles"),
    ("markets", "What is market capitalisation?",
     "Share price × number of shares outstanding — the market's total valuation of a company. AMFI classifies the top 100 "
     "companies as large-cap, 101–250 as mid-cap and the rest as small-cap. Index weights use free-float market cap, which "
     "excludes promoter and locked-in holdings.",
     "AMFI classification; NSE Indices"),
    ("markets", "What is a P/E ratio?",
     "Price-to-earnings = share price ÷ earnings per share, i.e. how many years of current profit you pay for. A P/E of 25 "
     "means investors pay ₹25 per ₹1 of annual earnings. High P/E can mean expected growth or overvaluation; compare it with "
     "the company's history and sector peers rather than judging it alone.",
     "Standard valuation ratio"),
    ("markets", "Is a P/E of 25 high?",
     "It depends on growth and sector: the Nifty 50 has historically traded around 18–24, so 25 is slightly above average; a "
     "fast-growing consumer or IT company at 25 may be reasonable while a slow PSU at 25 looks expensive. Look at the PEG "
     "(P/E ÷ growth), ROE and peers before concluding.",
     "Nifty 50 historical P/E range (NSE)"),
    ("markets", "What is dividend yield?",
     "Annual dividend per share ÷ share price. A ₹20 dividend on a ₹1,000 share is a 2% yield. Mature companies (ITC, Coal India, "
     "PSU banks) often yield 3–6%; growth companies pay little. Dividends are taxed at your slab.",
     "Standard definition; s.56 taxation"),
    ("markets", "How do I start investing in stocks?",
     "Open a demat and trading account with a SEBI-registered broker (Zerodha, Groww, Upstox, bank brokers) using PAN, Aadhaar "
     "and a bank account; complete KYC; transfer money; then place orders during market hours (9:15–15:30). Start with index "
     "funds or large companies you understand, invest regularly, and never trade on tips or leverage.",
     "SEBI investor charter; broker onboarding"),
    ("markets", "What is a demat account?",
     "An electronic account with a depository (NSDL or CDSL, via a broker/DP) that holds your shares, ETFs, bonds and mutual-"
     "fund units the way a bank holds cash. It comes with a trading account for buying and selling; charges include a small "
     "annual maintenance fee and per-sale DP charges.",
     "Depositories Act 1996; NSDL/CDSL"),
    ("markets", "What are the steps to open a demat account?",
     "Pick a SEBI-registered broker, fill the online form, upload PAN, Aadhaar, a bank proof and a signature, complete "
     "e-KYC/in-person verification (video or Aadhaar OTP), e-sign the agreement, and add a nominee. The account is usually "
     "active within a day; add funds via UPI or net banking to start.",
     "Broker account-opening process; SEBI KYC norms"),
    ("markets", "How does an IPO work?",
     "A company sells shares to the public for the first time through a SEBI-approved prospectus. Retail investors apply via "
     "UPI/ASBA through their broker for lots within the price band (minimum lot ~₹14,000–15,000; up to ₹2 lakh for the retail "
     "category); money stays blocked, not debited, until allotment, which is by lottery when oversubscribed. Shares list on "
     "T+3 days. 35% of the issue is reserved for retail.",
     "SEBI ICDR Regulations; SEBI T+3 listing circular (2023)"),
    ("markets", "What is T+1 settlement?",
     "Shares you buy are credited to your demat and sellers get money one working day after the trade (T+1) — India moved to "
     "this in January 2023, and offers optional same-day (T+0) settlement for some stocks. Until settlement you cannot sell the "
     "shares you bought (except intraday).",
     "SEBI T+1 settlement circular; T+0 beta"),
    ("markets", "Why do stock prices move?",
     "Prices balance buyers and sellers, so anything that changes expected future profits or risk moves them: earnings and "
     "guidance, interest rates and RBI policy, inflation, oil and rupee moves, foreign-investor flows, government policy, "
     "global markets and sentiment. Short-term moves are mostly noise; long-term prices follow earnings.",
     "General market economics"),
    ("markets", "What is a stop loss?",
     "An order to sell automatically if the price falls to a level you set, limiting losses on a trade. A stop-loss market "
     "order sells at the next available price; a stop-limit sets a floor but may not fill in a fast fall. It is a trading "
     "tool — long-term investors in diversified funds rarely need one.",
     "Exchange order types (NSE)"),
    ("markets", "What is a circuit limit?",
     "Exchange-set daily price bands: individual stocks have 2–20% bands beyond which trading in that stock halts for the "
     "day; the market-wide circuit breaker pauses all trading when the Nifty/Sensex moves 10%, 15% or 20% in a day. Stocks "
     "with derivatives have no fixed band but a dynamic 10% filter.",
     "SEBI circuit-breaker circular (2001, amended); NSE price bands"),
    ("markets", "What is a bull market and a bear market?",
     "A bull market is a sustained rise (commonly 20% or more from a low) driven by optimism; a bear market is a fall of 20% or "
     "more from a peak with pessimism. Corrections are smaller (10%+) dips within a bull run. SIP investors benefit from "
     "continuing through bear phases.",
     "Common market definitions"),
    ("markets", "What is a bonus issue and a stock split?",
     "Both increase the number of shares without changing the company's value. A bonus (e.g. 1:1) gives free extra shares "
     "from reserves; a split lowers the face value (₹10 → ₹2 means 5× the shares). The price adjusts proportionally on the "
     "ex-date, so your holding value is unchanged; for tax, bonus shares have zero cost and a fresh holding period.",
     "Companies Act 2013; s.55 cost of bonus shares"),
    ("markets", "What is the record date and ex-date?",
     "The record date is when the company checks its register to decide who gets a dividend, bonus or rights; with T+1 "
     "settlement the ex-date is the same day — you must buy at least one trading day before to be eligible. On the ex-date the "
     "price drops by roughly the dividend amount.",
     "SEBI/exchange corporate-action norms post T+1"),
    ("markets", "What is STT?",
     "Securities Transaction Tax, charged on every exchange trade: 0.1% on delivery buys and sells of shares, 0.025% on "
     "intraday sells, 0.1% on options premium sell and 0.02% on futures (rates raised in Oct 2024), and 0.001% on equity "
     "mutual-fund redemptions. Paying STT is what makes equity gains eligible for the concessional 20%/12.5% rates.",
     "Finance (No. 2) Act 2024 STT schedule"),
    ("markets", "What is F&O and why is it risky?",
     "Futures and options are derivative contracts on an index or stock with leverage — a small margin controls a large "
     "position, so losses can exceed your capital. SEBI's study found about 9 in 10 individual F&O traders lost money "
     "(average loss over ₹1 lakh a year), which led to larger lot sizes and fewer weekly expiries in 2024–25. Treat it as "
     "speculation, not investing.",
     "SEBI study on individual traders in equity F&O (Sept 2024); SEBI F&O measures Oct 2024"),
    ("markets", "What are large-cap vs small-cap stocks?",
     "Large-caps (top 100 by market value — Reliance, TCS, HDFC Bank) are established, liquid and relatively stable; small-"
     "caps (rank 251+) are young or niche companies with higher growth potential but far bigger price swings and liquidity "
     "risk. Mid-caps sit between. Diversified funds blend them according to their mandate.",
     "AMFI market-cap classification"),
    ("markets", "What is a REIT?",
     "A Real Estate Investment Trust owns income-producing commercial property (offices, malls) and distributes at least 90% "
     "of its cash flows; units trade on the exchange like shares (Embassy, Mindspace, Brookfield, Nexus). You get rental yield "
     "of roughly 6–8% plus capital appreciation with small ticket sizes; distributions are taxed depending on their "
     "components. InvITs do the same for roads and power lines.",
     "SEBI (REIT) Regulations 2014"),
    ("markets", "What is a sovereign gold bond?",
     "Government bonds denominated in grams of gold, issued by RBI, with 2.5% a year interest plus the gold price at maturity "
     "(8 years; exit from year 5). Capital gains at maturity are tax-free for individuals. No fresh tranches have been issued "
     "since February 2024; existing bonds trade on the exchange.",
     "RBI SGB scheme; Budget 2025 discontinued new issues"),
    ("markets", "What is a registered investment adviser?",
     "A SEBI-registered RIA (under the 2013 IA Regulations) can give personalised investment advice for a fee and must act in "
     "your interest, with no commissions on products. Distributors (ARN holders) earn commissions and can only give incidental "
     "advice. Check registration on the SEBI website; unregistered 'finfluencers' cannot legally give stock tips.",
     "SEBI (Investment Advisers) Regulations 2013; SEBI finfluencer rules 2024"),
    ("markets", "Should I buy Reliance (or any stock) now?",
     "I can't tell you whether to buy a specific stock — that would be personalised advice, which only a SEBI-registered "
     "adviser who knows your finances can give. What I can do is explain how to evaluate it: check the latest price and P/E "
     "against its history and peers, read the quarterly results and debt levels, understand which businesses drive its "
     "earnings, and decide what share of your portfolio one company should be (rarely more than 5–10%).",
     "SEBI IA Regulations; general stock-analysis framework"),
    ("markets", "Which stocks will go up next month?",
     "Nobody can reliably predict short-term stock moves, and anyone claiming to is guessing or selling something. Over long "
     "periods prices follow earnings, so the evidence-based approach is diversified investing (index funds or well-run "
     "diversified funds) with a multi-year horizon, rather than trying to time next month. I can explain how to analyse a "
     "stock or build a portfolio if that helps.",
     "SEBI investor-protection guidance; efficient-markets evidence"),
    ("markets", "Is crypto a good investment?",
     "Crypto is legal to hold in India but unregulated, extremely volatile and taxed harshly — a flat 30% on gains, 1% TDS on "
     "every trade and no set-off of losses. If you choose to hold any, most guidance is to keep it a small speculative slice "
     "(a few percent) of money you can afford to lose, on exchanges registered with FIU-IND. That is education, not a "
     "recommendation.",
     "s.115BBH; FIU-IND registration of VDA exchanges"),

    # ── insurance ───────────────────────────────────────────────────────────
    ("insurance", "What is a term plan?",
     "Pure life insurance: you pay a small premium for a large sum assured (say ₹1 crore for roughly ₹10,000–15,000 a year for a "
     "healthy 30-year-old), paid to your family only if you die during the term. No maturity value, which is exactly why it is "
     "cheap. Cover 10–15× annual income plus loans; premiums qualify for 80C and payouts are tax-free.",
     "IRDAI product norms; s.10(10D)"),
    ("insurance", "Term vs endowment insurance?",
     "A term plan gives maximum cover per rupee; an endowment or money-back plan bundles insurance with savings, so cover is "
     "small and returns are usually only 4–6%. Most planners suggest 'buy term, invest the rest' — a term plan plus PPF/ELSS/"
     "index funds beats an endowment on both protection and returns. Surrendering an endowment early loses money.",
     "IRDAI surrender-value rules (2024); general planning guidance"),
    ("insurance", "What is a ULIP?",
     "A Unit Linked Insurance Plan mixes a small life cover with market-linked funds, charging mortality, fund-management and "
     "policy fees; there is a 5-year lock-in. Maturity is tax-free only if the annual premium is up to ₹2.5 lakh (policies "
     "after Feb 2021) and under 10% of the sum assured. A term plan plus mutual funds is usually cheaper and more flexible.",
     "IRDAI ULIP guidelines; s.10(10D) (Finance Act 2021)"),
    ("insurance", "How much health insurance do I need?",
     "A base family floater of at least ₹10 lakh in a metro (₹5 lakh in smaller cities), topped up with a super top-up of "
     "₹20–50 lakh for large hospitalisations, since a single ICU stay can cost ₹5–10 lakh. Buy young for lower premiums and "
     "shorter waiting periods; employer cover alone ends when the job does.",
     "IRDAI; general planning guidance on medical inflation"),
    ("insurance", "What are waiting periods in health insurance?",
     "Standard rules since IRDAI's 2024 reforms: a 30-day initial wait (except accidents), a maximum 3-year wait for "
     "pre-existing diseases (down from 4), specific waits for named conditions, and a 5-year moratorium after which claims "
     "cannot be rejected for non-disclosure. Cashless treatment must be authorised within 1 hour and discharge within 3 hours.",
     "IRDAI master circular on health insurance (May 2024)"),
    ("insurance", "What is a claim settlement ratio?",
     "The share of claims an insurer paid out of those received in a year — published by IRDAI. Look for 97%+ for term "
     "insurance, and also check the amount-based ratio and complaint volumes. A high ratio with a long track record matters "
     "more than a slightly cheaper premium.",
     "IRDAI annual report / public disclosures"),
    ("insurance", "Is insurance premium GST-free now?",
     "Yes for individuals: from 22 September 2025 premiums on all individual life policies (term, endowment, ULIP) and "
     "individual/family health policies are exempt from GST (previously 18%). Group policies bought by employers still "
     "attract GST.",
     "GST Council 56th meeting decision (Sept 2025)"),
    ("insurance", "What is the free-look period?",
     "After buying a life or health policy you have 30 days from receiving the policy document (extended from 15 days by "
     "IRDAI in 2024) to return it for a refund of the premium minus a small risk and stamp-duty charge. Use it to re-read the "
     "exclusions.",
     "IRDAI Protection of Policyholders' Interests Regulations 2024"),

    # ── business accounting and ratios ──────────────────────────────────────
    ("accounting", "How do I read a balance sheet?",
     "A balance sheet is a snapshot on one date of what a business owns (assets), owes (liabilities) and what is left for the "
     "owners (equity): assets = liabilities + equity. Assets are split into current (cash, receivables, inventory — within a "
     "year) and non-current (plant, property); liabilities into current (payables, short-term loans) and long-term debt. Read "
     "liquidity (current assets vs current liabilities), leverage (debt vs equity) and the trend across years.",
     "Companies Act 2013 Schedule III format"),
    ("accounting", "What is the current ratio and what does it mean?",
     "Current ratio = current assets ÷ current liabilities. It shows whether you can pay the next year's bills from assets "
     "that turn into cash within a year. Around 1.5–2 is comfortable for most businesses; below 1 means obligations exceed "
     "liquid assets (a liquidity strain), while a very high ratio can mean idle cash or bloated inventory.",
     "Standard liquidity ratio"),
    ("accounting", "What is the quick ratio?",
     "(Current assets − inventory) ÷ current liabilities — the 'acid test' that excludes stock because it may be slow to sell. "
     "Around 1 or above is healthy. A current ratio of 2 with a quick ratio of 0.5 signals that liquidity depends on moving "
     "inventory.",
     "Standard liquidity ratio"),
    ("accounting", "What is a good debt-to-equity ratio?",
     "Total debt ÷ shareholders' equity. Below 1 is conservative, 1–2 is common in capital-intensive industries, above 2 "
     "means heavy leverage and interest burden. Compare with peers: banks and NBFCs naturally run high ratios; IT and FMCG "
     "companies near zero.",
     "Standard leverage ratio"),
    ("accounting", "What is EBITDA?",
     "Earnings before interest, taxes, depreciation and amortisation — operating profit before financing and non-cash charges, "
     "used to compare the core profitability of businesses with different debt and asset bases. EBITDA margin = EBITDA ÷ "
     "revenue. It ignores capital spending and working capital, so always check cash flow too.",
     "Standard financial metric"),
    ("accounting", "What is gross margin vs net margin?",
     "Gross margin = (revenue − cost of goods sold) ÷ revenue: the markup on what you sell. Operating margin also subtracts "
     "overheads; net margin = net profit ÷ revenue after interest and tax. A shop with ₹10 lakh sales, ₹7 lakh COGS and ₹2 lakh "
     "overheads has a 30% gross margin and a 10% operating margin.",
     "Standard profitability ratios"),
    ("accounting", "What is working capital?",
     "Current assets − current liabilities: the money tied up in running the business day to day (inventory and receivables "
     "minus payables). Positive working capital funds operations; the cash conversion cycle (inventory days + receivable days − "
     "payable days) shows how long cash is locked up. Banks lend 'working capital limits' against it.",
     "Standard definition; RBI working-capital finance norms"),
    ("accounting", "What is the difference between a P&L and a cash flow statement?",
     "The profit and loss statement records revenue and expenses when earned/incurred (accrual), so profit can exist without "
     "cash — unpaid invoices are revenue. The cash flow statement tracks actual cash in and out, split into operating, "
     "investing and financing activities. A profitable firm with negative operating cash flow is a warning sign.",
     "Ind AS 7 / AS 3; Schedule III"),
    ("accounting", "What is accrual vs cash accounting?",
     "Accrual accounting records income when earned and expenses when incurred regardless of payment; cash accounting records "
     "them when money moves. Companies must use accrual (Companies Act); individuals and professionals may use cash basis for "
     "income tax under section 145. Accrual gives a truer picture of profitability; cash basis is simpler.",
     "s.145 Income-tax Act; Companies Act 2013"),
    ("accounting", "What is depreciation?",
     "Spreading the cost of a long-lived asset over its useful life as an annual expense. Companies Act uses useful lives "
     "(Schedule II; straight-line or written-down value); income tax uses WDV rates by block — e.g. 15% for plant and machinery, "
     "40% for computers, 10% for buildings — with only half the rate if the asset is used under 180 days in the year.",
     "Companies Act Schedule II; Income-tax Rule 5 / Appendix I"),
    ("accounting", "What is a trial balance?",
     "A list of every ledger account's debit or credit balance at a date; total debits must equal total credits, which checks "
     "that double-entry postings balance (not that they are correct). It is the raw material from which the P&L and balance "
     "sheet are prepared.",
     "Standard bookkeeping"),
    ("accounting", "What is DSCR?",
     "Debt service coverage ratio = cash available for debt service (usually EBITDA or net operating income) ÷ (interest + "
     "principal due in the year). Lenders want 1.25 or higher; below 1 means the business cannot pay its loans from operations.",
     "Bank credit-appraisal practice"),
    ("accounting", "What is interest coverage ratio?",
     "EBIT ÷ interest expense — how many times operating profit covers interest. Above 3 is comfortable; below 1.5 signals "
     "distress, and below 1 means the company isn't earning its interest.",
     "Standard solvency ratio"),
    ("accounting", "What is MSME registration and what are the limits?",
     "Udyam registration (free, online, Aadhaar + PAN) classifies a business by investment in plant/machinery and turnover — "
     "from April 2025: micro up to ₹2.5 crore investment and ₹10 crore turnover; small ₹25 crore / ₹100 crore; medium "
     "₹125 crore / ₹500 crore. Benefits include priority-sector loans, collateral-free CGTMSE cover, delayed-payment "
     "protection (45 days) and government tender preferences.",
     "MSME Development Act 2006; Budget 2025 revised criteria (effective 1 Apr 2025)"),
    ("accounting", "What is the 45-day MSME payment rule (section 43B(h))?",
     "Since FY 2023-24 a buyer can deduct an expense for goods or services from a registered micro or small enterprise only "
     "if it is paid within the MSMED Act time limit — 15 days without a written agreement, or up to 45 days with one. Amounts "
     "unpaid at year-end beyond the limit are disallowed (and allowed in the year of payment), plus interest at 3× the RBI bank "
     "rate is payable to the MSME.",
     "s.43B(h) Income-tax Act (Finance Act 2023); MSMED Act s.15"),
    ("accounting", "What are the books-of-account requirements for a small business?",
     "Under section 44AA, businesses with income above ₹2.5 lakh or turnover above ₹25 lakh (in any of the last 3 years) must "
     "keep books; professionals above ₹2.5 lakh income keep cash book, ledger and bills. Presumptive-scheme taxpayers are "
     "exempt. GST-registered firms must also keep invoices, stock and ITC records for 6 years.",
     "s.44AA; Rule 6F; CGST Act s.35"),
    ("accounting", "What is inventory turnover?",
     "Cost of goods sold ÷ average inventory — how many times a year stock is sold and replaced. ₹60 lakh COGS on ₹10 lakh "
     "average stock is 6× (about 61 days of inventory). Higher is leaner; a falling ratio hints at obsolete stock or slowing "
     "sales.",
     "Standard efficiency ratio"),
    ("accounting", "What is receivable days (DSO)?",
     "Days sales outstanding = (receivables ÷ credit sales) × 365 — the average time customers take to pay. 30 days is good; "
     "90+ days strains cash and raises bad-debt risk. Offer early-payment discounts, invoice promptly, and use the MSME "
     "Samadhaan portal for overdue dues from large buyers.",
     "Standard efficiency ratio; MSME Samadhaan"),
    ("accounting", "What is the difference between revenue, profit and cash?",
     "Revenue is total sales; profit is what remains after all expenses (gross → operating → net); cash is what is actually in "
     "the bank. A firm can have rising revenue, positive profit and still run out of cash if customers pay late or it over-"
     "invests in stock — which is why the cash flow statement matters.",
     "Standard accounting concepts"),
    ("accounting", "What is ROE and ROCE?",
     "Return on equity = net profit ÷ shareholders' equity — the return owners earn. Return on capital employed = EBIT ÷ "
     "(equity + debt) — the return on all long-term capital, better for comparing companies with different leverage. "
     "Consistent ROE/ROCE above 15% usually indicates a quality business.",
     "Standard profitability ratios"),
]
