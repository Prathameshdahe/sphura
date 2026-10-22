"""Labelled dataset for Sphura's finance intent router (6-way classifier that drives the LangGraph).

Labels (which branch of the graph a message needs):
  spending      the user's own money: statements, transactions, budgets, recurring charges, savings goals
  documents     grounded questions about uploaded finance documents: balance sheets, P&L, invoices, policies, reports
  market        live market data or finance news: stock / fund / index / FX quotes, "news about X", price today
  explain       finance education and calculations: concepts, EMI/SIP/FD/tax maths, how X works, comparisons
  advice        a request for a personal recommendation: "should I buy", "where should I invest", "is X a good buy"
  out_of_scope  anything that is not finance: coding, recipes, sports, homework, travel plans, chit-chat

The dataset has two parts:
  1. Template generation — per label, templates with typed slots × slot vocabularies × phrasing noise
     (prefix, suffix, casing, dropped punctuation), fixed seed, de-duplicated, per-template cap.
  2. HARD — hand-written examples on the class boundaries ("TCS share price" is market but "TCS in my
     portfolio" is spending; "what is a SIP" is explain but "should I start a SIP" is advice; "python script
     to parse my bank CSV" is out_of_scope).

Run from backend/:  .venv/Scripts/python -m ml.router_data      → ml/data/fin_router.jsonl
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

LABELS = ["spending", "documents", "market", "explain", "advice", "out_of_scope"]
SEED = 1729
PER_LABEL = {"spending": 300, "documents": 300, "market": 300, "explain": 320, "advice": 300, "out_of_scope": 360}
DATA_PATH = Path(__file__).resolve().parent / "data" / "fin_router.jsonl"

SLOTS: dict[str, list[str]] = {
    "category": ["food", "dining", "Swiggy", "Zomato", "groceries", "rent", "fuel", "travel", "Uber", "shopping",
                 "Amazon", "subscriptions", "Netflix", "EMIs", "utilities", "electricity", "cabs", "coffee",
                 "online shopping", "eating out", "petrol", "mobile recharges", "ATM withdrawals", "insurance",
                 "Blinkit", "Flipkart", "Myntra", "gym", "OTT", "medicines"],
    "period": ["last month", "this month", "in August", "in September", "last quarter", "this year", "in 2026",
               "last week", "over the last 3 months", "since April", "in Q2", "in the last 6 months", "in Diwali week",
               "in May and June", "year to date"],
    "goal": ["save 20%", "save ₹10,000 a month", "cut my expenses by 15%", "build a 3-month emergency fund",
             "save for a bike", "save ₹5 lakh in two years", "reduce my food spend", "stop overspending",
             "save for a Goa trip", "put aside 30% of my salary", "clear my credit card debt faster"],
    "stmt": ["bank statement", "statement", "HDFC statement", "SBI statement", "ICICI statement", "savings account",
             "credit card statement", "account statement", "CSV I uploaded", "Excel statement", "passbook export",
             "Kotak statement", "Axis statement", "PhonePe history", "Paytm statement"],
    "amount": ["₹5,000", "₹12,000", "₹2 lakh", "₹50,000", "₹999", "₹15,000", "₹1 lakh", "₹3,500", "₹25,000",
               "₹75,000", "₹20,000", "₹8,000"],
    "doc": ["balance sheet", "P&L statement", "profit and loss statement", "annual report", "invoice",
            "insurance policy", "cash flow statement", "audit report", "loan agreement", "Form 16", "GST return",
            "income statement", "quarterly results PDF", "term sheet", "mutual fund factsheet", "offer document",
            "credit card agreement", "home loan sanction letter", "salary slip", "ITR acknowledgement", "tax notice",
            "rental agreement", "trial balance", "ledger", "purchase order", "bank sanction letter"],
    "docq": ["what is the total revenue", "what are the current liabilities", "what is the net profit",
             "how much cash is on hand", "what is the depreciation figure", "what are the total assets",
             "what is the premium amount", "what is the interest rate mentioned", "what are the exclusions",
             "what is the due date", "what is the GST amount", "what is the tax deducted", "what is the EBITDA",
             "who is the auditor", "what is the coverage limit", "what is the processing fee", "what is the tenure",
             "what is the gross margin", "what is the receivables figure", "what is the equity", "what is the sum assured",
             "what was the operating expense", "what is the invoice total", "what is the closing balance",
             "how many shares are outstanding"],
    "ratio": ["current ratio", "quick ratio", "debt-to-equity", "gross margin", "net margin", "ROE", "ROCE",
              "interest coverage", "working capital", "asset turnover", "liquidity", "leverage", "operating margin",
              "EBITDA margin", "inventory turnover", "DSCR"],
    "stock": ["TCS", "Infosys", "Reliance", "HDFC Bank", "ICICI Bank", "Tata Motors", "Wipro", "SBI", "Adani Ports",
              "Zomato", "Paytm", "ITC", "Bajaj Finance", "Maruti", "Asian Paints", "Tata Steel", "Airtel", "HAL",
              "IRCTC", "Nykaa", "Apple", "Tesla", "Nvidia", "Microsoft", "Google", "Amazon stock", "Jio Financial",
              "LIC", "Coal India", "ONGC", "Titan", "Sun Pharma", "Hindustan Unilever", "Kotak Bank", "Axis Bank",
              "L&T", "DMart", "Vedanta", "NTPC", "Bharat Electronics"],
    "index": ["Nifty 50", "Sensex", "Bank Nifty", "Nifty IT", "Nasdaq", "S&P 500", "Dow Jones", "Nifty Midcap",
              "Nikkei", "FTSE 100", "Nifty Next 50"],
    "fund": ["Parag Parikh Flexi Cap", "SBI Small Cap", "Nippon India Growth Fund", "Mirae Asset Large Cap",
             "Quant Small Cap", "HDFC Mid Cap", "Axis Bluechip", "UTI Nifty 50 Index Fund", "ICICI Pru Technology Fund",
             "Motilal Oswal Nasdaq 100 FoF", "Kotak Emerging Equity", "SBI Contra Fund"],
    "fx": ["USD to INR", "dollar to rupee", "EUR to INR", "GBP to INR", "rupee vs dollar", "USD INR", "JPY to INR",
           "AED to INR", "SGD to INR", "CAD to INR"],
    "commodity": ["gold", "silver", "crude oil", "Brent crude", "Bitcoin", "Ethereum", "gold in Mumbai",
                  "24k gold", "natural gas", "copper"],
    "newsq": ["news", "latest news", "headlines", "what happened", "any updates", "why is it falling",
              "why is it up today", "quarterly results", "analyst views in the news", "latest developments"],
    "concept": ["SIP", "EMI", "a mutual fund", "an index fund", "ELSS", "NPS", "PPF", "EPF", "compound interest",
                "the new tax regime", "the old tax regime", "Section 80C", "Section 80D", "GST", "input tax credit",
                "ITR-1", "ITR-2", "ITR-4", "a credit score", "CIBIL score", "a fixed deposit", "a recurring deposit",
                "a balance sheet", "EBITDA", "the current ratio", "a P/E ratio", "a dividend yield", "a demat account",
                "NAV", "an expense ratio", "LTCG tax", "STCG tax", "TDS", "advance tax", "HRA exemption",
                "standard deduction", "a sovereign gold bond", "an ETF", "a liquid fund", "a debt fund",
                "a term insurance plan", "a ULIP", "the repo rate", "inflation", "CRR and SLR", "a bull market",
                "a stop loss", "an IPO", "a bonus issue", "a stock split", "a credit card billing cycle",
                "a UPI mandate", "a NACH mandate", "an overdraft", "a personal loan", "a home loan", "a top-up loan",
                "the 50/30/20 rule", "an emergency fund", "a REIT", "a gilt fund", "XIRR", "CAGR", "rupee cost averaging",
                "a step-up SIP", "a sweep-in FD", "a no-cost EMI", "a credit utilisation ratio", "a balance transfer",
                "the GST composition scheme", "reverse charge under GST", "e-invoicing", "a HUF", "Form 26AS", "AIS",
                "Section 87A rebate", "capital gains indexation", "a tax-saving FD", "a sweep account", "net worth",
                "a cash flow statement", "accrual accounting", "working capital", "a trial balance", "depreciation"],
    "calc": ["EMI on ₹10 lakh at 9% for 5 years", "EMI for a ₹25 lakh home loan at 8.5% for 20 years",
             "SIP of ₹5,000 for 10 years at 12%", "₹1 lakh FD at 7% for 3 years", "RD of ₹2,000 for 2 years at 6.5%",
             "tax on ₹12 lakh income in the new regime", "tax on 15 LPA old vs new regime", "₹50 lakh at 8% for 15 years",
             "SIP of ₹10,000 at 15% for 20 years", "car loan of ₹8 lakh at 10% for 7 years", "GST at 18% on ₹45,000",
             "HRA exemption on ₹30,000 rent in Bengaluru", "₹3 lakh personal loan at 14% for 3 years",
             "LTCG on ₹2 lakh gains in equity", "maturity of a ₹1.5 lakh PPF deposit per year for 15 years",
             "CAGR from ₹1 lakh to ₹2.5 lakh in 6 years", "step-up SIP of ₹5,000 growing 10% a year for 15 years",
             "income tax on ₹20 lakh salary in the old regime", "EMI on ₹2 lakh bike loan at 11% for 3 years",
             "how much ₹10,000 a month becomes in 25 years at 12%"],
    "compare": ["old vs new tax regime", "SIP vs lump sum", "FD vs debt fund", "PPF vs NPS", "ELSS vs PPF",
                "term vs endowment insurance", "index fund vs active fund", "home loan prepayment vs investing",
                "credit card vs debit card", "EPF vs NPS", "gold ETF vs sovereign gold bond", "RD vs SIP",
                "ETF vs mutual fund", "liquid fund vs savings account", "ITR-1 vs ITR-2", "GST regular vs composition",
                "floating vs fixed rate home loan", "large cap vs small cap", "direct vs regular mutual fund plans",
                "NPS Tier 1 vs Tier 2"],
    "buy": ["buy", "invest in", "put money in", "add", "pick", "go for", "start a SIP in", "get into", "accumulate",
            "sell", "exit", "book profits in", "hold", "average down on", "buy more of"],
    "goalq": ["retire at 45", "buy a house in 5 years", "my kid's education", "a ₹1 crore corpus", "my wedding",
              "financial freedom", "a passive income of ₹50k a month", "my parents' retirement", "a world trip",
              "a car in 2 years"],
    "amount_inv": ["₹5,000 a month", "₹10 lakh", "₹1 lakh", "₹50,000", "₹20,000 a month", "₹2 crore", "my bonus",
                   "₹25 lakh from a property sale", "my first salary", "₹3 lakh of savings"],
    "lang": ["Python", "JavaScript", "Java", "C++", "Rust", "Go", "TypeScript", "SQL", "bash", "Kotlin", "Swift", "R"],
    "codetask": ["reverse a linked list", "sort a dictionary by value", "parse JSON", "read a CSV file",
                 "write a binary search", "connect to PostgreSQL", "build a REST API", "implement a queue",
                 "find duplicates in a list", "scrape a website", "validate an email with regex", "merge two arrays",
                 "write unit tests", "deploy with Docker", "fix a null pointer exception", "use async/await",
                 "create a React component", "train a CNN", "write a Flask app", "compute Fibonacci"],
    "dish": ["biryani", "pasta", "dal makhani", "pancakes", "butter chicken", "masala dosa", "chole bhature",
             "chocolate cake", "pav bhaji", "paneer tikka", "ramen", "sushi", "rajma chawal", "idli sambar", "pizza",
             "samosa", "khichdi", "momos", "gulab jamun", "shawarma"],
    "sport": ["the IPL", "the cricket match", "India vs Australia", "the FIFA World Cup", "the Champions League",
              "Wimbledon", "the Olympics", "the F1 race", "the NBA finals", "the Pro Kabaddi final", "the Asia Cup",
              "the ICC T20 World Cup", "El Clasico", "the Ashes"],
    "subject": ["photosynthesis", "the French Revolution", "Newton's laws", "mitosis", "the water cycle",
                "quadratic equations", "the Mughal empire", "plate tectonics", "organic chemistry", "the Pythagoras theorem",
                "integration by parts", "the Cold War", "DNA replication", "Ohm's law", "the Indus Valley civilisation",
                "trigonometry", "the periodic table", "electromagnetic induction", "the Big Bang", "cell division"],
    "hw": ["essay", "summary", "5-mark answer", "assignment", "report", "presentation", "speech", "paragraph",
           "lab report", "poem", "project abstract", "book review"],
    "place": ["Goa", "Manali", "Kerala", "Ladakh", "Bali", "Dubai", "Japan", "Paris", "Coorg", "Rishikesh", "Sikkim",
              "Andaman", "Udaipur", "Hampi", "Thailand", "Vietnam", "Singapore", "Munnar", "Jaipur", "Varanasi"],
    "chat": ["hi", "hello", "hey there", "good morning", "how are you", "thanks", "thank you so much", "ok",
             "tell me a joke", "who are you", "what can you do", "bye", "lol", "cool", "nice", "haha", "hmm",
             "what's up", "good night", "are you a bot"],
    "health": ["headache", "fever", "back pain", "cold and cough", "sore throat", "acidity", "insomnia",
               "knee pain", "migraine", "stomach ache", "hair fall", "dry skin"],
    "movie": ["a Bollywood movie", "a Netflix series", "a sci-fi film", "a Korean drama", "an anime",
              "a thriller", "a Tamil movie", "a comedy show", "a documentary", "a Marvel movie"],
    "gadget": ["iPhone 17", "a laptop under 60k", "Galaxy S26", "a mechanical keyboard", "noise-cancelling headphones",
               "a gaming PC", "a smartwatch", "an air purifier", "a DSLR", "a tablet for notes"],
}

TEMPLATES: dict[str, list[str]] = {
    "spending": [
        "where did my money go {period}?", "how much did I spend on {category} {period}?",
        "what are my biggest expenses {period}?", "any subscriptions I forgot about in my {stmt}?",
        "can I {goal}?", "how much can I save if I cut {category} by half?", "show my spending by category {period}",
        "what recurring charges are on my {stmt}?", "analyse my {stmt}", "what's my total income vs expenses {period}?",
        "how many times did I order from {category} {period}?", "am I overspending on {category}?",
        "compare my spending {period} with the month before", "what did I spend {amount} on?",
        "break down my {stmt} by category", "which month was my most expensive?", "how much went to {category} {period}?",
        "list all my {category} transactions {period}", "what's my average monthly spend on {category}?",
        "find duplicate charges in my {stmt}", "how much did I withdraw from ATMs {period}?",
        "what percentage of my salary goes to {category}?", "did my rent go up {period}?",
        "summarise my {stmt} for {period}", "what was my net savings {period}?", "which merchants do I pay the most?",
        "how much did I transfer to friends {period}?", "what's my burn rate?", "track my {category} budget of {amount}",
        "set a budget of {amount} for {category}", "is my spending on {category} increasing?",
        "how much did I pay in bank charges {period}?", "what were my EMIs {period}?",
        "how much did I spend on weekends vs weekdays?", "categorise the transactions in my {stmt}",
        "what are my top 10 transactions {period}?", "how much did I spend on {category} and {category} together?",
        "what's left after my fixed expenses?", "if I keep spending like this, how much will I save {period}?",
        "what's my savings rate {period}?", "where can I cut costs based on my {stmt}?",
        "how much do I spend on {category} every month on average?", "flag unusual transactions in my {stmt}",
        "how much did I spend on UPI {period}?", "mera {category} ka kharcha kitna hua {period}?",
        "kitna paisa {category} pe gaya {period}?", "how much did I earn {period}?",
        "how much cashback did I get {period}?", "what are my monthly fixed costs?",
    ],
    "documents": [
        "{docq} in this {doc}?", "{docq} according to the uploaded {doc}?", "what is the {ratio} from my {doc}?",
        "summarise the attached {doc}", "is my liquidity healthy based on this {doc}?", "explain the {doc} I uploaded",
        "what does page 3 of the {doc} say about liabilities?", "compare the two {doc}s I uploaded",
        "calculate the {ratio} from the {doc}", "what should I watch in this {doc}?", "find the {ratio} in the attached file",
        "{docq} in the PDF?", "what are the key numbers in this {doc}?", "does the {doc} mention any pending dues?",
        "what is the total of all line items in this {doc}?", "which year does this {doc} cover?",
        "pull out revenue, expenses and profit from the {doc}", "are there red flags in this {doc}?",
        "what is the vendor name on the {doc}?", "what deductions are listed in my {doc}?",
        "how is the {ratio} trending across these {doc}s?", "from the {doc}, {docq}?",
        "what does clause 4 of the {doc} say?", "quote the exact figure for net profit from the attached {doc}",
        "what was the revenue growth according to the {doc}?", "in the uploaded {doc}, {docq}?",
        "list the assets and liabilities from this {doc}", "what's the premium and the coverage in the attached {doc}?",
        "check the {doc} and tell me the interest rate", "is the {ratio} in my {doc} good or bad?",
        "what are the payment terms on this {doc}?", "extract the table from the {doc} and total it",
        "based on the {doc}, how much tax was deducted?", "which expenses grew the most in this {doc}?",
        "what does the auditor say in the {doc}?", "is this {doc} for FY 2025-26?",
        "what's the HSN code on this {doc}?", "how much GST is charged on the attached {doc}?",
        "what is the loan amount in the attached {doc}?", "read my {doc} and tell me the {ratio}",
        "what are the exclusions in the uploaded {doc}?", "does the {doc} say anything about prepayment charges?",
        "what is the closing balance in the uploaded {doc}?", "who signed the {doc}?",
        "what's the difference between the two {doc}s?", "is the company profitable according to its {doc}?",
        "what is the equity figure in the {doc}?", "give me a one-paragraph summary of this {doc}",
    ],
    "market": [
        "{stock} share price today", "what's the {stock} stock price right now?", "how is {index} doing today?",
        "{newsq} about {stock}", "{stock} {newsq}", "current {fx} rate", "what is the {fx} exchange rate today?",
        "{commodity} price today", "latest {commodity} rate", "NAV of {fund} today", "how did {stock} close today?",
        "is {index} up or down today?", "{stock} 52 week high", "{stock} market cap", "{stock} quarterly results today",
        "what's the {index} level now?", "news about {fund}", "{stock} price chart for the last month",
        "how much did {stock} move this week?", "top gainers on {index} today", "why did {stock} fall today?",
        "why is {index} up today?", "latest finance news", "what's happening in the markets today?",
        "RBI policy news today", "did SEBI announce anything today?", "{stock} dividend news", "{stock} results date",
        "{stock} ki price kya hai aaj?", "aaj {index} kaisa hai?", "{commodity} ka rate kya hai aaj?",
        "quote for {stock}", "{stock} live price", "{stock} share rate", "{stock} vs {stock} price comparison today",
        "what is the P/E of {stock} right now?", "{fund} returns this year", "{fund} NAV history", "{fx} today",
        "{stock} pre-market", "{stock} after hours", "how is {stock} trading today?", "latest on {stock} buyback",
        "{index} today's performance", "{stock} 1 year return", "{stock} closing price yesterday",
        "{stock} high and low today", "any news on {stock} merger?", "stock market news today India",
        "what did the market do this week?", "{commodity} futures price",
    ],
    "explain": [
        "what is {concept}?", "explain {concept} simply", "how does {concept} work?", "{concept} meaning",
        "{calc}", "calculate {calc}", "what's the {calc}?", "compute {calc}", "{compare} — which is better and why?",
        "explain {compare}", "difference between {compare}", "how is {concept} taxed?", "how do I claim {concept}?",
        "what are the rules for {concept}?", "give me an example of {concept}", "{concept} explained like I'm 15",
        "how to calculate {concept}?", "formula for {concept}", "what is the limit for {concept}?",
        "is {concept} tax free?", "who should use {concept}?", "pros and cons of {concept}",
        "how does {concept} affect my taxes?", "what documents are needed for {concept}?",
        "when is the deadline for {concept}?", "what happens if I miss {concept}?", "can you show the maths for {calc}?",
        "{concept} kya hota hai?", "{concept} samjhao", "how is {concept} different from {concept}?",
        "what are the GST slabs?", "how do GST input tax credits work?", "which ITR form should a freelancer use?",
        "what is the UPI transaction limit per day?", "what happens if a UPI payment fails but money is debited?",
        "how is EPF interest calculated?", "how does the 80C deduction work?", "what is the lock-in for ELSS?",
        "how is a credit score calculated?", "how do I read a balance sheet?", "what is a good {ratio}?",
        "how do I compute {ratio}?", "what does a high {ratio} mean?", "teach me the basics of {concept}",
        "how is EMI calculated?", "how does SIP compounding work?", "what's the maths behind {concept}?",
        "how much tax do I pay on {amount} of FD interest?", "how is HRA calculated?",
        "what is the rebate under section 87A?", "explain {concept} with numbers",
    ],
    "advice": [
        "should I {buy} {stock}?", "is {stock} a good buy right now?", "should I {buy} {fund}?",
        "where should I invest {amount_inv}?", "what should I do with {amount_inv}?", "is it a good time to {buy} {commodity}?",
        "which mutual fund should I pick for {goalq}?", "should I {buy} {stock} or {stock}?",
        "how should I invest for {goalq}?", "which stocks will go up next month?", "give me a stock tip",
        "what's the best investment for {amount_inv}?", "should I prepay my home loan or invest in {fund}?",
        "is {fund} good for the long term?", "should I switch from {fund} to {fund}?", "which is the best {index} stock to buy?",
        "recommend a portfolio for {amount_inv}", "should I sell my {stock} shares now?", "is {commodity} going to rise?",
        "will {stock} double in a year?", "should I take a personal loan to invest in {stock}?",
        "{stock} lena chahiye kya?", "{amount_inv} kahan invest karu?", "should I {buy} {commodity} before Diwali?",
        "pick 5 stocks for me", "is it safe to {buy} {stock} at this price?", "which SIP is best for me?",
        "should I move my money from FD to {fund}?", "what's the best stock under ₹100?", "which crypto should I buy?",
        "should I invest in {stock} IPO?", "is {stock} overvalued, should I exit?", "best mutual fund for {goalq}?",
        "should I stop my SIP in {fund}?", "how much of my salary should go into {fund}?",
        "should I {buy} {index} ETF now or wait for a dip?", "is this a good time to enter the market?",
        "should I book profits in {stock}?", "will {index} crash this year?", "which bank stock is the best buy?",
        "I have {amount_inv}, which stock should I buy today?", "should I invest in {commodity} or {stock}?",
        "is {fund} better than {fund} for me?", "tell me what to buy for quick returns",
        "should I take a loan against my {fund} units?", "is real estate or {stock} better for me?",
        "should I invest my emergency fund in {fund}?", "what allocation should I have between equity and debt?",
        "should I {buy} {stock} after today's fall?", "suggest a stock that will give 20% in 6 months",
    ],
    "out_of_scope": [
        "write a {lang} function to {codetask}", "how do I {codetask} in {lang}?", "fix this {lang} error for me",
        "explain {codetask} in {lang}", "recipe for {dish}", "how do I cook {dish}?", "what goes into {dish}?",
        "who won {sport}?", "what's the score of {sport}?", "when is {sport} starting?", "explain {subject}",
        "write a {hw} on {subject}", "help me with my {subject} homework", "summarise {subject} for my exam",
        "plan a trip to {place}", "best time to visit {place}?", "what to pack for {place}?", "{chat}",
        "I have a {health}, what should I do?", "home remedy for {health}", "recommend {movie}", "suggest {gadget}",
        "which is better, {gadget} or {gadget}?", "write a poem about {place}", "translate 'good morning' to Tamil",
        "what's the weather in {place} tomorrow?", "tell me a story about a dragon", "who is the prime minister of Japan?",
        "how tall is Mount Everest?", "write a cover letter for a software job", "draft an email to my professor",
        "what is the capital of Australia?", "how do I lose weight?", "give me a workout plan", "best books on {subject}",
        "solve 2x + 3 = 11", "what is the derivative of x^2?", "how to improve my English speaking?",
        "write a birthday wish for my mom", "what should I name my dog?", "explain how a rocket works",
        "debug my {lang} code", "convert this {lang} code to {lang}", "write SQL to {codetask}",
        "what are the symptoms of {health}?", "how to make {dish} without onion?", "{sport} highlights",
        "who is the best player in {sport}?", "what's a good gift for a friend who likes {place}?",
        "describe the plot of {movie}", "how do I set up a {lang} dev environment?", "what is machine learning?",
        "{subject} ke notes bana do", "mujhe {dish} ki recipe batao", "{place} jane ka best time?",
    ],
}

PREFIXES = ["hey, ", "hi! ", "quick question: ", "ok so ", "can you tell me ", "please ", "yo ", "hello, ",
            "I was wondering, ", "sphura, ", "umm ", "so ", "just curious, ", "help: ", "need help: ", "", "", "",
            "", "", "", "", "", ""]
SUFFIXES = [" thanks", " pls", " please", " asap", " :)", " thank you!", " — keep it short", " (in detail)",
            " in hindi", " in simple words", " quickly", " for me", "", "", "", "", "", "", "", "", "", "", ""]

# Hand-written hard / boundary cases.
HARD: list[tuple[str, str]] = [
    # spending vs market
    ("how much TCS stock do I hold according to my statement?", "spending"),
    ("what did I pay Zerodha last month?", "spending"),
    ("my SIP debits — how much went out in September?", "spending"),
    ("how much did I spend on Amazon this year", "spending"),
    ("I spent too much on Swiggy, show me the numbers", "spending"),
    ("list every Netflix charge on my card", "spending"),
    ("why is my electricity bill higher this month", "spending"),
    ("which day of the month do most of my EMIs hit?", "spending"),
    ("how much salary came in this quarter?", "spending"),
    ("total of all UPI payments to Rahul", "spending"),
    ("my spends last month pls", "spending"),
    ("statement analysis", "spending"),
    ("where does my money go", "spending"),
    ("how much do I pay in subscriptions in a year?", "spending"),
    ("am I living paycheck to paycheck?", "spending"),
    ("I want to save 20% of my salary, where should I cut?", "spending"),
    ("what's my monthly average spend?", "spending"),
    ("how much did I spend on the Goa trip?", "spending"),
    ("any charges I don't recognise?", "spending"),
    ("find the ATM withdrawals in June", "spending"),
    ("how much interest did my savings account pay me?", "spending"),
    ("do I spend more on weekends?", "spending"),
    ("did I pay my credit card bill in full last month?", "spending"),
    ("what's my biggest single transaction this year?", "spending"),
    ("monthly rent vs income ratio from my account", "spending"),
    ("did I get any refunds last month?", "spending"),
    ("mera monthly kharcha kitna hai?", "spending"),
    ("kitna bacha is mahine?", "spending"),
    ("is my dining spend above 10% of my income?", "spending"),
    ("compare March and April spending", "spending"),
    ("how much have I invested through SIPs so far according to my bank statement?", "spending"),
    ("list recurring payments", "spending"),
    ("what categories am I spending on?", "spending"),
    ("what was my spend on petrol in the second half of the year?", "spending"),
    ("savings this year?", "spending"),
    # documents vs explain
    ("what is the current ratio in the balance sheet I uploaded?", "documents"),
    ("is the company in the attached report profitable?", "documents"),
    ("what does this invoice charge GST on?", "documents"),
    ("explain the numbers in my P&L", "documents"),
    ("from the annual report, what was the dividend declared?", "documents"),
    ("page 12 of the policy — what's excluded?", "documents"),
    ("summarise this document", "documents"),
    ("what's the debt in this balance sheet?", "documents"),
    ("does the loan agreement allow prepayment without penalty?", "documents"),
    ("what is the sum insured in the attached policy?", "documents"),
    ("what tax was deducted according to my Form 16?", "documents"),
    ("read the uploaded factsheet and tell me the expense ratio", "documents"),
    ("is my liquidity healthy?", "documents"),
    ("current ratio and what it means", "documents"),
    ("what should I watch for in this balance sheet?", "documents"),
    ("quick ratio from the file", "documents"),
    ("does the balance sheet look healthy?", "documents"),
    ("what's the revenue in the PDF?", "documents"),
    ("total liabilities?", "documents"),
    ("what does the uploaded GST return show as output tax?", "documents"),
    ("is this invoice overdue?", "documents"),
    ("what are the notes to accounts saying about contingent liabilities?", "documents"),
    ("compare FY24 and FY25 revenue in the report", "documents"),
    ("how much depreciation is charged in the uploaded P&L?", "documents"),
    ("what's the tenure in my loan sanction letter?", "documents"),
    ("which items in this invoice attract 18% GST?", "documents"),
    ("what's the equity to debt in this file?", "documents"),
    ("highlight the risks mentioned in the annual report", "documents"),
    ("what does the policy say about pre-existing diseases?", "documents"),
    ("rate of interest in the attached FD receipt", "documents"),
    # market vs advice vs explain
    ("TCS share price today", "market"),
    ("what is TCS?", "explain"),
    ("should I buy TCS?", "advice"),
    ("news about HDFC Bank", "market"),
    ("HDFC Bank price", "market"),
    ("Reliance ka share kitne ka hai", "market"),
    ("what's gold at today?", "market"),
    ("nifty?", "market"),
    ("sensex today", "market"),
    ("dollar rate", "market"),
    ("Infosys results", "market"),
    ("why is Zomato down 5%?", "market"),
    ("any news on the RBI rate decision?", "market"),
    ("what did the Fed do today?", "market"),
    ("Bitcoin price in INR", "market"),
    ("latest news on Adani", "market"),
    ("is the market open today?", "market"),
    ("Tata Motors stock", "market"),
    ("Apple stock price", "market"),
    ("Nvidia earnings news", "market"),
    ("crude oil price now", "market"),
    ("what's the NAV of Parag Parikh Flexi Cap?", "market"),
    ("how much did Nifty fall this week?", "market"),
    ("USD INR", "market"),
    ("Wipro buyback news", "market"),
    ("SBI Q2 results", "market"),
    ("what's trending on Dalal Street today?", "market"),
    ("IT stocks news", "market"),
    ("bank nifty live", "market"),
    ("silver rate today in Delhi", "market"),
    ("what's the price of Reliance and what's its P/E?", "market"),
    ("what is a P/E ratio?", "explain"),
    ("is Reliance's P/E of 25 high?", "explain"),
    ("what is the Nifty 50?", "explain"),
    ("how is the Sensex calculated?", "explain"),
    ("what is a stock?", "explain"),
    ("how do I start investing?", "explain"),
    ("what are the steps to open a demat account?", "explain"),
    ("how does an IPO work?", "explain"),
    ("why do stock prices move?", "explain"),
    ("what is market capitalisation?", "explain"),
    ("how are mutual funds taxed in India?", "explain"),
    ("what is the difference between NSE and BSE?", "explain"),
    ("what is a SIP?", "explain"),
    ("EMI on 10 lakh at 9% for 5 years", "explain"),
    ("EMI for 25 lakh home loan at 8.5% for 20 years", "explain"),
    ("I earn 12 LPA, which tax regime is better?", "explain"),
    ("how does 80C work?", "explain"),
    ("what is EBITDA?", "explain"),
    ("old vs new tax regime", "explain"),
    ("what is a balance sheet?", "explain"),
    ("how much will 5000 a month become in 10 years at 12%?", "explain"),
    ("is 750 a good credit score?", "explain"),
    ("what is CIBIL?", "explain"),
    ("GST on restaurant bills?", "explain"),
    ("how does input tax credit work for a small business?", "explain"),
    ("ITR-3 kiske liye hai?", "explain"),
    ("which ITR for salary plus capital gains?", "explain"),
    ("UPI limit per day?", "explain"),
    ("money debited but UPI failed, what now?", "explain"),
    ("EPF interest rate and how it's credited", "explain"),
    ("PPF maturity rules", "explain"),
    ("NPS tax benefit under 80CCD(1B)", "explain"),
    ("what is a term plan?", "explain"),
    ("how is LTCG on equity taxed now?", "explain"),
    ("what is indexation?", "explain"),
    ("tell me about sovereign gold bonds", "explain"),
    ("what's the 4% rule?", "explain"),
    ("how does a credit card interest-free period work?", "explain"),
    ("what is the repo rate and why does it matter to my home loan?", "explain"),
    ("difference between gross and net salary", "explain"),
    ("what is HRA?", "explain"),
    ("how does compound interest work? show an example", "explain"),
    ("explain SIP vs lumpsum", "explain"),
    ("what is a liquid fund and when to use it?", "explain"),
    ("what is an emergency fund and how big should it be?", "explain"),
    ("meaning of NAV", "explain"),
    ("how much tax on 18 lakh?", "explain"),
    ("what is TDS on FD?", "explain"),
    ("what is section 24 deduction for home loan interest?", "explain"),
    ("how does a step-up SIP work?", "explain"),
    ("what is a good debt-to-equity ratio?", "explain"),
    ("how do I read a P&L?", "explain"),
    ("should I buy Reliance?", "advice"),
    ("is HDFC Bank a good buy at this price?", "advice"),
    ("which mutual fund is best for a beginner?", "advice"),
    ("where do I invest 1 lakh?", "advice"),
    ("should I start a SIP now or wait?", "advice"),
    ("is it a good time to buy gold?", "advice"),
    ("which stocks to buy today?", "advice"),
    ("recommend 3 small caps", "advice"),
    ("is crypto a good investment for me?", "advice"),
    ("should I sell my Tata Motors shares?", "advice"),
    ("will Nifty go up next week?", "advice"),
    ("tell me a multibagger", "advice"),
    ("best fund for my daughter's education?", "advice"),
    ("should I invest in the LIC IPO?", "advice"),
    ("prepay home loan or invest in equity?", "advice"),
    ("is PPF or ELSS better for me?", "advice"),
    ("I have 10 lakh, FD or mutual fund?", "advice"),
    ("should I take a loan to buy a car now?", "advice"),
    ("which is the safest investment for my parents' money?", "advice"),
    ("should I buy Zomato after the fall?", "advice"),
    ("should I buy a house or keep renting?", "advice"),
    ("buy or sell Infosys?", "advice"),
    ("is it wise to put my bonus into Bitcoin?", "advice"),
    ("Reliance lu ya nahi?", "advice"),
    ("kaunsa mutual fund best hai mere liye?", "advice"),
    ("should I exit all my equity before the budget?", "advice"),
    ("should I increase my SIP to 20k?", "advice"),
    ("do you think Tesla is overpriced, should I short it?", "advice"),
    ("recommend a stock for my first investment", "advice"),
    ("should I keep my money in savings or invest?", "advice"),
    # out of scope
    ("write a python script to parse my bank statement csv", "out_of_scope"),
    ("write a Python script", "out_of_scope"),
    ("recipe for biryani", "out_of_scope"),
    ("who won the match?", "out_of_scope"),
    ("explain photosynthesis", "out_of_scope"),
    ("fix the TypeError in my pandas code", "out_of_scope"),
    ("what's the weather today?", "out_of_scope"),
    ("tell me a joke", "out_of_scope"),
    ("hi", "out_of_scope"),
    ("hello there", "out_of_scope"),
    ("thanks a lot!", "out_of_scope"),
    ("who is the CEO of Google?", "out_of_scope"),
    ("how do I learn guitar?", "out_of_scope"),
    ("write a regex for Indian phone numbers", "out_of_scope"),
    ("sql query to join two tables", "out_of_scope"),
    ("best laptop for coding?", "out_of_scope"),
    ("plan my Manali trip", "out_of_scope"),
    ("how many calories in a samosa?", "out_of_scope"),
    ("translate this to French", "out_of_scope"),
    ("write a leave application", "out_of_scope"),
    ("what is 17 times 23?", "out_of_scope"),
    ("how far is the moon?", "out_of_scope"),
    ("who painted the Mona Lisa?", "out_of_scope"),
    ("explain quantum computing", "out_of_scope"),
    ("how to center a div in CSS?", "out_of_scope"),
    ("ipl points table", "out_of_scope"),
    ("Virat Kohli's century today", "out_of_scope"),
    ("good morning!", "out_of_scope"),
    ("what can you do?", "out_of_scope"),
    ("are you ChatGPT?", "out_of_scope"),
    ("write a poem about money", "out_of_scope"),
    ("make a resume for a data analyst", "out_of_scope"),
    ("how do I fix my wifi?", "out_of_scope"),
    ("recommend a good Netflix series", "out_of_scope"),
    ("what's the plot of Inception?", "out_of_scope"),
    ("how do I meditate?", "out_of_scope"),
    ("tips to sleep better", "out_of_scope"),
    ("kya haal hai", "out_of_scope"),
    ("biryani kaise banate hain", "out_of_scope"),
    ("mujhe python sikhao", "out_of_scope"),
    ("draw me a cat", "out_of_scope"),
    ("what is the capital of Canada?", "out_of_scope"),
    ("chemistry: balance this equation", "out_of_scope"),
    ("my girlfriend is angry, what do I say?", "out_of_scope"),
    ("how to train a dog?", "out_of_scope"),
    ("explain the offside rule", "out_of_scope"),
    ("write a LinkedIn post about my promotion", "out_of_scope"),
    ("how to make cold coffee", "out_of_scope"),
    ("what's a good name for a startup?", "out_of_scope"),
    ("decode this base64 string", "out_of_scope"),
    ("build me a todo app in React", "out_of_scope"),
    ("how to apply for a passport?", "out_of_scope"),
    ("explain the rules of chess", "out_of_scope"),
    ("history of the Taj Mahal", "out_of_scope"),
    ("is it going to rain in Mumbai?", "out_of_scope"),
    ("convert 5 km to miles", "out_of_scope"),
    ("what rhymes with orange?", "out_of_scope"),
    ("write an essay on climate change", "out_of_scope"),
    ("how do vaccines work?", "out_of_scope"),
    ("help me with a Dockerfile", "out_of_scope"),
    ("bye", "out_of_scope"),
    ("ok thanks", "out_of_scope"),
    ("lol", "out_of_scope"),
    ("tell me more", "out_of_scope"),
    ("why?", "out_of_scope"),
]

_KEY_RE = re.compile(r"[^a-z0-9]+")


def _key(text: str) -> str:
    return _KEY_RE.sub(" ", text.lower()).strip()


def _fill(template: str, rng: random.Random) -> str:
    def repl(match: re.Match[str]) -> str:
        return rng.choice(SLOTS[match.group(1)])

    return re.sub(r"\{(\w+)\}", repl, template)


def _vary(text: str, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.18:
        text = rng.choice(PREFIXES) + text
    elif r < 0.30:
        text = text + rng.choice(SUFFIXES)
    if rng.random() < 0.25:
        text = text.lower()
    elif rng.random() < 0.10:
        text = text[0].upper() + text[1:]
    if rng.random() < 0.20:
        text = text.rstrip("?.! ")
    if rng.random() < 0.05:
        text = text.replace("?", "??")
    return " ".join(text.split())


def _templated(label: str, n: int, rng: random.Random, seen: set[str]) -> list[dict]:
    rows: list[dict] = []
    templates = TEMPLATES[label]
    per_template: Counter[str] = Counter()
    cap = max(6, (n // len(templates)) * 2 + 2)
    attempts = 0
    while len(rows) < n and attempts < n * 60:
        attempts += 1
        template = rng.choice(templates)
        if per_template[template] >= cap:
            continue
        text = _vary(_fill(template, rng), rng)
        key = _key(text)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        per_template[template] += 1
        rows.append({"text": text, "label": label, "template": template, "source": "template"})
    return rows


def build_dataset(seed: int = SEED, per_label: dict[str, int] | None = None) -> list[dict]:
    """Deterministic: templated examples per label + the hand-written HARD set (de-duplicated)."""
    per_label = per_label or PER_LABEL
    rng = random.Random(seed)
    seen: set[str] = set()
    rows: list[dict] = []
    for text, label in HARD:  # hand-written first, so a template duplicate never shadows a hand label
        assert label in LABELS, (text, label)
        key = _key(text)
        if key in seen:
            raise ValueError(f"duplicate hand-written example: {text!r}")
        seen.add(key)
        rows.append({"text": text, "label": label, "template": None, "source": "hand"})
    for label in LABELS:
        rows.extend(_templated(label, per_label[label], rng, seen))
    rng.shuffle(rows)
    return rows


def save(rows: list[dict], path: Path = DATA_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load(path: Path = DATA_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing — run `python -m ml.router_data` first")
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    rows = build_dataset()
    save(rows)
    counts = Counter(r["label"] for r in rows)
    hand = sum(r["source"] == "hand" for r in rows)
    print(f"{len(rows)} examples ({hand} hand-written) -> {DATA_PATH}")
    for label in LABELS:
        print(f"  {label:13s} {counts[label]:4d}")


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
