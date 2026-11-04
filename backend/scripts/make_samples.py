"""Generate synthetic sample statements (+ exact ground truth) for the demo and tests.

All banks, people and account numbers are fictional. Variants exercise the edge
cases the pipeline is built for:
Written to tests/data/synthetic_pdfs (test fixtures; the app's demo samples live in samples/).
  aurora_savings.pdf          text PDF, 3 pages, wrapped narrations, repeated headers, B/F row
  aurora_savings_scanned.pdf  the same statement as a skewed, noisy ~110-DPI scan (OCR path)
  nimbus_protected.pdf        password "demo1234", newest-first, single Amount column with (Dr)/(Cr)
  nimbus_card.pdf             credit-card statement: summary tiles, Cr suffix for payments/refunds
"""
from __future__ import annotations

import json
import random
import zlib
import sys
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "data" / "synthetic_pdfs"
TRUTH = ROOT / "tests" / "data" / "synthetic"


def inr(v: float) -> str:
    """Indian digit grouping: 1,23,456.78"""
    neg = v < 0
    s = f"{abs(v):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + "." + frac


def ref(r: random.Random, n: int = 12) -> str:
    return "".join(r.choice("0123456789") for _ in range(n))


def bank_transactions(seed: int = 3) -> tuple[float, list[dict]]:
    r = random.Random(seed)
    opening = 48_250.75
    rows: list[dict] = []
    start = date(2025, 4, 1)
    friends = ["KARTIK MENON", "SNEHA IYER", "ROHAN DESAI", "ANANYA RAO"]
    for month in range(3):
        m0 = date(2025, 4 + month, 1)
        def d(day): return m0.replace(day=min(day, 28))
        rows += [
            {"date": d(1), "desc": f"NEFT CR-CITI0000001-ORBITAL SYSTEMS PVT LTD-SALARY {m0:%b %Y}".upper(), "credit": 92_500.00, "cat": "salary"},
            {"date": d(2), "desc": f"UPI/DR/{ref(r)}/RAMESH KUMAR/SBIN/rameshk@oksbi/Rent {m0:%b}", "debit": 22_000.00, "cat": "transfer_out"},
            {"date": d(5), "desc": f"ACH D- BRIGHTPATH FINANCE LTD-{ref(r, 10)}", "debit": 8_450.00, "cat": "loan"},
            {"date": d(7), "desc": f"ACH D- KUVERA MUTUAL FUND SIP-{ref(r, 9)}", "debit": 5_000.00, "cat": "investment"},
            {"date": d(9), "desc": f"POS 512345XXXXXX4321 NETFLIX.COM MUMBAI", "debit": 649.00, "cat": "entertainment"},
            {"date": d(11), "desc": f"BIL/BPAY/{ref(r)}/TATA POWER MUMBAI/ELECTRICITY", "debit": round(r.uniform(1400, 2600), 2), "cat": "utilities"},
            {"date": d(14), "desc": f"ATM WDL ATM CASH {ref(r, 4)} ANDHERI EAST MUMBAI", "debit": 5_000.00, "cat": "cash_withdrawal"},
        ]
        for _ in range(r.randint(5, 8)):
            day = r.randint(1, 28)
            kind = r.random()
            if kind < 0.3:
                m = r.choice(["SWIGGY", "ZOMATO"])
                rows.append({"date": d(day), "desc": f"UPI/DR/{ref(r)}/{m}/YESB/{m.lower()}@ybl/Payment for order", "debit": round(r.uniform(180, 950), 2), "cat": "food"})
            elif kind < 0.5:
                m = r.choice(["BLINKIT", "ZEPTO", "SHREE GANESH KIRANA STORE"])
                rows.append({"date": d(day), "desc": f"UPI/DR/{ref(r)}/{m}/ICIC/{m.split()[0].lower()}@icici/groceries", "debit": round(r.uniform(300, 2400), 2), "cat": "groceries"})
            elif kind < 0.62:
                rows.append({"date": d(day), "desc": f"POS 512345XXXXXX4321 INDIAN OIL PETROL PUMP ANDHERI", "debit": round(r.uniform(1500, 3200), 2), "cat": "fuel"})
            elif kind < 0.74:
                rows.append({"date": d(day), "desc": f"UPI/DR/{ref(r)}/UBER INDIA/UTIB/uber.rides@axisbank/Trip", "debit": round(r.uniform(150, 700), 2), "cat": "travel"})
            elif kind < 0.86:
                rows.append({"date": d(day), "desc": f"POS 512345XXXXXX4321 AMAZON SELLER SERVICES BANGALORE", "debit": round(r.uniform(400, 6000), 2), "cat": "shopping"})
            else:
                f = r.choice(friends)
                debit = r.random() < 0.6
                key = "debit" if debit else "credit"
                rows.append({"date": d(day), "desc": f"IMPS-{ref(r)}-{f}-HDFC-XXXXXXX{ref(r, 4)}-{'DINNER SPLIT' if debit else 'RETURNED'}",
                             key: float(r.choice([500, 750, 1200, 2000])), "cat": "transfer_out" if debit else "transfer_in"})
    rows.append({"date": date(2025, 6, 30), "desc": "CREDIT INTEREST CAPITALISED", "credit": 412.00, "cat": "interest"})
    rows.append({"date": date(2025, 6, 30), "desc": "SMS CHARGES FOR APR-JUN 2025 QTR", "debit": 17.70, "cat": "charges"})
    rows.append({"date": date(2025, 5, 18), "desc": f"REV-UPI/{ref(r)}/ZEPTO/REFUND FOR CANCELLED ORDER", "credit": 640.00, "cat": "refund"})
    rows.sort(key=lambda x: x["date"])
    bal = opening
    for x in rows:
        bal = round(bal + x.get("credit", 0) - x.get("debit", 0), 2)
        x["balance"] = bal
    return opening, rows


def wrap(text: str, width: int) -> list[str]:
    out, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= width:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def draw_bank(opening: float, rows: list[dict]) -> pymupdf.Document:
    doc = pymupdf.open()
    W, H = 595, 842
    cols = [("Txn Date", 36, 92), ("Particulars", 92, 262), ("Ref No.", 262, 330), ("Debit", 330, 400),
            ("Credit", 400, 470), ("Balance", 470, 560)]
    fs = 7.6
    lh = 9.6

    def header(page, first: bool):
        page.draw_rect(pymupdf.Rect(36, 30, 560, 62), color=None, fill=(0.17, 0.2, 0.45))
        page.insert_text((46, 52), "AURORA BANK", fontsize=16, fontname="hebo", color=(1, 1, 1))
        page.insert_text((420, 50), "Statement of Account", fontsize=10, fontname="helv", color=(1, 1, 1))
        y = 80
        if first:
            left = [("Account Name", "Ms. Priya Venkataraman"), ("Address", "Flat 12B, Lotus Residency, Andheri East"),
                    ("", "Mumbai 400069"), ("Email", "priya.v@example.com")]
            right = [("Account Number", "50200012345678"), ("IFSC Code", "AURB0001234"), ("Branch", "ANDHERI EAST"),
                     ("Customer ID", "88412365"), ("Account Type", "SAVINGS - REGULAR"), ("Currency", "INR")]
            for i, (k, v) in enumerate(left):
                page.insert_text((40, y + i * 12), k, fontsize=8, fontname="helv", color=(0.35, 0.35, 0.4))
                page.insert_text((115, y + i * 12), (": " if k else "  ") + v, fontsize=8, fontname="helv")
            for i, (k, v) in enumerate(right):
                page.insert_text((330, y + i * 12), k, fontsize=8, fontname="helv", color=(0.35, 0.35, 0.4))
                page.insert_text((420, y + i * 12), ": " + v, fontsize=8, fontname="helv")
            y += 6 * 12 + 6
            page.insert_text((40, y), f"Statement Period : 01-Apr-2025 To 30-Jun-2025", fontsize=8.5, fontname="hebo")
            y += 14
        top = y
        page.draw_rect(pymupdf.Rect(36, top, 560, top + 16), color=None, fill=(0.9, 0.91, 0.96))
        for name, x0, x1 in cols:
            tx = x0 + 3 if name in ("Txn Date", "Particulars", "Ref No.") else x1 - 3 - pymupdf.get_text_length(name, "hebo", 8)
            page.insert_text((tx, top + 11), name, fontsize=8, fontname="hebo")
        return top + 16

    page = doc.new_page(width=W, height=H)
    y = header(page, True)
    pages = [page]

    def row_line(page, y):
        page.draw_line((36, y), (560, y), color=(0.85, 0.86, 0.9), width=0.5)

    page.insert_text((39, y + 10), "01-Apr-2025", fontsize=fs, fontname="helv")
    page.insert_text((95, y + 10), "B/F OPENING BALANCE", fontsize=fs, fontname="helv")
    b = inr(opening)
    page.insert_text((557 - pymupdf.get_text_length(b, "helv", fs), y + 10), b, fontsize=fs, fontname="helv")
    y += 14
    row_line(page, y)
    for x in rows:
        lines = wrap(x["desc"], 34)
        need = len(lines) * lh + 5
        if y + need > H - 60:
            page = doc.new_page(width=W, height=H)
            pages.append(page)
            y = header(page, False)
        x["page"] = len(pages) - 1
        base = y + 10
        page.insert_text((39, base), x["date"].strftime("%d-%b-%Y"), fontsize=fs, fontname="helv")
        for i, ln in enumerate(lines):
            page.insert_text((95, base + i * lh), ln, fontsize=fs, fontname="helv")
        rf = x.get("ref") or ref(random.Random(zlib.crc32(x["desc"].encode())), 10)
        page.insert_text((265, base), rf, fontsize=fs - 0.6, fontname="helv")
        for key, x1 in (("debit", 397), ("credit", 467)):
            if x.get(key):
                t = inr(x[key])
                page.insert_text((x1 - pymupdf.get_text_length(t, "helv", fs), base), t, fontsize=fs, fontname="helv")
        t = inr(x["balance"])
        page.insert_text((557 - pymupdf.get_text_length(t, "helv", fs), base), t, fontsize=fs, fontname="helv")
        y += need
        row_line(page, y)
    for i in range(doc.page_count):
        p = doc[i]
        p.insert_text((260, H - 30), f"Page {i + 1} of {len(pages)}", fontsize=7.5, fontname="helv", color=(0.4, 0.4, 0.45))
        p.insert_text((36, H - 18), "This is a computer generated statement and does not require a signature. Aurora Bank is fictional.",
                      fontsize=6.5, fontname="helv", color=(0.5, 0.5, 0.55))
    return doc


def scanned_copy(doc: pymupdf.Document, seed: int = 5) -> pymupdf.Document:
    r = np.random.default_rng(seed)
    out = pymupdf.open()
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
        h, w = img.shape
        angle = [0.9, -0.6, 0.4][i % 3]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(img, m, (w, h), borderValue=255)
        img = cv2.GaussianBlur(img, (3, 3), 0.6)
        noise = r.normal(0, 9, img.shape)
        img = np.clip(img.astype(float) + noise, 0, 255).astype(np.uint8)
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=jpg.tobytes())
    return out


def draw_union_style(opening: float, rows: list[dict]) -> pymupdf.Document:
    """Newest-first, single Amount column with (Dr)/(Cr) suffix — like several PSU banks."""
    doc = pymupdf.open()
    W, H = 595, 842
    page = doc.new_page(width=W, height=H)
    page.insert_text((40, 50), "NIMBUS CO-OPERATIVE BANK", fontsize=15, fontname="hebo", color=(0.05, 0.35, 0.3))
    page.insert_text((40, 66), "DETAILS OF STATEMENT", fontsize=9, fontname="hebo")
    info = [("Name", "ARJUN MEHTA"), ("Account Number", "6100 2233 4455 66".replace(" ", "")), ("IFSC", "NMBS0004411"),
            ("Customer/CIF ID", "551200877"), ("Account Type", "Savings Account"), ("Currency", "INR")]
    for i, (k, v) in enumerate(info):
        page.insert_text((40, 86 + i * 12), f"{k}", fontsize=8, fontname="helv")
        page.insert_text((140, 86 + i * 12), f": {v}", fontsize=8, fontname="helv")
    page.insert_text((40, 166), "Statement Period From - 01/04/2025 To 30/06/2025", fontsize=8.5, fontname="helv")
    cols = [("Tran Id", 40, 105), ("Tran Date", 105, 170), ("Remarks", 170, 380), ("Amount (Rs.)", 380, 470), ("Balance (Rs.)", 470, 555)]
    y = 182
    pages = [page]

    def hdr(page, y):
        for name, x0, x1 in cols:
            page.insert_text((x0 + 2, y + 10), name, fontsize=8, fontname="hebo")
        page.draw_line((40, y + 14), (555, y + 14), color=(0, 0, 0), width=0.6)
        return y + 18

    y = hdr(page, y)
    r = random.Random(11)
    for x in reversed(rows):
        lines = wrap(x["desc"], 40)
        need = len(lines) * 9.5 + 6
        if y + need > H - 50:
            page = doc.new_page(width=W, height=H)
            pages.append(page)
            y = hdr(page, 40)
        base = y + 9
        page.insert_text((42, base), f"S{ref(r, 8)}", fontsize=7.4, fontname="helv")
        page.insert_text((107, base), x["date"].strftime("%d/%m/%Y"), fontsize=7.4, fontname="helv")
        for i, ln in enumerate(lines):
            page.insert_text((172, base + i * 9.5), ln, fontsize=7.4, fontname="helv")
        amt = f"{x.get('debit') or x.get('credit'):.2f} ({'Dr' if x.get('debit') else 'Cr'})"
        page.insert_text((467 - pymupdf.get_text_length(amt, "helv", 7.4), base), amt, fontsize=7.4, fontname="helv")
        b = f"{x['balance']:.2f}"
        page.insert_text((552 - pymupdf.get_text_length(b, "helv", 7.4), base), b, fontsize=7.4, fontname="helv")
        y += need
    for i in range(doc.page_count):
        p = doc[i]
        p.insert_text((480, H - 25), f"Page {i + 1} of {len(pages)}", fontsize=7, fontname="helv")
    return doc


def card_statement() -> tuple[pymupdf.Document, dict]:
    r = random.Random(21)
    prev = 18_420.50
    rows = [
        {"date": date(2025, 5, 22), "desc": "PAYMENT RECEIVED - THANK YOU", "credit": 18_420.50, "cat": "card_payment"},
        {"date": date(2025, 5, 24), "desc": "MAKEMYTRIP INDIA PVT LTD NEW DELHI", "debit": 12_640.00, "cat": "travel"},
        {"date": date(2025, 5, 25), "desc": "SWIGGY BANGALORE", "debit": 486.00, "cat": "food"},
        {"date": date(2025, 5, 27), "desc": "AMAZON.IN BANGALORE", "debit": 3_299.00, "cat": "shopping"},
        {"date": date(2025, 5, 30), "desc": "SPOTIFY INDIA MUMBAI", "debit": 119.00, "cat": "entertainment"},
        {"date": date(2025, 6, 2), "desc": "HPCL FUEL STATION PUNE", "debit": 2_850.00, "cat": "fuel"},
        {"date": date(2025, 6, 4), "desc": "AMAZON.IN BANGALORE REFUND", "credit": 899.00, "cat": "refund"},
        {"date": date(2025, 6, 8), "desc": "APOLLO PHARMACY PUNE", "debit": 1_145.60, "cat": "health"},
        {"date": date(2025, 6, 12), "desc": "BOOKMYSHOW MUMBAI", "debit": 920.00, "cat": "entertainment"},
        {"date": date(2025, 6, 15), "desc": "BIGBASKET BANGALORE", "debit": 2_310.40, "cat": "groceries"},
        {"date": date(2025, 6, 18), "desc": "FINANCE CHARGES", "debit": 0.0, "cat": "charges"},
        {"date": date(2025, 6, 20), "desc": "GST ON CHARGES", "debit": 0.0, "cat": "charges"},
    ]
    rows = [x for x in rows if x.get("debit", 1) != 0.0]
    debits = round(sum(x.get("debit", 0) for x in rows), 2)
    credits = round(sum(x.get("credit", 0) for x in rows), 2)
    total = round(prev + debits - credits, 2)
    minimum = round(max(200, total * 0.05), 2)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(30, 28, 565, 70), color=None, fill=(0.35, 0.12, 0.45))
    page.insert_text((44, 55), "NIMBUS PLATINUM CREDIT CARD", fontsize=14, fontname="hebo", color=(1, 1, 1))
    page.insert_text((400, 54), "Credit Card Statement", fontsize=10, fontname="helv", color=(1, 1, 1))
    page.insert_text((40, 92), "Card Holder Name : ROHIT KULKARNI", fontsize=8.5, fontname="helv")
    page.insert_text((40, 105), "Card No : 4567 89XX XXXX 1234", fontsize=8.5, fontname="helv")
    tiles = [("Statement Date", "20/06/2025"), ("Statement Period", "21/05/2025 - 20/06/2025"), ("Payment Due Date", "10/07/2025"),
             ("Credit Limit", "2,00,000.00")]
    tiles2 = [("Previous Balance", inr(prev)), ("Payments/Credits", inr(credits)), ("Purchases/Debits", inr(debits)),
              ("Total Amount Due", inr(total)), ("Minimum Amount Due", inr(minimum))]
    for row_i, ts in enumerate((tiles, tiles2)):
        w = 525 / len(ts)
        for i, (k, v) in enumerate(ts):
            x0 = 35 + i * w
            y0 = 122 + row_i * 44
            page.draw_rect(pymupdf.Rect(x0, y0, x0 + w - 6, y0 + 36), color=(0.75, 0.7, 0.8), width=0.6)
            page.insert_text((x0 + 6, y0 + 13), k, fontsize=7.6, fontname="helv", color=(0.35, 0.3, 0.4))
            page.insert_text((x0 + 6, y0 + 28), v, fontsize=8.6, fontname="hebo")
    y = 230
    page.insert_text((40, y), "Date", fontsize=8.5, fontname="hebo")
    page.insert_text((120, y), "Transaction Details", fontsize=8.5, fontname="hebo")
    page.insert_text((470, y), "Amount (Rs.)", fontsize=8.5, fontname="hebo")
    page.draw_line((36, y + 5), (560, y + 5), color=(0.3, 0.3, 0.3), width=0.6)
    y += 20
    for x in rows:
        page.insert_text((40, y), x["date"].strftime("%d/%m/%Y"), fontsize=8, fontname="helv")
        page.insert_text((120, y), x["desc"], fontsize=8, fontname="helv")
        amt = inr(x.get("debit") or x.get("credit")) + (" Cr" if x.get("credit") else "")
        page.insert_text((540 - pymupdf.get_text_length(amt, "helv", 8), y), amt, fontsize=8, fontname="helv")
        y += 15
    page.insert_text((40, 800), "Nimbus Bank is fictional. Generated for demonstration.", fontsize=6.5, fontname="helv", color=(0.5, 0.5, 0.5))
    truth = {"statement_type": "credit_card", "opening_balance": prev, "total_due": total, "minimum_due": minimum,
             "card_number": "4567 89XX XXXX 1234", "account_holder": "Rohit Kulkarni",
             "transactions": [{"date": x["date"].isoformat(), "description": x["desc"], "debit": x.get("debit"),
                               "credit": x.get("credit"), "balance": None, "category": x["cat"]} for x in rows]}
    return doc, truth


def main() -> None:
    OUT.mkdir(exist_ok=True)
    TRUTH.mkdir(parents=True, exist_ok=True)
    opening, rows = bank_transactions()
    truth_rows = [{"date": x["date"].isoformat(), "description": x["desc"], "debit": x.get("debit"), "credit": x.get("credit"),
                   "balance": x["balance"], "category": x["cat"]} for x in rows]
    base_truth = {"statement_type": "bank_account", "opening_balance": opening, "closing_balance": rows[-1]["balance"],
                  "account_number": "50200012345678", "ifsc": "AURB0001234", "account_holder": "Ms. Priya Venkataraman",
                  "transactions": truth_rows}

    doc = draw_bank(opening, rows)
    doc.save(OUT / "aurora_savings.pdf", garbage=3, deflate=True)
    (TRUTH / "aurora_savings.json").write_text(json.dumps(base_truth, indent=1))
    scanned_copy(doc).save(OUT / "aurora_savings_scanned.pdf", garbage=3, deflate=True)
    (TRUTH / "aurora_savings_scanned.json").write_text(json.dumps(base_truth, indent=1))

    nim = draw_union_style(opening, rows)
    nim.save(OUT / "nimbus_protected.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="demo1234", owner_pw="owner-demo")
    t2 = dict(base_truth, account_number="61002233445566", ifsc="NMBS0004411", account_holder="Arjun Mehta")
    (TRUTH / "nimbus_protected.json").write_text(json.dumps(t2, indent=1))

    card, ct = card_statement()
    card.save(OUT / "nimbus_card.pdf", garbage=3, deflate=True)
    (TRUTH / "nimbus_card.json").write_text(json.dumps(ct, indent=1))

    print(f"wrote 4 samples to {OUT}; {len(rows)} bank rows; card total due {ct['total_due']}")


if __name__ == "__main__":
    sys.exit(main())
