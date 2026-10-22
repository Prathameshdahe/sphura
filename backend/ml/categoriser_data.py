"""Labelled dataset for Sphura's transaction categoriser (14-way narration classifier).

Classes (label id → display name used by the finance dashboard):
  salary         Salary          payroll / stipend credits
  rent           Rent            house rent, PG, society maintenance
  groceries      Groceries       supermarkets, quick-commerce, kirana
  dining         Dining          food delivery, restaurants, cafés
  travel         Travel          cabs, metro, trains, flights, hotels, tolls
  fuel           Fuel            petrol pumps, CNG, EV charging
  utilities      Utilities       electricity, gas, water, mobile, broadband, DTH
  shopping       Shopping        e-commerce, fashion, electronics, retail stores
  subscriptions  Subscriptions   streaming, software, gym, memberships
  emi_loan       Loans & EMI     EMIs, loan repayments, credit-card bill payments
  investments    Investments     SIP/MF, FD/RD, stocks, NPS/PPF, insurance premiums (and redemptions)
  transfers      Transfers       P2P UPI/IMPS/NEFT to people, self transfers, wallet loads
  fees           Fees & charges  bank charges, GST on charges, penalties, AMC
  cash           Cash withdrawal ATM / branch cash

Two credit-only categories (Refunds, Interest) are not model classes: `app.features.finance.categorize`
keeps them as deterministic rules because the dashboard's sign inference depends on them and they are
keyword-trivial ("REFUND", "CASHBACK", "INT.PD"). "Other" is the fallback when nothing matches.

The dataset has three parts:
  1. Generated narrations — Indian bank-statement formats (HDFC/SBI/ICICI/Axis/Kotak styles of UPI, POS,
     NEFT/IMPS/RTGS, ACH/NACH, ATM, BillDesk/BBPS, EMI/SI) × merchant/person lists × noise (casing, masked
     card digits, reference numbers, cities, Hinglish notes, dropped separators). Fixed seed, de-duplicated.
  2. samples/bank_statement_demo.csv — every narration of the demo statement, labelled by the author.
  3. TEST — 400 narrations written and labelled by hand by the author (`categoriser_test_set.py`); they use
     formats and merchants the generator does not, so the test measures generalisation, not memorisation.

Each row: {"text", "direction": "credit"|"debit", "amount", "label", "template", "source"}.
The model input is `model_text(row)` = "<direction> | <narration>" so the sign is a feature.

Run from backend/:  .venv/Scripts/python -m ml.categoriser_data   → ml/data/categoriser_{train,test}.jsonl
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

SEED = 2026
PER_CLASS = 480  # generated rows per class (demo-statement rows come on top)
DATA_DIR = Path(__file__).resolve().parent / "data"
TRAIN_PATH = DATA_DIR / "categoriser_train.jsonl"
TEST_PATH = DATA_DIR / "categoriser_test.jsonl"
SAMPLE_PATH = Path(__file__).resolve().parents[2] / "samples" / "bank_statement_demo.csv"

LABELS = ["salary", "rent", "groceries", "dining", "travel", "fuel", "utilities", "shopping", "subscriptions",
          "emi_loan", "investments", "transfers", "fees", "cash"]
DISPLAY = {"salary": "Salary", "rent": "Rent", "groceries": "Groceries", "dining": "Dining", "travel": "Travel",
           "fuel": "Fuel", "utilities": "Utilities", "shopping": "Shopping", "subscriptions": "Subscriptions",
           "emi_loan": "Loans & EMI", "investments": "Investments", "transfers": "Transfers",
           "fees": "Fees & charges", "cash": "Cash withdrawal"}
assert list(DISPLAY) == LABELS

# ── vocabularies ─────────────────────────────────────────────────────────────
MERCHANTS: dict[str, list[str]] = {
    "groceries": ["ZEPTO", "BLINKIT", "BIGBASKET", "SWIGGY INSTAMART", "INSTAMART", "DMART", "D MART READY",
                  "JIOMART", "RELIANCE FRESH", "RELIANCE SMART BAZAAR", "MORE SUPERMARKET", "NATURES BASKET",
                  "SPENCERS RETAIL", "STAR BAZAAR", "RATNADEEP SUPER MARKET", "VISHAL MEGA MART", "COUNTRY DELIGHT",
                  "MILKBASKET", "LICIOUS", "FRESHTOHOME", "AMUL PARLOUR", "MOTHER DAIRY", "SAFAL", "KIRANA STORE",
                  "SRI BALAJI PROVISION STORE", "NEW ANAND GENERAL STORE", "FRESHPIK", "SUPERMARKET", "OTIPY",
                  "DAILY NEEDS MART", "METRO CASH AND CARRY", "LULU HYPERMARKET", "HYPERCITY", "NILGIRIS"],
    "dining": ["SWIGGY", "ZOMATO", "DOMINOS PIZZA", "DOMINO'S", "MCDONALDS", "KFC", "BURGER KING", "SUBWAY",
               "STARBUCKS", "CAFE COFFEE DAY", "CCD", "CHAAYOS", "THIRD WAVE COFFEE", "BLUE TOKAI", "HALDIRAMS",
               "BARBEQUE NATION", "PIZZA HUT", "WOW MOMO", "BIRYANI BY KILO", "BEHROUZ BIRYANI", "FAASOS",
               "EATSURE", "SARAVANA BHAVAN", "UDUPI RESTAURANT", "PUNJABI DHABA", "THE BISTRO", "SOCIAL",
               "TRUFFLES", "MEGHANA FOODS", "ANAND SWEETS", "A2B", "ROLLS MANIA", "DUNKIN", "BOX8", "TACO BELL",
               "CHAI POINT", "THEOBROMA", "NATURALS ICE CREAM", "BASKIN ROBBINS", "CAFE", "RESTAURANT",
               "BIKANERVALA", "WENDYS", "BURGER SINGH", "HOTEL EMPIRE", "RAMESHWARAM CAFE"],
    "travel": ["UBER INDIA", "UBER", "OLA", "OLACABS", "RAPIDO", "IRCTC", "INDIGO", "AIR INDIA", "VISTARA",
               "SPICEJET", "AKASA AIR", "MAKEMYTRIP", "MMT", "GOIBIBO", "CLEARTRIP", "YATRA", "REDBUS", "ABHIBUS",
               "BMRCL METRO", "DMRC METRO", "MUMBAI METRO ONE", "NAMMA METRO", "FASTAG RECHARGE", "NHAI TOLL",
               "PAYTM FASTAG", "AIRBNB", "OYO ROOMS", "TREEBO", "FABHOTELS", "BOOKING.COM", "KSRTC", "MSRTC",
               "BLUSMART", "MERU CABS", "NAMMA YATRI", "YULU", "BOUNCE", "ZOOMCAR", "REVV", "TAJ HOTELS",
               "LEMON TREE", "ITC HOTELS", "ROYAL BROTHERS", "INDIGO 6E", "RAILYATRI", "CONFIRMTKT", "IXIGO",
               "VOGO", "APSRTC", "TSRTC", "BANGALORE AIRPORT PARKING"],
    "fuel": ["INDIAN OIL", "IOCL", "INDIANOIL PETROL PUMP", "BHARAT PETROLEUM", "BPCL", "HPCL", "HP PETROL PUMP",
             "HINDUSTAN PETROLEUM", "SHELL INDIA", "NAYARA ENERGY", "JIO BP", "RELIANCE PETROL PUMP",
             "ESSAR PETROL", "SRI SAI FUELS", "SHREE KRISHNA PETROLEUM", "HIGHWAY FUEL STATION", "FILLING STATION",
             "ADANI CNG", "MAHANAGAR GAS CNG", "INDRAPRASTHA GAS CNG STATION", "TATA POWER EV CHARGING",
             "ATHER GRID", "STATIQ EV CHARGING", "CHARGEZONE", "PETROL PUMP", "COCO PETROL BUNK",
             "BHARAT PETROLEUM COCO", "IOCL COCO OUTLET", "ESSAR FUEL", "NAYARA PETROL"],
    "utilities": ["BESCOM", "MSEDCL", "TATA POWER", "ADANI ELECTRICITY", "BSES RAJDHANI", "BSES YAMUNA",
                  "TORRENT POWER", "TNEB", "KSEB", "APSPDCL", "TSSPDCL", "UPPCL", "WBSEDCL", "CESC", "PSPCL",
                  "DHBVN", "MAHANAGAR GAS", "INDRAPRASTHA GAS", "ADANI GAS", "INDANE GAS", "HP GAS", "BHARAT GAS",
                  "BWSSB WATER", "DELHI JAL BOARD", "AIRTEL POSTPAID", "AIRTEL PREPAID", "AIRTEL BROADBAND",
                  "AIRTEL XSTREAM FIBER", "JIO PREPAID", "JIO POSTPAID", "JIOFIBER", "VODAFONE IDEA", "VI POSTPAID",
                  "BSNL", "ACT FIBERNET", "HATHWAY BROADBAND", "TATA PLAY", "DISH TV", "D2H", "SUN DIRECT",
                  "EXCITEL BROADBAND", "YOU BROADBAND", "TIKONA", "PIPED GAS BILL", "WATER BILL", "ELECTRICITY BILL",
                  "MOBILE RECHARGE", "DTH RECHARGE", "GAS CYLINDER BOOKING"],
    "shopping": ["AMAZON", "AMAZON PAY INDIA", "AMZN", "FLIPKART", "FLIPKART INTERNET", "MYNTRA", "AJIO", "NYKAA",
                 "MEESHO", "TATA CLIQ", "CROMA", "RELIANCE DIGITAL", "VIJAY SALES", "DECATHLON", "IKEA", "LIFESTYLE",
                 "SHOPPERS STOP", "WESTSIDE", "PANTALOONS", "MAX FASHION", "ZARA", "H AND M", "UNIQLO", "LENSKART",
                 "PEPPERFRY", "URBAN LADDER", "APPLE STORE", "SAMSUNG SMART CAFE", "MI HOME", "BOAT LIFESTYLE",
                 "FIRSTCRY", "HAMLEYS", "CROSSWORD", "SAPNA BOOK HOUSE", "TITAN WORLD", "TANISHQ", "KALYAN JEWELLERS",
                 "BATA", "NIKE STORE", "ADIDAS", "PUMA", "SNAPDEAL", "SHOPSY", "BEWAKOOF", "THE SOULED STORE",
                 "FABINDIA", "PHOENIX MALL", "LULU MALL", "DLF MALL", "SNITCH", "BOMBAY SHAVING COMPANY",
                 "MAMAEARTH", "PURPLLE", "SUGAR COSMETICS", "BIBA", "W FOR WOMAN", "MARKS AND SPENCER",
                 "RELIANCE TRENDS", "TRENDS", "ZUDIO", "V MART", "BIG BAZAAR", "AMAZON SELLER SERVICES"],
    "subscriptions": ["NETFLIX", "NETFLIX.COM", "SPOTIFY", "SPOTIFY INDIA", "AMAZON PRIME", "PRIME VIDEO",
                      "HOTSTAR", "DISNEY PLUS HOTSTAR", "JIOHOTSTAR", "YOUTUBE PREMIUM", "GOOGLE ONE", "GOOGLE STORAGE",
                      "APPLE.COM/BILL", "ICLOUD", "APPLE MUSIC", "SONYLIV", "ZEE5", "JIOCINEMA", "AUDIBLE",
                      "KINDLE UNLIMITED", "OPENAI CHATGPT SUBSCR", "CHATGPT", "CLAUDE.AI", "ANTHROPIC",
                      "MICROSOFT 365", "MICROSOFT", "ADOBE CREATIVE CLOUD", "ADOBE", "NOTION LABS", "GITHUB",
                      "CANVA", "LINKEDIN PREMIUM", "CULT.FIT", "CULTFIT", "GOLDS GYM", "ANYTIME FITNESS",
                      "HEALTHIFYME", "DUOLINGO", "COURSERA", "UDEMY", "UNACADEMY", "GAANA PLUS", "WYNK", "ALT BALAJI",
                      "TIMES PRIME", "ZOMATO GOLD", "SWIGGY ONE", "MUBI", "NYTIMES", "THE HINDU EPAPER",
                      "ECONOMIC TIMES PRIME", "DROPBOX", "ZOOM.US", "GOOGLE WORKSPACE", "PLAYSTATION PLUS",
                      "XBOX GAME PASS", "STEAM GAMES", "SETAPP", "GRAMMARLY", "FIGMA", "NORD VPN", "EXPRESSVPN"],
    "emi_loan": ["BAJAJ FINANCE", "BAJAJ FINSERV", "HDFC BANK HOME LOAN", "SBI HOME LOAN", "ICICI HOME FINANCE",
                 "LIC HOUSING FINANCE", "PNB HOUSING", "TATA CAPITAL", "HDB FINANCIAL", "IDFC FIRST BANK LOAN",
                 "AXIS BANK PERSONAL LOAN", "KOTAK CAR LOAN", "MAHINDRA FINANCE", "CHOLAMANDALAM", "SHRIRAM FINANCE",
                 "MUTHOOT FINANCE", "MANAPPURAM GOLD LOAN", "HERO FINCORP", "TVS CREDIT", "FULLERTON INDIA",
                 "MONEYVIEW", "KREDITBEE", "NAVI LOAN", "EARLYSALARY", "FIBE", "LAZYPAY", "SIMPL", "ZESTMONEY",
                 "CRED CLUB", "CRED", "HDFC CREDIT CARD PAYMENT", "SBI CARD PAYMENT", "ICICI CREDIT CARD BILL",
                 "AXIS CC PAYMENT", "AMEX CARD PAYMENT", "ONECARD", "SLICE", "HOME CREDIT", "POONAWALLA FINCORP",
                 "L AND T FINANCE", "ADITYA BIRLA FINANCE", "INDIABULLS HOUSING", "CANFIN HOMES",
                 "HDFC EDUCATION LOAN", "AVANSE EDUCATION LOAN", "SBI CAR LOAN"],
    "investments": ["ZERODHA BROKING", "ZERODHA", "GROWW", "UPSTOX", "KUVERA", "COIN BY ZERODHA", "PAYTM MONEY",
                    "INDMONEY", "SMALLCASE", "ANGEL ONE", "5PAISA", "ICICI DIRECT", "HDFC SECURITIES",
                    "KOTAK SECURITIES", "MOTILAL OSWAL", "SHAREKHAN", "DHAN", "ET MONEY", "SCRIPBOX", "NIPPON INDIA MF",
                    "SBI MUTUAL FUND", "HDFC MUTUAL FUND", "ICICI PRU MF", "AXIS MUTUAL FUND", "MIRAE ASSET MF",
                    "PARAG PARIKH MF", "UTI MF", "KOTAK MAHINDRA MF", "QUANT MUTUAL FUND", "MOTILAL OSWAL MF",
                    "BSE STAR MF", "NSE NMF", "NPS TRUST", "CRA NSDL NPS", "KFINTECH", "CAMS", "LIC OF INDIA",
                    "LIC PREMIUM", "HDFC LIFE", "ICICI PRU LIFE", "SBI LIFE", "MAX LIFE", "TATA AIA", "BAJAJ ALLIANZ",
                    "STAR HEALTH", "NIVA BUPA", "HDFC ERGO", "ICICI LOMBARD", "POLICYBAZAAR", "DITTO INSURANCE",
                    "FIXED DEPOSIT", "RECURRING DEPOSIT", "PPF ACCOUNT", "SUKANYA SAMRIDDHI", "SOVEREIGN GOLD BOND",
                    "RBI RETAIL DIRECT", "JAR APP", "GULLAK", "STABLE MONEY", "WINT WEALTH", "GRIP INVEST",
                    "INDIAN CLEARING CORP", "NSDL DEMAT", "CDSL"],
    "fees": ["SMS CHARGES", "SMS ALERT CHARGES INCL GST", "DEBIT CARD ANNUAL FEE", "DC ANNUAL CHARGES", "AMC CHARGES",
             "ACCOUNT MAINTENANCE CHARGES", "MIN BAL CHARGES", "NON MAINTENANCE CHARGES", "MAB CHARGES",
             "IMPS CHARGES", "NEFT CHARGES", "RTGS CHARGES", "ATM DECLINE CHARGES", "ATM USAGE CHARGES",
             "CASH WITHDRAWAL CHARGES", "CHEQUE BOOK CHARGES", "CHEQUE RETURN CHARGES", "ECS RETURN CHARGES",
             "ACH RETURN CHARGES", "LATE PAYMENT FEE", "LATE PAYMENT CHARGES", "FINANCE CHARGES", "OVERLIMIT FEE",
             "GST ON CHARGES", "GST DEBIT", "SERVICE CHARGES", "SERVICE TAX", "CONSOLIDATED CHARGES",
             "FOREX MARKUP FEE", "INTL TXN FEE", "CARD REPLACEMENT FEE", "STATEMENT CHARGES", "LOCKER RENT",
             "DEMAT AMC", "FOLIO MAINTENANCE", "PROCESSING FEE", "BOUNCE CHARGES", "PENAL INTEREST", "PENALTY",
             "TDS ON INTEREST", "TDS", "DUPLICATE STATEMENT CHARGES", "STOP PAYMENT CHARGES", "SI FAILURE CHARGES",
             "INTEREST DEBIT", "CASH DEPOSIT CHARGES", "BRANCH TXN CHARGES", "DD CHARGES", "SIGNATURE VERIFICATION CHG"],
    "cash": [],
    "rent": [],
    "salary": [],
    "transfers": [],
}
COMPANIES = ["ACME ANALYTICS PVT LTD", "INFOSYS LTD", "TATA CONSULTANCY SERVICES", "WIPRO LTD", "HCL TECHNOLOGIES",
             "TECH MAHINDRA", "ACCENTURE SOLUTIONS", "CAPGEMINI TECHNOLOGY", "COGNIZANT", "DELOITTE", "KPMG INDIA",
             "EY GDS", "RELIANCE RETAIL", "FLIPKART INTERNET", "AMAZON DEVELOPMENT CENTRE", "RAZORPAY SOFTWARE",
             "ZOMATO LTD", "SWIGGY", "PHONEPE PVT LTD", "PAYTM", "FRESHWORKS", "ZOHO CORP", "BYJUS", "OLA ELECTRIC",
             "HDFC BANK LTD", "ICICI BANK", "AXIS BANK", "KOTAK MAHINDRA", "LARSEN AND TOUBRO", "MAHINDRA AND MAHINDRA",
             "BOSCH LTD", "SIEMENS", "SAMSUNG INDIA", "GOOGLE INDIA", "MICROSOFT INDIA", "ADOBE SYSTEMS", "ORACLE INDIA",
             "SAP LABS", "NVIDIA GRAPHICS", "QUALCOMM INDIA", "INTEL TECHNOLOGY", "CISCO SYSTEMS", "JIO PLATFORMS",
             "SUN PHARMA", "DR REDDYS", "ASIAN PAINTS", "HINDUSTAN UNILEVER", "ITC LTD", "NESTLE INDIA",
             "STARTUP LABS PVT LTD", "NEXGEN SOFTWARE", "BLUE ORBIT TECHNOLOGIES", "VERTEX CONSULTING",
             "MINDTREE", "PERSISTENT SYSTEMS", "MPHASIS", "LTIMINDTREE", "COFORGE", "BIRLASOFT",
             "INDIAN INSTITUTE OF SCIENCE", "IIT BOMBAY", "DRDO", "ISRO", "BHARAT ELECTRONICS", "NTPC", "ONGC"]
PEOPLE = ["RAHUL SHARMA", "PRIYA SHARMA", "AMIT KUMAR", "SNEHA PATEL", "ROHIT VERMA", "ANJALI SINGH", "VIKRAM NAIR",
          "MEERA IYER", "ARJUN REDDY", "KAVYA RAO", "SURESH GUPTA", "POOJA MEHTA", "NIKHIL JAIN", "DEEPIKA DAS",
          "RAMESH KUMAR", "SUNITA DEVI", "MANISH AGARWAL", "NEHA KAPOOR", "KARTHIK S", "DIVYA M", "ASHOK YADAV",
          "LAKSHMI N", "HARSH VARDHAN", "RITU CHAUHAN", "SANJAY MISHRA", "ANITA JOSHI", "VIVEK TIWARI", "SHREYA GHOSH",
          "ADITYA BHAT", "NISHA KHAN", "MOHAMMED IRFAN", "FATIMA SHAIKH", "JOSEPH THOMAS", "ANNA GEORGE",
          "GURPREET SINGH", "SIMRAN KAUR", "TANVI DESAI", "YASH SHAH", "RAJESH PILLAI", "SWATI KULKARNI",
          "ABHISHEK SAXENA", "ISHA MALHOTRA", "VARUN KHANNA", "PALLAVI DESHPANDE", "SACHIN PAWAR", "RINA BORA",
          "DHRUV MEHRA", "AARTI SONI", "PRANAV JOSHI", "SHALINI MENON", "KIRAN B", "BHAVNA GOEL", "MUKESH RANA",
          "RAJU", "MUMMY", "PAPA", "BHAIYA", "DIDI", "AKASH", "MOM", "DAD"]
LANDLORD_NOTES = ["HOUSE RENT", "RENT", "ROOM RENT", "FLAT RENT", "PG RENT", "MONTHLY RENT", "RENT FOR FLAT 302",
                  "RENT {MON}", "HOUSE RENT {MON}", "RENT {MON} {YYYY}", "MAINTENANCE AND RENT", "RENT PAYMENT",
                  "RENT 2BHK", "HOSTEL RENT", "SECURITY DEPOSIT RENT", "RENT ADVANCE"]
RENT_PLATFORMS = ["NOBROKER", "NOBROKER TECHNOLOGIES", "NESTAWAY", "STANZA LIVING", "ZOLO STAYS", "COLIVE",
                  "HOUSING.COM RENT PAY", "RENTPAY", "CRED RENT", "MAGICBRICKS RENT", "PAYTM RENT PAYMENT",
                  "ZOLOSTAYS", "YOUR SPACE PG", "SOCIETY MAINTENANCE", "APNACOMPLEX MAINTENANCE", "MYGATE MAINTENANCE",
                  "ADDA SOCIETY MAINTENANCE", "PRESTIGE APARTMENTS MAINT", "RWA MAINTENANCE"]
VPAS = ["@ybl", "@okaxis", "@okhdfcbank", "@oksbi", "@okicici", "@paytm", "@upi", "@icici", "@hdfcbank", "@axisbank",
        "@ibl", "@axl", "@apl", "@yesbank", "@kotak", "@ptyes", "@ptaxis", "@sbi", "@cnrb", "@boi", "@pnb", "@fbl"]
CITIES = ["BENGALURU", "BANGALORE", "MUMBAI", "DELHI", "NEW DELHI", "PUNE", "HYDERABAD", "CHENNAI", "KOLKATA",
          "AHMEDABAD", "GURGAON", "GURUGRAM", "NOIDA", "JAIPUR", "LUCKNOW", "KOCHI", "INDORE", "CHANDIGARH", "BHOPAL",
          "NAGPUR", "SURAT", "VADODARA", "COIMBATORE", "MYSURU", "THANE", "NAVI MUMBAI", "VIZAG", "PATNA", "BHUBANESWAR",
          "DEHRADUN", "GOA", "MANGALORE", "TRIVANDRUM", "GUWAHATI", "RANCHI", "RAIPUR", "KANPUR", "AGRA", "VARANASI"]
BANKS = ["HDFC", "SBI", "ICICI", "AXIS", "KOTAK", "PNB", "BOB", "CANARA", "UNION", "IDFC", "YES", "INDUSIND", "FEDERAL",
         "BOI", "IOB", "CBI", "UCO", "RBL", "AU SMALL FIN", "BANDHAN"]
IFSC_PREFIX = ["HDFC0", "SBIN0", "ICIC0", "UTIB0", "KKBK0", "PUNB0", "BARB0", "CNRB0", "UBIN0", "IDFB0", "YESB0",
               "INDB0", "FDRL0", "BKID0", "IOBA0", "CBIN0", "UCBA0", "RATN0", "AUBL0", "BDBL0"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTHS_LONG = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER",
               "NOVEMBER", "DECEMBER"]
YEARS = ["2024", "2025", "2026"]
HINGLISH_NOTES = ["ghar ka kharcha", "chai", "khana", "lunch", "dinner", "party", "petrol", "milk", "sabzi",
                  "mummy ko", "udhaar wapas", "split bill", "movie", "gift", "shaadi gift", "room rent", "bike",
                  "recharge", "fees", "books", "medicine", "trip", "goa trip", "cab share", "pizza", "thanks",
                  "returning money", "for groceries", "paid", "sent via upi", "payment", "ok", "bill", "dues", "share"]
NOTE_BY_CLASS = {
    "transfers": ["UPI", "PAYMENT FROM PHONE", "SENT VIA GPAY", "NA", "UDHAAR", "RETURN", "SPLIT", "LEND", "GIFT",
                  "MONEY", "FOR MOM", "PAID BACK", "DINNER SHARE", "TRIP SHARE", "PAY", "SELF", "TO SELF",
                  "OWN ACCOUNT TRANSFER", "FUND TRANSFER", "FAMILY", "POCKET MONEY", "HELP", "LOAN TO FRIEND",
                  "SHAADI GIFT", "BIRTHDAY GIFT", "BIRTHDAY", "DIWALI GIFT", "ADVANCE", "FOR BOOKS", "CAB SHARE"],
}

# ── generated narration formats ─────────────────────────────────────────────
# Each entry: (template_id, format string). Slots: {M} merchant/payee, {V} vpa handle, {R10} {R12} {R16} refs,
# {CARD} masked card, {CITY}, {IFSC}, {MON}, {MONL}, {YYYY}, {NOTE}, {BANK}, {ATMID}, {ACCT}, {N}
UPI_FORMATS = [
    ("upi_hdfc", "UPI-{M}-{VPAID}{V}-{R12}-{NOTE}"),
    ("upi_hdfc2", "UPI-{M}-{VPAID}{V}-{R12}-UPI"),
    ("upi_sbi", "UPI/DR/{R12}/{M}/{BANK}/{VPAID}{V}/{NOTE}"),
    ("upi_sbi_cr", "UPI/CR/{R12}/{M}/{BANK}/{VPAID}{V}/{NOTE}"),
    ("upi_icici", "UPI/{R12}/{NOTE}/{VPAID}{V}/{M}"),
    ("upi_axis", "UPI/P2M/{R12}/{M}/{NOTE}"),
    ("upi_axis_p2a", "UPI/P2A/{R12}/{M}/{BANK}/{NOTE}"),
    ("upi_kotak", "UPI/{M}/{R12}/{NOTE}"),
    ("upi_short", "UPI-{R12}-{M}"),
    ("upi_bob", "UPI/{R12}/{M}/{VPAID}{V}"),
    ("upi_pnb", "UPI/{R12}/{M}/{NOTE}/{BANK}"),
    ("upi_lower", "upi-{m}-{vpaid}{v}-{R12}"),
    ("upi_phonepe", "PHONEPE-{M}-{R12}"),
    ("upi_gpay", "GPAY-{M}-{R12}-{NOTE}"),
    ("upi_paytm", "PAYTM-{M}-{R12}"),
    ("upi_mandate", "UPI MANDATE-{M}-{R12}-AUTOPAY"),
]
POS_FORMATS = [
    ("pos_hdfc", "POS {CARD} {M}"),
    ("pos_city", "POS {CARD} {M} {CITY}"),
    ("pos_icici", "VPS/{M}/{DD}-{MM}-{YY}/{R6}"),
    ("pos_axis", "POS/{M}/{CITY}/{R8}"),
    ("pos_sbi", "DEBIT CARD PURCHASE {M} {CITY}"),
    ("pos_ecom", "ECOM PUR/{M}/{R12}"),
    ("pos_ecom2", "ECOM {CARD} {M}"),
    ("pos_kotak", "PCD/{M}/{CITY}"),
    ("pos_intl", "INTL POS {CARD} {M}"),
    ("pos_cc", "CC PURCHASE {M} {CITY}"),
    ("pos_short", "{M} {CITY} IND"),
    ("pos_lower", "pos {CARD} {m}"),
    ("pos_dc", "DC PUR {M} {CITY} {R6}"),
    ("pos_tap", "TAP AND PAY {M}"),
]
BILL_FORMATS = [
    ("bill_billdesk", "BILLDESK-{M}"),
    ("bill_billdesk2", "BILLDESK {M} BILL PAYMENT"),
    ("bill_bbps", "BBPS/{M}/{R12}"),
    ("bill_bbps2", "BBPS-{M}-{R10}"),
    ("bill_si", "{M} BILL-SI"),
    ("bill_si2", "SI-{M}-{R8}"),
    ("bill_autopay", "AUTOPAY {M} {MON}"),
    ("bill_plain", "{M} BILL PAYMENT"),
    ("bill_payu", "PAYU-{M}-{R10}"),
    ("bill_ccavenue", "CCAVENUE*{M}"),
    ("bill_razorpay", "RAZORPAY*{M}"),
    ("bill_ib", "IB BILLPAY DR-{M}-{R8}"),
    ("bill_upi", "UPI-{M}-{VPAID}{V}-{R12}-BILL"),
]
NEFT_FORMATS_CR = [
    ("neft_cr_hdfc", "NEFT CR-{IFSC}-{M}-{NOTE}"),
    ("neft_cr_sbi", "BY TRANSFER-NEFT*{IFSC}*{R16}*{M}"),
    ("neft_cr_icici", "NEFT-{R16}-{M}-{NOTE}"),
    ("neft_cr_axis", "NEFT/{M}/{R16}/{NOTE}"),
    ("imps_cr", "IMPS-{R12}-{M}-{NOTE}"),
    ("imps_cr2", "IMPS/P2A/{R12}/{M}/{BANK}"),
    ("rtgs_cr", "RTGS CR-{IFSC}-{M}-{NOTE}"),
    ("ft_cr", "FT - CR - {ACCT} - {M}"),
]
NEFT_FORMATS_DR = [
    ("neft_dr_hdfc", "NEFT DR-{IFSC}-{M}-NETBANK-{NOTE}"),
    ("neft_dr_sbi", "TO TRANSFER-NEFT*{IFSC}*{R16}*{M}"),
    ("neft_dr_icici", "NEFT-{R16}-{M}-{NOTE}"),
    ("imps_dr", "IMPS-{R12}-{M}-{NOTE}"),
    ("imps_dr2", "IMPS/P2A/{R12}/{M}/{BANK}/{NOTE}"),
    ("imps_dr3", "MMT/IMPS/{R12}/{NOTE}/{M}/{BANK}"),
    ("rtgs_dr", "RTGS DR-{IFSC}-{M}-{NOTE}"),
    ("ft_dr", "FT - DR - {ACCT} - {M}"),
]
SALARY_FORMATS = [
    ("sal_neft", "NEFT CR-{IFSC}-{M}-SALARY {MON} {YYYY}"),
    ("sal_neft2", "NEFT CR-{IFSC}-{M}-SAL {MON}"),
    ("sal_sbi", "BY TRANSFER-NEFT*{IFSC}*{R16}*{M} SALARY"),
    ("sal_sbi2", "BY TRANSFER-NEFT*{IFSC}*{R16}*{M}"),
    ("sal_icici", "SAL/{M}/{MON}{YY}"),
    ("sal_axis", "SALARY-{M}-{MONL} {YYYY}"),
    ("sal_ach", "ACH C- {M}-SALARY-{R8}"),
    ("sal_imps", "IMPS-{R12}-{M}-SALARY {MON}"),
    ("sal_plain", "{M} SALARY CREDIT {MON}"),
    ("sal_plain2", "SALARY {MONL} {YYYY} {M}"),
    ("sal_stipend", "NEFT CR-{IFSC}-{M}-STIPEND {MON}"),
    ("sal_payroll", "{M} PAYROLL {MON}{YYYY}"),
    ("sal_wages", "IMPS-{R12}-{M}-WAGES {MON}"),
    ("sal_bonus", "NEFT CR-{IFSC}-{M}-BONUS AND SAL {MON}"),
    ("sal_lower", "neft cr-{IFSC}-{m}-salary {mon} {YYYY}"),
    ("sal_rev", "{M} SAL {MON} {YYYY} NEFT CR {IFSC}"),
]
RENT_FORMATS = [
    ("rent_imps", "IMPS-{R12}-{M}-{RNOTE}"),
    ("rent_upi", "UPI-{M}-{VPAID}{V}-{R12}-{RNOTE}"),
    ("rent_upi_sbi", "UPI/DR/{R12}/{M}/{BANK}/{VPAID}{V}/{RNOTE}"),
    ("rent_neft", "NEFT DR-{IFSC}-{M}-NETBANK-{RNOTE}"),
    ("rent_neft_sbi", "TO TRANSFER-NEFT*{IFSC}*{R16}*{M} {RNOTE}"),
    ("rent_platform", "{RP} {RNOTE}"),
    ("rent_platform2", "UPI-{RP}-{VPAID}{V}-{R12}-{RNOTE}"),
    ("rent_platform3", "POS {CARD} {RP}"),
    ("rent_platform4", "RAZORPAY*{RP}"),
    ("rent_si", "SI-{RP}-{RNOTE}"),
    ("rent_plain", "{RNOTE} {M}"),
    ("rent_plain2", "{RNOTE} PAID TO {M}"),
]
CASH_FORMATS = [
    ("atm_hdfc", "ATW-{CARD}-{ATMID}-{CITY}"),
    ("atm_hdfc2", "ATW-{CARD}-{ATMID}-{CITY}-{R6}"),
    ("atm_sbi", "ATM WDL-ATM CASH {R6} {CITY} {BANK}"),
    ("atm_sbi2", "ATM CASH WDL {CITY} {DD}{MM}{YY}"),
    ("atm_nwd", "NWD-{CARD}-{ATMID}-{CITY}"),
    ("atm_nfs", "NFS/CASH WDL/{R8}/{CITY}"),
    ("atm_eaw", "EAW-{CARD}-{ATMID}-{CITY}"),
    ("atm_icici", "ATM/CASH WDL/{CITY}/{R6}"),
    ("atm_axis", "ATM-CASH/{ATMID}/{CITY}/{R6}"),
    ("atm_plain", "CASH WITHDRAWAL {CITY} ATM"),
    ("atm_plain2", "ATM CASH WITHDRAWAL"),
    ("atm_self", "CASH WITHDRAWAL SELF"),
    ("atm_branch", "CASH WDL AT BRANCH {CITY}"),
    ("atm_chq", "SELF CHQ CASH {R6}"),
    ("atm_cwdr", "CWDR/{ATMID}/{CITY}"),
    ("atm_other_bank", "ATM WDL {BANK} ATM {CITY} {R6}"),
    ("atm_micro", "AEPS CASH WITHDRAWAL {R8}"),
    ("atm_cdm", "CASH WDL CDM {CITY}"),
    ("atm_lower", "atw-{CARD}-{ATMID}-{city}"),
    ("atm_upi_atm", "UPI ATM CASH WDL {R12}"),
]
EMI_FORMATS = [
    ("emi_ach", "ACH D- {M}-{R10}"),
    ("emi_ach2", "ACH D- {M}-EMI-{R8}"),
    ("emi_ach3", "ACH DEBIT {M} LOAN EMI"),
    ("emi_nach", "NACH-{M}-{R12}"),
    ("emi_nach2", "NACH DR {M} {MON} EMI"),
    ("emi_ecs", "ECS/{M}/{R10}"),
    ("emi_si", "SI-{M}-LOAN A/C {ACCT}"),
    ("emi_plain", "EMI {N} {M} LOAN A/C {ACCT}"),
    ("emi_plain2", "{M} EMI {MON} {YYYY}"),
    ("emi_plain3", "LOAN EMI {M}"),
    ("emi_upi", "UPI-{M}-{VPAID}{V}-{R12}-EMI"),
    ("emi_bill", "BILLDESK-{M}-EMI"),
    ("emi_cc", "{M}"),
    ("emi_cc2", "CREDIT CARD PAYMENT {M}"),
    ("emi_cc3", "IB BILLPAY DR-{M}-{R8}"),
    ("emi_cc4", "CC BILL PAYMENT {M} {MON}"),
    ("emi_home", "HOME LOAN EMI {M} {MON}{YYYY}"),
    ("emi_car", "CAR LOAN INSTALMENT {M}"),
    ("emi_pl", "PERSONAL LOAN EMI {M} {R8}"),
    ("emi_bnpl", "{M} PAY LATER REPAYMENT"),
]
INVEST_FORMATS = [
    ("inv_ach", "ACH D- {M}-{R10}"),
    ("inv_ach_sip", "ACH D- {M}-MF SIP"),
    ("inv_ach_sip2", "ACH D- {M}-SIP-{R8}"),
    ("inv_nach", "NACH-{M}-SIP-{R12}"),
    ("inv_nach2", "NACH DR {M} {MON} SIP"),
    ("inv_si", "SI {M} SIP {MON}"),
    ("inv_upi", "UPI-{M}-{VPAID}{V}-{R12}-SIP"),
    ("inv_upi2", "UPI-{M}-{VPAID}{V}-{R12}-UPI"),
    ("inv_upi_mandate", "UPI MANDATE-{M}-{R12}-SIP AUTOPAY"),
    ("inv_neft", "NEFT DR-{IFSC}-{M}-NETBANK-INVESTMENT"),
    ("inv_bse", "BSE LTD-{M}-{R8}"),
    ("inv_plain", "{M} SIP"),
    ("inv_plain2", "MF PURCHASE {M}"),
    ("inv_fd", "FD BOOKED {ACCT}"),
    ("inv_fd2", "TRANSFER TO FD A/C {ACCT}"),
    ("inv_rd", "RD INSTALMENT {ACCT} {MON}"),
    ("inv_ppf", "PPF DEPOSIT A/C {ACCT}"),
    ("inv_nps", "NPS CONTRIBUTION {M}"),
    ("inv_lic", "{M} PREMIUM {MON}"),
    ("inv_lic2", "ACH D- {M}-PREMIUM-{R8}"),
    ("inv_pos", "POS {CARD} {M}"),
    ("inv_broker", "{M} FUNDS TRANSFER {R8}"),
    ("inv_sgb", "SGB SUBSCRIPTION {M}"),
    ("inv_redemption_cr", "NEFT CR-{IFSC}-{M}-REDEMPTION"),
    ("inv_redemption_cr2", "ACH C- {M}-MF REDEMPTION-{R8}"),
    ("inv_dividend_cr", "ACH C- {M}-DIVIDEND"),
    ("inv_fd_mat_cr", "FD MATURITY PROCEEDS {ACCT}"),
    ("inv_payout_cr", "NEFT CR-{IFSC}-{M}-PAYOUT"),
    ("inv_lower", "ach d- {m}-mf sip"),
]
FEES_FORMATS = [
    ("fee_plain", "{M}"),
    ("fee_gst", "{M} INCL GST"),
    ("fee_gst2", "{M} + GST"),
    ("fee_mon", "{M} {MON} {YYYY}"),
    ("fee_mon2", "{M} FOR {MONL}"),
    ("fee_acct", "{M} A/C {ACCT}"),
    ("fee_card", "{M} {CARD}"),
    ("fee_dr", "DR {M}"),
    ("fee_chg", "{M} CHG"),
    ("fee_ref", "{M} {R8}"),
    ("fee_lower", "{m}"),
    ("fee_bank", "{BANK} {M}"),
]
TRANSFER_FORMATS_DR = [
    ("tr_upi_hdfc", "UPI-{M}-{VPAID}{V}-{R12}-{TNOTE}"),
    ("tr_upi_hdfc2", "UPI-{M}-{VPAID}{V}-{R12}-UPI"),
    ("tr_upi_sbi", "UPI/DR/{R12}/{M}/{BANK}/{VPAID}{V}/{TNOTE}"),
    ("tr_upi_icici", "UPI/{R12}/{TNOTE}/{VPAID}{V}/{M}"),
    ("tr_upi_axis", "UPI/P2A/{R12}/{M}/{BANK}/{TNOTE}"),
    ("tr_upi_kotak", "UPI/{M}/{R12}/{TNOTE}"),
    ("tr_imps", "IMPS-{R12}-{M}-{TNOTE}"),
    ("tr_imps2", "IMPS/P2A/{R12}/{M}/{BANK}/{TNOTE}"),
    ("tr_imps3", "MMT/IMPS/{R12}/{TNOTE}/{M}/{BANK}"),
    ("tr_neft", "NEFT DR-{IFSC}-{M}-NETBANK-{TNOTE}"),
    ("tr_neft_sbi", "TO TRANSFER-NEFT*{IFSC}*{R16}*{M}"),
    ("tr_neft_sbi2", "TO TRANSFER-INB {M} {TNOTE}"),
    ("tr_ft", "FT - DR - {ACCT} - {M}"),
    ("tr_self", "TRANSFER TO OWN A/C {ACCT}"),
    ("tr_self2", "FUND TRF TO SELF {BANK} {ACCT}"),
    ("tr_self3", "IMPS-{R12}-SELF-{BANK}"),
    ("tr_self4", "UPI-SELF-{VPAID}{V}-{R12}-TO SELF"),
    ("tr_wallet", "PAYTM WALLET LOAD {R10}"),
    ("tr_wallet2", "UPI-ADD MONEY PHONEPE WALLET-{R12}"),
    ("tr_wallet3", "AMAZON PAY WALLET LOAD"),
    ("tr_gpay", "GPAY-{M}-{R12}-{TNOTE}"),
    ("tr_phonepe", "PHONEPE-{M}-{R12}"),
    ("tr_lower", "upi-{m}-{vpaid}{v}-{R12}-{tnote}"),
    ("tr_chq", "CHQ PAID {R6} {M}"),
    ("tr_dd", "DD ISSUED {M}"),
]
TRANSFER_FORMATS_CR = [
    ("tr_cr_upi_hdfc", "UPI-{M}-{VPAID}{V}-{R12}-{TNOTE}"),
    ("tr_cr_upi_sbi", "UPI/CR/{R12}/{M}/{BANK}/{VPAID}{V}/{TNOTE}"),
    ("tr_cr_upi_icici", "UPI/{R12}/{TNOTE}/{VPAID}{V}/{M}"),
    ("tr_cr_upi_axis", "UPI/P2A/{R12}/{M}/{BANK}/{TNOTE}"),
    ("tr_cr_imps", "IMPS-{R12}-{M}-{TNOTE}"),
    ("tr_cr_imps2", "IMPS/P2A/{R12}/{M}/{BANK}"),
    ("tr_cr_neft", "NEFT CR-{IFSC}-{M}-{TNOTE}"),
    ("tr_cr_neft_sbi", "BY TRANSFER-NEFT*{IFSC}*{R16}*{M}"),
    ("tr_cr_neft_sbi2", "BY TRANSFER-INB {M} {TNOTE}"),
    ("tr_cr_ft", "FT - CR - {ACCT} - {M}"),
    ("tr_cr_self", "TRANSFER FROM OWN A/C {ACCT}"),
    ("tr_cr_self2", "IMPS-{R12}-SELF-{BANK}"),
    ("tr_cr_chq", "CHQ DEP {R6} {M}"),
    ("tr_cr_cash_dep", "CASH DEPOSIT {CITY} BRANCH"),
    ("tr_cr_cdm", "CDM CASH DEPOSIT {CITY}"),
    ("tr_cr_gpay", "GPAY-{M}-{R12}-{TNOTE}"),
    ("tr_cr_lower", "upi-{m}-{vpaid}{v}-{R12}-{tnote}"),
]

# (label, formats, merchant list, direction, weight) — the spec of what to generate for each class
SPEC: dict[str, list[tuple[list[tuple[str, str]], list[str], str, float]]] = {
    "groceries": [(UPI_FORMATS, MERCHANTS["groceries"], "debit", 0.6), (POS_FORMATS, MERCHANTS["groceries"], "debit", 0.4)],
    "dining": [(UPI_FORMATS, MERCHANTS["dining"], "debit", 0.65), (POS_FORMATS, MERCHANTS["dining"], "debit", 0.35)],
    "travel": [(UPI_FORMATS, MERCHANTS["travel"], "debit", 0.5), (POS_FORMATS, MERCHANTS["travel"], "debit", 0.35),
               (BILL_FORMATS[8:11], MERCHANTS["travel"], "debit", 0.15)],
    "fuel": [(POS_FORMATS, MERCHANTS["fuel"], "debit", 0.55), (UPI_FORMATS, MERCHANTS["fuel"], "debit", 0.45)],
    "utilities": [(BILL_FORMATS, MERCHANTS["utilities"], "debit", 0.6), (UPI_FORMATS, MERCHANTS["utilities"], "debit", 0.3),
                  (POS_FORMATS, MERCHANTS["utilities"], "debit", 0.1)],
    "shopping": [(POS_FORMATS, MERCHANTS["shopping"], "debit", 0.5), (UPI_FORMATS, MERCHANTS["shopping"], "debit", 0.4),
                 (BILL_FORMATS[8:11], MERCHANTS["shopping"], "debit", 0.1)],
    "subscriptions": [(POS_FORMATS, MERCHANTS["subscriptions"], "debit", 0.5), (UPI_FORMATS[-1:] + UPI_FORMATS[:4],
                      MERCHANTS["subscriptions"], "debit", 0.3), (BILL_FORMATS[4:7] + BILL_FORMATS[8:11],
                      MERCHANTS["subscriptions"], "debit", 0.2)],
    "emi_loan": [(EMI_FORMATS, MERCHANTS["emi_loan"], "debit", 1.0)],
    "investments": [(INVEST_FORMATS[:23], MERCHANTS["investments"], "debit", 0.85),
                    (INVEST_FORMATS[23:28], MERCHANTS["investments"], "credit", 0.15)],
    "fees": [(FEES_FORMATS, MERCHANTS["fees"], "debit", 1.0)],
    "cash": [(CASH_FORMATS, [""], "debit", 1.0)],
    "salary": [(SALARY_FORMATS, COMPANIES, "credit", 1.0)],
    "rent": [(RENT_FORMATS, PEOPLE, "debit", 1.0)],
    "transfers": [(TRANSFER_FORMATS_DR, PEOPLE, "debit", 0.6), (TRANSFER_FORMATS_CR, PEOPLE, "credit", 0.4)],
}

AMOUNT_RANGE = {"salary": (18000, 250000), "rent": (5000, 60000), "groceries": (80, 6000), "dining": (60, 4000),
                "travel": (40, 25000), "fuel": (200, 6000), "utilities": (99, 8000), "shopping": (150, 60000),
                "subscriptions": (99, 3000), "emi_loan": (1500, 60000), "investments": (500, 100000),
                "transfers": (50, 100000), "fees": (5, 1500), "cash": (500, 25000)}

_KEY_RE = re.compile(r"[^a-z0-9]+")


def _key(text: str) -> str:
    return _KEY_RE.sub(" ", text.lower()).strip()


def model_text(row: dict) -> str:
    """What the classifier sees: the sign of the transaction plus the narration."""
    return f"{row.get('direction', 'debit')} | {row['text']}"


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def _vpa_id(rng: random.Random, merchant: str) -> str:
    base = re.sub(r"[^a-z0-9]", "", merchant.lower())[:12] or "pay"
    styles = [base, base + ".payu", base + ".rzp", base + str(rng.randint(1, 99)), "q" + _digits(rng, 8),
              base + ".bd", "paytm-" + _digits(rng, 8), "paytmqr" + _digits(rng, 10), base + "." + _digits(rng, 4),
              base + "@", "bharatpe" + _digits(rng, 8), "gpay-" + _digits(rng, 10)]
    out = rng.choice(styles)
    return out.rstrip("@")


def _fill(fmt: str, merchant: str, rng: random.Random, label: str) -> str:
    mon_i = rng.randrange(12)
    vpa = rng.choice(VPAS)
    note_pool = NOTE_BY_CLASS.get("transfers")
    tnote = rng.choice(note_pool + HINGLISH_NOTES) if rng.random() < 0.8 else _digits(rng, 6)
    note = rng.choice(["UPI", "PAYMENT", "NA", "ORDER", "BILL", "PAY", "", (merchant.split() or ["PAY"])[0], "ONLINE",
                       "PURCHASE", "FOOD", "TRIP", "RECHARGE", "SUBSCRIPTION", "PAYMENT FROM PHONE",
                       rng.choice(HINGLISH_NOTES)])
    values = {
        "M": merchant, "m": merchant.lower(), "V": vpa, "v": vpa, "VPAID": _vpa_id(rng, merchant),
        "vpaid": _vpa_id(rng, merchant), "R6": _digits(rng, 6), "R8": _digits(rng, 8), "R10": _digits(rng, 10),
        "R12": _digits(rng, 12), "R16": _digits(rng, 16), "CARD": f"{_digits(rng, 6)}XXXXXX{_digits(rng, 4)}",
        "CITY": rng.choice(CITIES), "city": rng.choice(CITIES).lower(), "IFSC": rng.choice(IFSC_PREFIX) + _digits(rng, 6),
        "MON": MONTHS[mon_i], "mon": MONTHS[mon_i].lower(), "MONL": MONTHS_LONG[mon_i], "YYYY": rng.choice(YEARS),
        "YY": rng.choice(YEARS)[2:], "DD": f"{rng.randint(1, 28):02d}", "MM": f"{mon_i + 1:02d}", "NOTE": note,
        "BANK": rng.choice(BANKS), "ATMID": rng.choice(["S1AW", "SBIN", "HDFC", "ICIC", "AXIS", "KKBK", "PUNB"])
        + _digits(rng, 4), "ACCT": "XXXX" + _digits(rng, 4) if rng.random() < 0.5 else _digits(rng, 11),
        "N": str(rng.randint(1, 60)), "TNOTE": tnote, "tnote": tnote.lower(),
        "RNOTE": rng.choice(LANDLORD_NOTES).replace("{MON}", MONTHS[mon_i]).replace("{YYYY}", rng.choice(YEARS)),
        "RP": rng.choice(RENT_PLATFORMS),
    }
    out = fmt
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def _noise(text: str, rng: random.Random) -> str:
    """Statement-export noise: casing, separators, truncation, masked digits, trailing junk."""
    r = rng.random()
    if r < 0.12:
        text = text.lower()
    elif r < 0.18:
        text = text.title()
    if rng.random() < 0.10:
        text = text.replace("-", " ")
    if rng.random() < 0.06:
        text = text.replace("/", " ")
    if rng.random() < 0.08:  # exports often truncate narrations
        text = text[: rng.randint(22, max(23, len(text) - 1))]
    if rng.random() < 0.06:
        text = re.sub(r"\d{4,}", lambda m: m.group(0)[:2] + "X" * (len(m.group(0)) - 4) + m.group(0)[-2:], text, count=1)
    if rng.random() < 0.05:
        text = text + " " + rng.choice(["IND", "IN", "MUMBAI IN", "BANGALORE IN", "Ref No " + _digits(rng, 10)])
    if rng.random() < 0.04:
        text = "  " + text + "  "
    return " ".join(text.split())


def _amount(label: str, rng: random.Random) -> float:
    lo, hi = AMOUNT_RANGE[label]
    value = rng.uniform(lo, hi) if rng.random() < 0.5 else rng.choice([lo, hi, 99, 149, 199, 299, 499, 999, 1500,
                                                                         2000, 5000, 10000, 20000, 25000])
    value = min(max(value, lo), hi)
    return round(value, 2) if rng.random() < 0.6 else float(int(value))


def _generate(label: str, n: int, rng: random.Random, seen: set[str]) -> list[dict]:
    rows: list[dict] = []
    per_template: Counter[str] = Counter()
    specs = SPEC[label]
    weights = [w for _, _, _, w in specs]
    attempts = 0
    while len(rows) < n and attempts < n * 40:
        attempts += 1
        formats, merchants, direction, _ = rng.choices(specs, weights=weights)[0]
        template_id, fmt = rng.choice(formats)
        merchant = rng.choice(merchants)
        cap = max(8, n // max(4, len(formats) // 2))
        if per_template[template_id] >= cap:
            continue
        text = _noise(_fill(fmt, merchant, rng, label), rng)
        key = _key(text)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        per_template[template_id] += 1
        rows.append({"text": text, "direction": direction, "amount": _amount(label, rng), "label": label,
                     "template": template_id, "source": "generated"})
    return rows


# ── demo statement rows ──────────────────────────────────────────────────────
# Author labels for the distinct narration patterns of samples/bank_statement_demo.csv (substring → label).
SAMPLE_LABELS: list[tuple[str, str]] = [
    ("SALARY", "salary"), ("HOUSE RENT", "rent"), ("ZEPTO", "groceries"), ("BLINKIT", "groceries"),
    ("BIGBASKET", "groceries"), ("DMART", "groceries"), ("INSTAMART", "groceries"), ("SWIGGY", "dining"),
    ("ZOMATO", "dining"), ("STARBUCKS", "dining"), ("CHAAYOS", "dining"), ("DOMINOS", "dining"), ("CAFE", "dining"),
    ("OLA", "travel"), ("UBER", "travel"), ("IRCTC", "travel"), ("INDIGO", "travel"), ("RAPIDO", "travel"),
    ("METRO", "travel"), ("PETROL", "fuel"), ("BESCOM", "utilities"), ("AIRTEL", "utilities"), ("ACT FIBERNET", "utilities"),
    ("JIO", "utilities"), ("FLIPKART", "shopping"), ("AMAZON", "shopping"), ("MYNTRA", "shopping"), ("IKEA", "shopping"),
    ("CROMA", "shopping"), ("NYKAA", "shopping"), ("DECATHLON", "shopping"), ("NETFLIX", "subscriptions"),
    ("SPOTIFY", "subscriptions"), ("CHATGPT", "subscriptions"), ("HOTSTAR", "subscriptions"), ("CULT", "subscriptions"),
    ("ZERODHA", "investments"), ("GROWW", "investments"), ("LIC", "investments"), ("EMI", "emi_loan"),
    ("CRED", "emi_loan"), ("LOAN", "emi_loan"), ("ATW-", "cash"), ("NWD-", "cash"), ("ATM", "cash"),
    ("CHARGES", "fees"), ("CHG", "fees"), ("FEE", "fees"), ("GST", "fees"), ("PRIYA SHARMA", "transfers"),
    ("RAHUL", "transfers"), ("AMIT", "transfers"), ("SNEHA", "transfers"), ("IMPS-", "transfers"),
    ("NEFT", "transfers"), ("UPI-", "transfers"),
]


def sample_rows() -> list[dict]:
    """samples/bank_statement_demo.csv narrations with author labels (refund/interest credits are skipped)."""
    if not SAMPLE_PATH.exists():
        return []
    rows: list[dict] = []
    with SAMPLE_PATH.open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            text = " ".join((rec.get("Narration") or "").split())
            debit = (rec.get("Withdrawal Amt.") or "").strip()
            credit = (rec.get("Deposit Amt.") or "").strip()
            if not text or not (debit or credit):
                continue
            upper = text.upper()
            if any(w in upper for w in ("REFUND", "CASHBACK", "INTEREST", "INT.PD", "REVERSAL")):
                continue
            label = next((lab for needle, lab in SAMPLE_LABELS if needle in upper), None)
            if label is None:
                continue
            amount = float(credit or debit)
            rows.append({"text": text, "direction": "credit" if credit else "debit", "amount": amount, "label": label,
                         "template": "sample", "source": "sample"})
    return rows


def build_train(seed: int = SEED, per_class: int = PER_CLASS) -> list[dict]:
    """Deterministic training set: generated rows + the demo statement (test-set texts are excluded)."""
    from ml.categoriser_test_set import TEST_ROWS

    rng = random.Random(seed)
    seen = {_key(t) for t, _, _ in TEST_ROWS}
    rows: list[dict] = []
    for label in LABELS:
        rows.extend(_generate(label, per_class, rng, seen))
    for row in sample_rows():
        key = _key(row["text"])
        if key not in seen:
            seen.add(key)
            rows.append(row)
    rng.shuffle(rows)
    return rows


def build_test() -> list[dict]:
    """The author-labelled test set in row form."""
    from ml.categoriser_test_set import TEST_ROWS

    out = []
    for text, amount, label in TEST_ROWS:
        assert label in LABELS, (text, label)
        out.append({"text": text, "direction": "credit" if amount > 0 else "debit", "amount": abs(float(amount)),
                    "label": label, "template": "author", "source": "author"})
    return out


def save(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load(path: Path = TRAIN_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing — run `python -m ml.categoriser_data` first")
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    train, test = build_train(), build_test()
    save(train, TRAIN_PATH)
    save(test, TEST_PATH)
    counts = Counter(r["label"] for r in train)
    print(f"train: {len(train)} rows -> {TRAIN_PATH}")
    for label in LABELS:
        print(f"  {label:14s} {counts[label]:5d}")
    print(f"  sources: {dict(Counter(r['source'] for r in train))}")
    print(f"test: {len(test)} rows -> {TEST_PATH}  {dict(Counter(r['label'] for r in test))}")


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
