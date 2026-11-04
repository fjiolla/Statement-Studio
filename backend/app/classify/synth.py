"""Synthetic labelled narrations for training the ML classifier.

No public labelled dataset of Indian bank narrations exists, so we generate
one from the formats observed in real statements (SBI, HDFC, ICICI, Union,
IndusInd, card statements). The point of the model is to generalise to
merchants the dictionary has never seen — so most "merchant" examples are
generic Indian business names ("SHREE GANESH MEDICAL STORE"), and person names
and business stems are split into disjoint train/test pools so the reported
accuracy reflects unseen names.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .merchants import MERCHANTS

FIRST = ["RAHUL", "PRIYA", "AMIT", "SNEHA", "VIKAS", "ANJALI", "ROHIT", "POOJA", "SURESH", "KAVITA", "MANOJ", "NEHA", "ARJUN",
         "DIVYA", "SANJAY", "MEERA", "KARAN", "RITU", "DEEPAK", "SUNITA", "RAJESH", "ANITA", "ABDUL", "FATIMA", "MOHAMMED",
         "JOSEPH", "MARY", "GURPREET", "HARPREET", "VENKAT", "LAKSHMI", "SRINIVAS", "ARUN", "KRISHNA", "GANESH", "RAMESH",
         "SAMEER", "NIKHIL", "SHRUTI", "ADITYA", "VARUN", "TANVI", "ISHAAN", "NAVEEN", "SHALINI", "BHAVNA", "YOGESH", "PRAKASH",
         "DINESH", "HEMANT", "JYOTI", "MAHESH", "NARESH", "OMKAR", "PANKAJ", "RAVI", "SACHIN", "TARUN", "UMESH", "VIJAY", "ZOYA",
         "IBRAHIM", "SALMAN", "AISHA", "THOMAS"]
LAST = ["SHARMA", "VERMA", "GUPTA", "SINGH", "KUMAR", "PATEL", "SHAH", "REDDY", "NAIR", "IYER", "RAO", "JOSHI", "MEHTA",
        "DESAI", "KHAN", "SHAIKH", "DSOUZA", "FERNANDES", "PINTO", "BANERJEE", "CHATTERJEE", "DAS", "BOSE", "MUKHERJEE",
        "PILLAI", "MENON", "KULKARNI", "PAWAR", "JADHAV", "YADAV", "MISHRA", "PANDEY", "TIWARI", "CHAUHAN", "RATHORE",
        "AGARWAL", "JAIN", "BANSAL", "MALHOTRA", "KAPOOR", "SETHI", "BHATIA"]
STEMS = ["SHREE GANESH", "SAI KRUPA", "BALAJI", "JAI MATA DI", "NEW ROYAL", "OM SAI", "SHIV SHAKTI", "LAXMI", "GURU KRIPA",
         "MAHALAXMI", "SRI VENKATESWARA", "KRISHNA", "ANNAPURNA", "SUPREME", "CITY", "METRO", "GREEN LEAF", "STAR", "GOLDEN",
         "A1", "NATIONAL", "MODERN", "PARAMOUNT", "UNIQUE", "SHANTI", "JAI HIND", "VISHAL", "AMBIKA", "BHAGWATI", "SHUBH",
         "RAJ", "OSWAL", "AGGARWAL", "BOMBAY", "DELHI", "MADRAS", "HYDERABAD", "PUNJAB", "KERALA", "UDUPI", "SAGAR", "SUNRISE",
         "BLUE MOON", "SILVER OAK", "PRINCE", "EVERGREEN", "SHRIRAM", "MOTHER", "PARADISE", "NAVRANG", "KAMAL", "ASHOKA",
         "GOMTI", "NARMADA", "TRIVENI", "SURYA", "CHANDRA", "VINAYAK", "SIDDHI", "RIDDHI", "TIRUPATI", "DWARKA", "GOKUL"]
CITIES = ["MUMBAI", "DELHI", "BANGALORE", "BENGALURU", "PUNE", "HYDERABAD", "CHENNAI", "KOLKATA", "NOIDA", "GURGAON",
          "JAIPUR", "AHMEDABAD", "SURAT", "LUCKNOW", "INDORE", "THANE", "KOCHI", "GOA", "CHANDIGARH", "NAGPUR", "BHOPAL"]
BANKS = ["SBIN", "HDFC", "ICIC", "UTIB", "KKBK", "YESB", "PUNB", "BARB", "CNRB", "UBIN", "IDIB", "INDB", "FDRL", "IDFB", "PYTM"]
HANDLES = ["okaxis", "okhdfcbank", "okicici", "oksbi", "ybl", "ibl", "axl", "paytm", "upi", "apl", "freecharge", "kotak"]
COMPANIES = ["INFOSYS", "TCS", "WIPRO", "ACCENTURE SOLUTIONS", "COGNIZANT", "HCL TECHNOLOGIES", "TECH MAHINDRA", "ZETA LABS", "FRESHWORKS", "ACME ANALYTICS", "BRIGHT SOLUTIONS",
             "GLOBAL LOGISTICS", "SUNSHINE EXPORTS", "KRISHNA TEXTILES", "PIXEL STUDIOS", "QUANTUM SYSTEMS", "APEX INDUSTRIES"]

BUSINESS = {
    "food": ["RESTAURANT", "CAFE", "KITCHEN", "FOODS", "DHABA", "BIRYANI HOUSE", "SWEETS", "BAKERY", "HOTEL", "PIZZERIA",
             "CATERERS", "TIFFIN CENTRE", "JUICE CENTER", "CHAI POINT", "FAST FOOD", "BAR AND RESTAURANT", "FOOD COURT", "MESS"],
    "groceries": ["KIRANA STORE", "GENERAL STORE", "SUPERMARKET", "PROVISION STORE", "MART", "FRESH MART", "VEGETABLES",
                  "DAIRY", "MILK CENTRE", "GROCERY", "HYPERMARKET", "FRUITS AND VEG", "DEPARTMENTAL STORE"],
    "shopping": ["FASHION", "GARMENTS", "TEXTILES", "ELECTRONICS", "MOBILES", "FOOTWEAR", "JEWELLERS", "COLLECTION", "CREATIONS",
                 "BOUTIQUE", "OPTICALS", "GIFTS", "HARDWARE", "FURNITURE", "STATIONERS", "COSMETICS", "SAREES", "WATCH CO",
                 "COMPUTERS", "HOME APPLIANCES", "TOYS", "SPORTS"],
    "travel": ["TRAVELS", "TOURS AND TRAVELS", "CABS", "TAXI SERVICE", "TRANSPORT", "AIRWAYS", "PARKING", "TOLL PLAZA",
               "BUS SERVICE", "HOLIDAYS", "AUTO STAND", "RAILWAY CATERING"],
    "fuel": ["PETROLEUM", "FILLING STATION", "FUELS", "SERVICE STATION", "PETROL PUMP", "AUTO FUELS", "HP PETROL PUMP",
             "IOCL FUEL STATION", "BPCL PETRO"],
    "utilities": ["ELECTRICITY BOARD", "POWER CORP", "GAS AGENCY", "BROADBAND", "TELECOM", "CABLE NETWORK", "WATER WORKS",
                  "DIGITAL CABLE", "INTERNET SERVICES", "RECHARGE CENTRE"],
    "health": ["MEDICAL STORE", "PHARMACY", "CHEMIST", "HOSPITAL", "CLINIC", "DIAGNOSTICS", "PATHLAB", "DENTAL CARE",
               "MEDICOS", "HEALTHCARE", "NURSING HOME", "EYE CARE", "AYURVEDA", "PHYSIOTHERAPY"],
    "education": ["SCHOOL", "COLLEGE", "ACADEMY", "CLASSES", "INSTITUTE", "TUITION", "UNIVERSITY", "COACHING CENTRE",
                  "BOOK DEPOT", "PUBLIC SCHOOL", "LEARNING", "EDUCATION TRUST"],
    "entertainment": ["CINEMAS", "MULTIPLEX", "GAMING ZONE", "CLUB", "BOWLING", "AMUSEMENT PARK", "EVENTS", "STREAMING", "MUSIC"],
    "rent": ["PROPERTIES", "ESTATES", "APARTMENTS", "RESIDENCY", "CHS LTD", "HOUSING SOCIETY", "PG ACCOMMODATION", "HOSTEL"],
    "insurance": ["INSURANCE", "LIFE INSURANCE", "GENERAL INSURANCE", "ASSURANCE", "HEALTH INSURANCE"],
    "investment": ["SECURITIES", "WEALTH", "INVESTMENTS", "BROKING", "MUTUAL FUND", "ASSET MANAGEMENT", "STOCK BROKERS"],
    "loan": ["FINANCE", "FINSERV", "FINCORP", "CREDIT", "LENDING", "MICRO FINANCE", "HOUSING FINANCE", "MOTOR FINANCE"],
}
UPI_NOTES = ["Paym", "Payment", "NA", "UPI", "Sent from Paytm", "pay", "Collect", "OK", "Payment from Ph", "food", "rent",
             "dinner", "petrol", "bill", "groceries", "medicine", "fees"]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


@dataclass
class Example:
    text: str
    is_debit: bool
    amount: float
    statement_type: str
    label: str


def _ref(r: random.Random, n: int = 12) -> str:
    return "".join(r.choice("0123456789") for _ in range(n))


def _person(r: random.Random, pool_first, pool_last) -> str:
    style = r.random()
    f, l = r.choice(pool_first), r.choice(pool_last)
    if style < 0.35:
        return f"{f} {l}"
    if style < 0.6:
        return f"{f} {l[0]}"
    if style < 0.75:
        return f"MR {f} {l}"
    if style < 0.85:
        return f
    return f"{f}{l}"[:14]


def _vpa(r: random.Random, name: str) -> str:
    base = name.lower().replace(" ", "")[:12]
    if r.random() < 0.4:
        base = _ref(r, 10)
    return f"{base}@{r.choice(HANDLES)}"


def _amount(r: random.Random, lo: float, hi: float) -> float:
    return round(r.uniform(lo, hi), r.choice([0, 0, 2]))


def _upi(r: random.Random, name: str, debit: bool, vpa: str | None = None) -> str:
    vpa = vpa or _vpa(r, name)
    bank = r.choice(BANKS)
    dr = "DR" if debit else "CR"
    note = r.choice(UPI_NOTES)
    t = r.random()
    if t < 0.2:
        return f"UPI/{dr}/{_ref(r)}/{name}/{bank}/{vpa.split('@')[0]}/{note}"
    if t < 0.35:
        return f"{'WDL' if debit else 'DEP'} TFR UPI/{dr}/{_ref(r)}/{name}/{bank}/{vpa.split('@')[0]}/{note} 00976{_ref(r, 7)} AT 00529 {r.choice(CITIES)}"
    if t < 0.5:
        return f"UPI-{name}-{vpa}-{bank}0{_ref(r, 6)}-{_ref(r)}-{note.upper()}"
    if t < 0.62:
        return f"UPIA{'R' if debit else 'B'}/{_ref(r)}/{dr}/{name[:12]}/{bank}/{vpa[:16]}"
    if t < 0.74:
        return f"UPI{_ref(r)}{dr}{name.replace(' ', '')[:14]}{bank}{_ref(r, 10)}{vpa.split('@')[0][:8]}NA"
    if t < 0.86:
        return f"UPI/{_ref(r)}/{dr}/{name}/{vpa}"
    return f"MPAY/UPI/TRTR/{_ref(r)}/{name}/{vpa}"


def _card_spend(r: random.Random, merchant: str, stype: str) -> str:
    city = r.choice(CITIES)
    t = r.random()
    if stype == "credit_card":
        if t < 0.45:
            return f"{merchant} {city}"
        if t < 0.65:
            return f"{merchant}{' PVT LTD' if r.random() < 0.3 else ''} {city} IN"
        if t < 0.8:
            return f"PURCHASE - {_ref(r, 6)} - {merchant}"
        return f"{merchant[:18]}*{_ref(r, 6)} {city}"
    if t < 0.4:
        return f"POS {_ref(r, 6)}XXXXXX{_ref(r, 4)} {merchant[:22]} POS DEBIT"
    if t < 0.6:
        return f"VPS/{merchant[:16]}/{_ref(r)}/{city}"
    if t < 0.8:
        return f"PCD/{_ref(r, 4)}/{merchant}/{city}/{_ref(r, 6)}"
    return f"ME DC SI {_ref(r, 6)} {merchant}"


def _merchant_names(cat: str, r: random.Random, stems: list[str]) -> str:
    known = MERCHANTS.get(cat, {})
    if known and r.random() < 0.3:
        name = r.choice(list(known.keys()))
        alias = r.choice(known[name])
        return r.choice([name, alias]).upper().strip()
    suffix = r.choice(BUSINESS[cat])
    return f"{r.choice(stems)} {suffix}"


def generate(n: int = 24000, seed: int = 7, split: str = "train") -> list[Example]:
    r = random.Random(seed)
    # disjoint name pools: test-time names never appear in training
    def part(seq, frac=0.8):
        k = int(len(seq) * frac)
        return (seq[:k], seq[k:]) if split == "train" else (seq[k:], seq[:k])
    first, _ = part(FIRST)
    last, _ = part(LAST)
    stems, _ = part(STEMS)
    companies, _ = part(COMPANIES)

    out: list[Example] = []
    merchant_cats = list(BUSINESS.keys())

    def add(text, debit, amount, stype, label):
        if r.random() < 0.15:
            text = text.title() if r.random() < 0.5 else text.lower()
        out.append(Example(text, debit, amount, stype, label))

    while len(out) < n:
        k = r.random()
        stype = "credit_card" if r.random() < 0.2 else "bank_account"
        if k < 0.5:  # merchant spend via UPI / card / netbanking
            cat = r.choice(merchant_cats)
            m = _merchant_names(cat, r, stems)
            amt = _amount(r, 20, 4000 if cat in ("food", "groceries", "fuel") else 25000)
            if stype == "credit_card" or r.random() < 0.35:
                text = _card_spend(r, m, stype)
            else:
                vpa = f"{m.lower().replace(' ', '')[:10]}@{r.choice(['ybl', 'paytm', 'okaxis', 'icici', 'hdfcbank'])}"
                if r.random() < 0.3:
                    vpa = f"paytmqr{_ref(r, 6)}@paytm"
                text = _upi(r, m, True, vpa)
            add(text, True, amt, stype, cat)
        elif k < 0.62:  # P2P transfers
            name = _person(r, first, last)
            debit = r.random() < 0.55
            ch = r.random()
            if ch < 0.55:
                text = _upi(r, name, debit)
            elif ch < 0.7:
                text = f"NEFT {'DR' if debit else 'CR'}-{r.choice(BANKS)}0{_ref(r, 6)}-{name}-NETBANK, {r.choice(CITIES)[:3]}-N{_ref(r, 15)}-PERSONAL"
            elif ch < 0.85:
                text = f"IMPS-{_ref(r)}-{name}-{r.choice(BANKS)}-XXXXXXX{_ref(r, 4)}-{r.choice(['PERSONAL', 'FAMILY', 'GIFT', 'LOAN', 'NA'])}"
            else:
                text = f"{'TO' if debit else 'BY'} TRANSFER-INB {r.choice(['IMPS', 'NEFT', ''])}{_ref(r)}/{name}-"
            add(text, debit, _amount(r, 50, 60000), "bank_account", "transfer_out" if debit else "transfer_in")
        elif k < 0.67:  # salary
            co = r.choice(companies)
            mon = r.choice(MONTHS)
            t = r.choice([
                f"NEFT CR-{r.choice(BANKS)}0{_ref(r, 6)}-{co} PVT LTD-SALARY {mon}",
                f"SALARY CREDIT {mon} {r.choice(['2023', '2024', '2025'])} {co}",
                f"BY TRANSFER-NEFT*{r.choice(BANKS)}0{_ref(r, 6)}*{_ref(r)}*{co} SAL",
                f"N{r.choice(BANKS)}H{_ref(r, 11)} {r.choice(CITIES)}-{co}-SALARY",
                f"TRANSFER FROM SALARY", f"ACH C- {co} PAYROLL-{_ref(r, 8)}", f"{co} STIPEND {mon}",
            ])
            add(t, False, _amount(r, 15000, 250000), "bank_account", "salary")
        elif k < 0.70:
            t = r.choice(["CREDIT INTEREST--", "INT.PD:{}".format(_ref(r, 10)), "INTEREST CAPITALISED", "SB INT PAID",
                          "Int.Pd:{}:01-04-2024 to 30-06-2024".format(_ref(r, 10)), "FD INT CREDIT", "DIVIDEND {} LTD".format(r.choice(COMPANIES))])
            add(t, False, _amount(r, 5, 9000), "bank_account", "interest")
        elif k < 0.75:
            t = r.choice(["SMS CHARGES QTR", "ATM AMC CHARGES", "DEBIT CARD ANNUAL FEE", "MIN BAL CHGS", "GENERAL CHARGES RECOVERY",
                          "MCC ISSUE CHARGES--", "CROSS CURRENCY FEE", "OVERLIMIT FEE", "LATE PAYMENT FEE", "FINANCE CHARGES",
                          "IGST-VPS{}-RATE 18.0".format(_ref(r, 10)), "GST ON CHARGES", "CONSOLIDATED CHARGES FOR A/C",
                          "NEFT CHGS INCL GST", "CHQ BOOK ISSUE CHARGES", "IMPS CHARGES", "MARKUP FEE"])
            add(t, True, _amount(r, 1, 1500), stype, "charges")
        elif k < 0.80:
            t = r.choice(["ATM WDL ATM CASH {} {} {}".format(_ref(r, 4), r.choice(STEMS), r.choice(CITIES)),
                          "NFS/CASH WDL/{}/{}/{}".format(_ref(r), _ref(r, 8), r.choice(CITIES)),
                          "ATM/{}/CASH WDL/{}".format(_ref(r, 8), "12-10-23"), "CASH WITHDRAWAL BY CHEQUE-{}".format(_ref(r, 6)),
                          "CAM/{}/CASH WDL".format(_ref(r, 8)), "ATMWDL ATMCASH {} {}".format(_ref(r, 4), r.choice(CITIES))])
            add(t, True, float(r.choice([500, 1000, 2000, 2500, 5000, 10000, 20000])), "bank_account", "cash_withdrawal")
        elif k < 0.83:
            t = r.choice(["CASH DEPOSIT BY SELF", "BY CASH {}".format(r.choice(CITIES)), "CASH DEP {} BRANCH".format(r.choice(CITIES)),
                          "MICRO ATM CASH DEP - {}".format(r.choice(BANKS)), "CDM CASH DEPOSIT {}".format(_ref(r, 6))])
            add(t, False, _amount(r, 500, 50000), "bank_account", "cash_deposit")
        elif k < 0.87:
            lender = r.choice(list(MERCHANTS["loan"].keys())).upper() if r.random() < 0.5 else f"{r.choice(stems)} {r.choice(BUSINESS['loan'])}"
            t = r.choice([f"ACH D- {lender}-{_ref(r, 10)}", f"EMI {_ref(r, 7)} CHQ S{_ref(r, 11)}", f"NACH DR {lender} {_ref(r, 8)}",
                          f"LOAN REPAYMENT {lender}", f"ECS/{lender}/{_ref(r, 8)}", f"TO TRANSFER-HOUSING LOAN EMI-{_ref(r, 11)}"])
            add(t, True, _amount(r, 1000, 60000), "bank_account", "loan")
        elif k < 0.90:
            biller = r.choice(list(MERCHANTS["utilities"].keys())).upper()
            t = r.choice([f"BIL/BPAY/{_ref(r)}/{biller}", f"IB BILLPAY DR-{biller[:8]}-{_ref(r, 10)}",
                          f"NHDF{_ref(r, 10)}/BILLDK{biller.replace(' ', '')[:12]}", f"RECHARGE {biller} {_ref(r, 10)}",
                          f"UPI/DR/{_ref(r)}/{biller}/UTIB/{biller.lower().replace(' ', '')[:8]}@axisbank/bill"])
            add(t, True, _amount(r, 99, 6000), "bank_account", "utilities")
        elif k < 0.92:
            t = r.choice(["REV-IMPS-{}-{}".format(_ref(r), _person(r, first, last)), "NFS/CASH WDL RVSL/{}".format(_ref(r)),
                          "REFUND {}".format(r.choice(["AMAZON", "FLIPKART", "MYNTRA", "IRCTC", "SWIGGY"])),
                          "{} CASHBACK".format(r.choice(["PAYTM", "AMAZON PAY", "CRED"])), "UPI REVERSAL {}".format(_ref(r)),
                          "ITD TAX REFUND AY 23-24 PAN XXXXX{}X".format(_ref(r, 4))])
            add(t, False, _amount(r, 10, 20000), stype, "refund")
        elif k < 0.94:
            t = r.choice(["PAYMENT RECEIVED - THANK YOU", "NEFT PAYMENT RECEIVED", "BBPS PAYMENT RECEIVED", "AUTOPAY PAYMENT",
                          "UPI PAYMENT RECEIVED THANK YOU", "ONLINE PAYMENT RECEIVED"])
            add(t, False, _amount(r, 500, 90000), "credit_card", "card_payment")
            t2 = r.choice(["CRED CLUB {}".format(_ref(r, 6)), "BILLDKKOTAKCARDS", "NHDF{}/SBI CARDS".format(_ref(r, 10)),
                           "IB BILLPAY DR-HDFCPE-{}XXXXXX{}".format(_ref(r, 6), _ref(r, 4)), "CREDIT CARD PAYMENT {}".format(_ref(r, 4))])
            add(t2, True, _amount(r, 500, 90000), "bank_account", "card_payment")
        elif k < 0.96:
            t = r.choice(["ADD MONEY TO WALLET PAYTM", "ONE MOBIKWIK GURGAON", "MOBIKWIKUPI CHENNAI", "PAYTM NOIDA", "AMAZON PAY BALANCE TOPUP",
                          "PHONEPE WALLET LOAD", "FREECHARGE WALLET"])
            add(t, True, _amount(r, 50, 10000), stype, "wallet")
        elif k < 0.98:
            t = r.choice(["DTAX {}".format(_ref(r, 10)), "ADVANCE TAX CHALLAN {}".format(_ref(r, 8)), "TIN NSDL INCOME TAX",
                          "GST PAYMENT CBIC {}".format(_ref(r, 8)), "TDS PAYMENT {}".format(_ref(r, 6)), "PROFESSION TAX MCGM"])
            add(t, True, _amount(r, 200, 80000), "bank_account", "tax")
        else:
            inv = r.choice(list(MERCHANTS["investment"].keys())).upper()
            t = r.choice([f"ACH D- {inv}-{_ref(r, 10)}", f"SIP {inv} {_ref(r, 8)}", f"BSE STAR MF {_ref(r, 8)}",
                          f"TO RD A/C {_ref(r, 10)}", f"UPI/DR/{_ref(r)}/{inv}/HDFC/{inv.lower()[:8]}@hdfcbank/SIP"])
            add(t, True, _amount(r, 500, 50000), "bank_account", "investment")
    r.shuffle(out)
    return out[:n]
