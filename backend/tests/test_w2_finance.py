"""Finance analytics: demo bank statement, balance sheet ratios, messy files, ownership, unit helpers."""
from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import settings
from app.db.base import session_scope
from app.db.models import Document
from app.features.finance.categorize import categorize
from app.features.finance.money import money
from app.features.finance.parsing import parse_amount, parse_dates
from app.features.finance.report import analyze_file, summary_markdown

REPO = Path(__file__).resolve().parents[2]
BANK = REPO / "samples" / "bank_statement_demo.csv"
BALANCE = REPO / "samples" / "balance_sheet_2025.csv"
MIME = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf"}


def add_doc(user_id: str, source: Path | None = None, *, text: str | None = None, filename: str | None = None,
            status: str = "ready") -> str:
    """A Document row whose stored file is a copy of `source` (or `text`), as an upload would leave it."""
    doc_id = str(uuid.uuid4())
    filename = filename or (source.name if source else "data.csv")
    dest = settings.upload_dir / f"{doc_id}{Path(filename).suffix}"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if source is not None:
        shutil.copyfile(source, dest)
    else:
        dest.write_text(text or "", encoding="utf-8")
    with session_scope() as db:
        db.add(Document(id=doc_id, user_id=user_id, filename=filename, mime_type=MIME.get(dest.suffix, "text/csv"),
                        size_bytes=dest.stat().st_size, sha256="0" * 64, storage_path=str(dest), status=status))
    return doc_id


def analyze(client, who, doc_id: str):
    return client.post("/api/finance/analyze", json={"docId": doc_id}, headers=who["headers"])


def test_demo_bank_statement(client, user):
    r = analyze(client, user, add_doc(user["user"]["id"], BANK))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert set(rep) == {"docId", "filename", "kind", "currency", "period", "totals", "byMonth", "byCategory",
                        "topTransactions", "balanceSheet", "profitLoss", "amountUnit", "insights", "warnings"}
    assert rep["kind"] == "bank_statement" and rep["currency"] == "INR" and rep["balanceSheet"] is None
    assert rep["profitLoss"] is None and rep["amountUnit"] is None
    assert rep["period"] == {"start": "2026-04-01", "end": "2026-09-30"}
    assert [m["month"] for m in rep["byMonth"]] == [f"2026-{m:02d}" for m in range(4, 10)]

    df = pd.read_csv(BANK)
    inflow, outflow = df["Deposit Amt."].fillna(0).sum(), df["Withdrawal Amt."].fillna(0).sum()
    totals = rep["totals"]
    assert totals["inflow"] == pytest.approx(inflow, abs=0.05)
    assert totals["outflow"] == pytest.approx(outflow, abs=0.05)
    assert totals["net"] == pytest.approx(inflow - outflow, abs=0.05)
    assert sum(m["net"] for m in rep["byMonth"]) == pytest.approx(totals["net"], abs=0.1)
    assert sum(c["amount"] for c in rep["byCategory"]) == pytest.approx(totals["outflow"], abs=0.1)
    assert sum(c["count"] for c in rep["byCategory"]) == int(df["Withdrawal Amt."].notna().sum())

    cats = {c["category"]: c for c in rep["byCategory"]}
    assert rep["byCategory"][0]["category"] == "Rent" and cats["Rent"]["amount"] == 132_000
    for expected in ("Groceries", "Dining", "Travel", "Utilities", "Subscriptions", "Investments", "Fuel",
                     "Shopping", "Cash withdrawal", "Fees & charges"):
        assert expected in cats, expected
    aug = next(m for m in rep["byMonth"] if m["month"] == "2026-08")
    assert aug["net"] < 0
    assert any("Aug 2026" in i for i in rep["insights"]) and any("Rent" in i for i in rep["insights"])
    top = rep["topTransactions"]
    assert len(top) == 10 and abs(top[0]["amount"]) >= abs(top[-1]["amount"])
    assert sum(1 for t in top if t["category"] == "Salary") <= 3
    assert any(t["amount"] < 0 for t in top) and all(len(t["date"]) == 10 for t in top)


def test_balance_sheet_ratios(client, user):
    r = analyze(client, user, add_doc(user["user"]["id"], BALANCE))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["kind"] == "balance_sheet" and rep["currency"] == "USD" and rep["totals"] is None
    bs = rep["balanceSheet"]
    assert bs["totalAssets"] == 4_610_000 and bs["totalLiabilities"] == 2_450_000 and bs["equity"] == 2_160_000
    assert bs["currentRatio"] == pytest.approx(1_960_000 / 650_000, abs=0.001)
    assert bs["quickRatio"] == pytest.approx((1_960_000 - 320_000) / 650_000, abs=0.001)
    assert bs["debtToEquity"] == pytest.approx(2_450_000 / 2_160_000, abs=0.001)
    assert [c["category"] for c in rep["byCategory"]] == ["Current Assets", "Non-Current Assets",
                                                          "Current Liabilities", "Non-Current Liabilities", "Equity"]
    assert any("Current ratio 3.02" in i for i in rep["insights"]) and rep["warnings"] == []


HDFC_MESSY = """HDFC BANK Ltd.,,,,,,
Account Holder : MR DEMO USER,,,,,,
Statement From : 01/03/2026 To : 31/03/2026,,,,,,
,,,,,,
Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
********,********,********,********,********,********,********
01/03/26,NEFT CR-ACME LTD-SALARY MAR,000123,01/03/26,,"1,00,000.00","1,50,000.00"
02/03/26,UPI-SWIGGY-swiggy@icici-1234-UPI,000124,02/03/26,450.50,,"1,49,549.50"
13/03/26,ATW-4160XXXX-ATM CASH,000125,13/03/26,"5,000.00",,"1,44,549.50"
25/03/26,ACH D- HDFC MF SIP,000126,25/03/26,"10,000.00",,"1,34,549.50"
not a row,,,,,,
,,,,,,
STATEMENT SUMMARY :-,,,,,,
Opening Balance,Dr Count,Cr Count,Debits,Credits,Closing Bal,
"50,000.00",3,1,"15,450.50","1,00,000.00","1,34,549.50",
"""

SIGNED_US = """Transaction Date,Description,Amount,Balance
03/15/2026,PAYROLL DEPOSIT ACME,"$4,200.00","$5,200.00"
03/16/2026,STARBUCKS #1234,($6.45),"$5,193.55"
03/20/2026,AMAZON.COM*AB12,-$120.10,"$5,073.45"
03/28/2026,NETFLIX.COM,-15.99,"$5,057.46"
"""

CRDR_SUFFIX = """Txn Date;Particulars;Amount;Balance
05-Apr-2026;UPI/ZOMATO/zomato@hdfcbank;350.00 Dr;9650.00 Cr
06-Apr-2026;IMPS/RAHUL SHARMA/loan return;2,000.00 Cr;11650.00 Cr
07-Apr-2026;BESCOM ELECTRICITY;1,200.00 Dr;10450.00 Cr
"""


def test_messy_bank_exports(tmp_path):
    for name, text in (("hdfc.csv", HDFC_MESSY), ("us.csv", SIGNED_US), ("crdr.csv", CRDR_SUFFIX)):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        rep = analyze_file(path, name, "doc")
        assert rep["kind"] == "bank_statement", (name, rep["warnings"])
        if name == "hdfc.csv":
            assert rep["totals"] == {"inflow": 100_000.0, "outflow": 15_450.5, "net": 84_549.5}
            assert rep["currency"] == "INR" and rep["period"] == {"start": "2026-03-01", "end": "2026-03-25"}
            assert any("above the table header" in w for w in rep["warnings"])
            assert any("Skipped" in w and "without a valid date" in w for w in rep["warnings"])
            assert {c["category"] for c in rep["byCategory"]} == {"Dining", "Cash withdrawal", "Investments"}
        elif name == "us.csv":
            assert rep["currency"] == "USD" and rep["period"]["start"] == "2026-03-15"
            assert rep["totals"]["inflow"] == 4200 and rep["totals"]["outflow"] == pytest.approx(142.54)
            assert {t["category"] for t in rep["topTransactions"]} >= {"Salary", "Dining", "Shopping", "Subscriptions"}
        else:
            assert rep["totals"] == {"inflow": 2000.0, "outflow": 1550.0, "net": 450.0}
            assert rep["period"] == {"start": "2026-04-05", "end": "2026-04-07"}


def test_xlsx_with_preamble_and_unsigned_amounts(tmp_path):
    path = tmp_path / "statement.xlsx"
    rows = [["Bank of Demo"], [None], ["Date", "Details", "Amount", "Balance"],
            [pd.Timestamp("2026-02-01"), "Salary credit ACME", 3000, 4000],
            [pd.Timestamp("2026-02-03"), "Rent February", 1200, 2800],
            [pd.Timestamp("2026-02-05"), "Grocery store", 150.25, 2649.75]]
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Feb", header=False, index=False)
        pd.DataFrame([["notes"]]).to_excel(writer, sheet_name="Notes", header=False, index=False)
    rep = analyze_file(path, path.name, "doc")
    assert rep["kind"] == "bank_statement"
    # signs come from the running balance
    assert rep["totals"] == {"inflow": 3000.0, "outflow": 1350.25, "net": 1649.75}
    assert {c["category"] for c in rep["byCategory"]} == {"Rent", "Groceries"}


@pytest.mark.parametrize("content", ["", "\n\n", "just,one,line\n", "a\n1\n2\n", "\x00\x01\x02 binary junk",
                                     "Date,Amount\nnot-a-date,abc\n,,\n", "Name,Score\nA,1\nB,x\nC,3\n"])
def test_garbage_never_raises(tmp_path, content):
    path = tmp_path / "junk.csv"
    path.write_text(content, encoding="utf-8")
    rep = analyze_file(path, "junk.csv", "doc")
    assert rep["kind"] in ("table", "bank_statement") and isinstance(rep["warnings"], list)
    assert summary_markdown(rep)


def test_corrupt_xlsx_is_a_warning_not_a_500(client, user):
    doc = add_doc(user["user"]["id"], text="definitely not a zip", filename="broken.xlsx")
    r = analyze(client, user, doc)
    assert r.status_code == 200 and r.json()["kind"] == "table" and r.json()["warnings"]


def test_generic_table(client, user):
    text = "Region,Product,Revenue,Units\nNorth,A,1200,10\nSouth,A,800,8\nNorth,B,300,3\nWest,C,950.5,7\n"
    rep = analyze(client, user, add_doc(user["user"]["id"], text=text, filename="sales.csv")).json()
    assert rep["kind"] == "table" and rep["byCategory"][0] == {"category": "North", "amount": 1500.0, "count": 2}
    assert any("Revenue: total 3,250.50" in i for i in rep["insights"])


def test_errors_and_ownership(client, user, other_user):
    doc = add_doc(user["user"]["id"], BANK)
    assert analyze(client, other_user, doc).status_code == 404
    assert analyze(client, user, str(uuid.uuid4())).status_code == 404
    pdf = add_doc(user["user"]["id"], text="%PDF-1.4", filename="report.pdf")
    r = analyze(client, user, pdf)
    assert r.status_code == 415 and "CSV or Excel" in r.json()["detail"]
    with session_scope() as db:
        Path(db.get(Document, doc).storage_path).unlink()
    assert analyze(client, user, doc).status_code == 404
    assert client.post("/api/finance/analyze", json={}, headers=user["headers"]).status_code == 422
    assert client.post("/api/finance/analyze", json={"docId": doc}).status_code == 401


def test_llm_insights_used_when_a_real_model_answers(client, user, monkeypatch):
    from app.features.finance import insights
    from app.llm import registry

    real_resolve = registry.resolve_model

    def fake_resolve(model_id):
        resolved = real_resolve("mock:sphura-mock")
        resolved.provider = "groq"
        return resolved

    async def fake_complete(model, messages, temperature=0.2, json_mode=False, timeout=30.0):
        assert "Rent" in messages[1]["content"]
        return "Here you go:\n- Rent is the largest cost at ₹1,32,000 over six months.\n- August was the only month " \
               "with a negative net cash flow.\n"

    monkeypatch.setattr(insights.registry, "resolve_model", fake_resolve)
    monkeypatch.setattr(insights.registry, "complete", fake_complete)
    rep = analyze(client, user, add_doc(user["user"]["id"], BANK)).json()
    assert rep["insights"] == ["Rent is the largest cost at ₹1,32,000 over six months.",
                               "August was the only month with a negative net cash flow."]


# ── unit helpers ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("1,23,456.50", (123456.5, 0)), ("₹ 2,000", (2000.0, 0)), ("Rs. 450.00", (450.0, 0)), ("(75.10)", (-75.1, 0)),
    ("-$12.00", (-12.0, 0)), ("120.00 Dr", (120.0, -1)), ("99.5 CR", (99.5, 1)), ("1.234,56", (1234.56, 0)),
    ("500-", (-500.0, 0)), ("", (None, 0)), ("abc", (None, 0)), ("--", (None, 0)), (42, (42.0, 0)),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_dates_dayfirst_and_sanity():
    dates, note = parse_dates(["01/04/26", "15/04/26", "02/05/26"], today=date(2026, 10, 22))
    assert dates == [date(2026, 4, 1), date(2026, 4, 15), date(2026, 5, 2)] and "day-first" in note
    us, _ = parse_dates(["03/15/2026", "03/16/2026"], today=date(2026, 10, 22))
    assert us == [date(2026, 3, 15), date(2026, 3, 16)]
    iso, _ = parse_dates(["2026-01-02", "2026-01-03"], today=date(2026, 10, 22))
    assert iso == [date(2026, 1, 2), date(2026, 1, 3)]
    weird, _ = parse_dates(["01/01/1850", "hello", 45000, None], today=date(2026, 10, 22))
    assert weird == [None, None, date(2023, 3, 15), None]


@pytest.mark.parametrize("text,amount,expected", [
    ("NEFT CR-ACME LTD-SALARY APR", 85000, "Salary"), ("IMPS-RAMESH-HOUSE RENT", -22000, "Rent"),
    ("UPI-SWIGGY-swiggy@icici", -320, "Dining"), ("UPI-SWIGGY INSTAMART-x@ybl", -800, "Groceries"),
    ("UPI-PRIYA SHARMA-priya@okaxis", -500, "Transfers"), ("UPI-PRIYA SHARMA-priya@okaxis", 500, "Transfers"),
    ("POS NETFLIX.COM", -649, "Subscriptions"), ("BESCOM ELECTRICITY", -1200, "Utilities"),
    ("ATW-4160XX-ATM CASH", -2000, "Cash withdrawal"), ("SMS CHARGES INCL GST", -17.7, "Fees & charges"),
    ("ACH D- ZERODHA MF SIP", -10000, "Investments"), ("INDIAN OIL PETROL", -2000, "Fuel"),
    ("UBER INDIA", -250, "Travel"), ("PAYTM FASTAG RECHARGE", -500, "Travel"), ("AMAZON PAY INDIA", -999, "Shopping"),
    ("REFUND-AMAZON", 999, "Refunds"), ("CREDIT INTEREST CAPITALISED", 1200, "Interest"),
    ("HOME LOAN EMI", -25000, "Loans & EMI"), ("MYSTERY MERCHANT", -10, "Other"),
])
def test_categorize(text, amount, expected):
    assert categorize(text, amount) == expected


def test_money_format():
    assert money(1234567.8, "INR") == "₹12,34,568" and money(-450.5, "INR") == "-₹450.50"
    assert money(4610000, "USD") == "$4,610,000" and money(12.5, None) == "12.50" and money(None, "USD") == "—"


# ── review regressions ───────────────────────────────────────────────────────
def test_money_rounds_before_formatting():
    assert money(999.999, "INR") == "₹1,000.00" and money(-0.001, "INR") == "₹0.00"
    assert money(1999.6, "INR") == "₹2,000" and money(0.5, "USD") == "$0.50"


@pytest.mark.parametrize("raw,expected", [
    ("12,50", (12.5, 0)), ("-950,00", (-950.0, 0)), ("2,500", (2500.0, 0)), ("9" * 400, (None, 0)),
    (float("inf"), (None, 0)), (1e300, (None, 0)),
])
def test_parse_amount_decimal_comma_and_overflow(raw, expected):
    assert parse_amount(raw) == expected


def test_fake_excel_exports_are_read(tmp_path):
    """Bank portals often serve HTML tables or UTF-16 TSV with an .xls extension."""
    html = ("<html><body><table><tr><td>Account: 1234</td></tr></table><table><tr><th>Date</th><th>Narration</th>"
            "<th>Withdrawal Amt.</th><th>Deposit Amt.</th><th>Closing Balance</th></tr>"
            "<tr><td>01/04/26</td><td>NEFT CR-ACME-SALARY</td><td></td><td>85,000.00</td><td>1,00,000.00</td></tr>"
            "<tr><td>03/04/26</td><td>UPI-SWIGGY</td><td>250.00</td><td></td><td>99,750.00</td></tr></table>"
            "</body></html>")
    (tmp_path / "stmt.xls").write_text(html, encoding="utf-8")
    rep = analyze_file(tmp_path / "stmt.xls", "stmt.xls", "doc")
    assert rep["kind"] == "bank_statement" and rep["currency"] == "INR"
    assert rep["totals"] == {"inflow": 85000.0, "outflow": 250.0, "net": 84750.0}
    (tmp_path / "tsv.xls").write_text("Date\tDescription\tDebit\tCredit\n2026-04-01\tSalary\t\t50000\n"
                                      "2026-04-03\tZepto\t900\t\n", encoding="utf-16")
    rep = analyze_file(tmp_path / "tsv.xls", "tsv.xls", "doc")
    assert rep["totals"] == {"inflow": 50000.0, "outflow": 900.0, "net": 49100.0}
    (tmp_path / "broken.xlsx").write_bytes(b"PK\x03\x04" + b"garbage" * 20)
    rep = analyze_file(tmp_path / "broken.xlsx", "broken.xlsx", "doc")
    assert rep["totals"] is None and "could not be read" in rep["warnings"][0]
