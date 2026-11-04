"""Layout fuzzer: random bank-statement PDFs with exact ground truth.

Each layout varies what real banks vary (header wording incl. bilingual Hindi,
column order/presence, debit/credit encoding, date & number formats, rules,
header style, wrapping, order, page breaks). Running hundreds of them shows
whether the extractor generalises beyond the handful of real samples.

Usage:
  python scripts/layout_fuzz.py 300            # run 300 layouts, print failures
  python scripts/layout_fuzz.py 1 --seed 42 --keep out/   # write one PDF to inspect
"""
from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

NOTO = None  # a font with Devanagari, for bilingual headers (optional)
for cand in ("/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc", "/System/Library/Fonts/Kohinoor.ttc",
             "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"):
    if Path(cand).exists():
        NOTO = cand
        break

HEAD = {
    "date": ["Date", "Txn Date", "Tran Date", "Transaction Date", "Post Date", "Posting Date", "Trans. Date", "Book Date", "Entry Date", "Txn. Dt."],
    "value_date": ["Value Date", "Value Dt", "Val Date", "Value\nDate"],
    "description": ["Description", "Narration", "Particulars", "Transaction Details", "Remarks", "Details", "Transaction Remarks",
                    "Narrative", "Description/Narration", "Transaction Particulars"],
    "ref": ["Chq/Ref No", "Ref No.", "Cheque No.", "Chq. No.", "Reference", "Instrument No", "Ref No./Cheque No.", "UTR / Ref"],
    "debit": ["Debit", "Withdrawal", "Withdrawals", "Withdrawal Amt.", "Debit Amount", "Dr Amount", "Withdrawal (Dr)", "Paid Out", "Debits"],
    "credit": ["Credit", "Deposit", "Deposits", "Deposit Amt.", "Credit Amount", "Cr Amount", "Deposit (Cr)", "Paid In", "Credits"],
    "amount": ["Amount", "Amount (Rs.)", "Txn Amount", "Transaction Amount", "Amt (INR)", "Amount (INR)"],
    "crdr": ["Dr/Cr", "Cr/Dr", "Type", "DR/CR", "D/C"],
    "balance": ["Balance", "Closing Balance", "Running Balance", "Balance (INR)", "Available Balance", "Balance (Rs.)"],
    "serial": ["S.No", "Sl No", "#", "Sr. No."],
}
HINDI = {"date": "दिनांक", "description": "विवरण", "debit": "नामे", "credit": "जमा", "balance": "शेष", "amount": "राशि",
         "ref": "संदर्भ", "value_date": "मूल्य दिनांक"}
DATE_FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y", "%d-%b-%y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %y", "%m/%d/%Y"]
SCHEMES = ["dr_cr_cols", "amount_crdr_col", "amount_suffix", "signed_amount", "dr_cr_no_balance", "amount_suffix_bal_suffix"]
NARR = ["UPI/DR/{r}/{n}/{b}/{v}@okaxis/Payment", "NEFT CR-{b}0001234-{n}-SALARY", "IMPS-{r}-{n}-{b}-XXXX1234-PERSONAL",
        "POS 512345XXXXXX4321 {m} {c}", "ACH D- {m} FINANCE LTD-{r}", "ATM WDL {c} ATM {r}", "BIL/BPAY/{r}/{m} POWER",
        "BY TRANSFER-INB {n}", "TO TRANSFER-{m} LOAN EMI", "CHQ DEP {r} {b} BRANCH", "INT.PD:{r}", "SMS CHARGES QTR",
        "UPI-{n}-{v}@ybl-{b}0009999-{r}-GROCERIES {m} MART", "Purchase at {m} {c} via debit card ending 4321"]
NAMES = ["RAHUL SHARMA", "PRIYA NAIR", "ANKIT GUPTA", "MEERA IYER", "ARJUN MEHTA", "KAVYA REDDY", "ROHIT DAS"]
MERCH = ["SWIGGY", "BLINKIT", "AMAZON", "SHREE BALAJI", "TATA", "RELIANCE", "INDIAN OIL", "APOLLO", "ZOMATO"]
CITIES = ["MUMBAI", "PUNE", "DELHI", "CHENNAI", "BENGALURU"]
BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK"]


@dataclass
class Layout:
    seed: int
    date_fmt: str
    scheme: str
    cols: list[str]
    labels: dict[str, str]
    bilingual: bool
    rules: str            # none | hlines | grid | zebra
    header_fill: bool
    stacked_header: bool
    grouping: str         # indian | western | none
    prefix: str           # "" | "Rs. " | "INR "
    blank: str            # "" | "-" | "0.00"
    font_size: float
    desc_width: int
    descending: bool
    opening_row: str | None
    repeat_header: bool
    num_align: str        # right | center
    rows_per_page: int
    notes: list[str] = field(default_factory=list)


def rnd_layout(seed: int) -> Layout:
    r = random.Random(seed)
    scheme = r.choice(SCHEMES)
    money = {"dr_cr_cols": ["debit", "credit", "balance"], "amount_crdr_col": ["amount", "crdr", "balance"],
             "amount_suffix": ["amount", "balance"], "signed_amount": ["amount", "balance"],
             "dr_cr_no_balance": ["debit", "credit"], "amount_suffix_bal_suffix": ["amount", "balance"]}[scheme]
    text = ["description"]
    if r.random() < 0.6:
        text.insert(r.choice([0, 1]), "ref")
    front = ["date"] + (["value_date"] if r.random() < 0.35 else [])
    cols = (["serial"] if r.random() < 0.2 else []) + front + text + money
    labels = {c: r.choice(HEAD[c]) for c in cols}
    return Layout(
        seed=seed, date_fmt=r.choice(DATE_FMTS), scheme=scheme, cols=cols, labels=labels,
        bilingual=bool(NOTO) and r.random() < 0.2, rules=r.choice(["none", "hlines", "grid", "zebra"]),
        header_fill=r.random() < 0.5, stacked_header=r.random() < 0.3, grouping=r.choice(["indian", "indian", "western", "none"]),
        prefix=r.choice(["", "", "", "Rs. ", "INR "]), blank=r.choice(["", "", "-", "0.00"]), font_size=r.choice([7.2, 7.8, 8.4, 9.0]),
        desc_width=r.choice([22, 28, 34, 46]), descending=r.random() < 0.2,
        opening_row=r.choice([None, None, "Opening Balance", "B/F", "BALANCE BROUGHT FORWARD"]),
        repeat_header=r.random() < 0.8, num_align=r.choice(["right", "right", "center"]), rows_per_page=r.choice([14, 20, 26, 40]),
    )


def fmt_num(v: float, g: str) -> str:
    s = f"{abs(v):.2f}"
    whole, frac = s.split(".")
    if g == "western":
        whole = f"{int(whole):,}"
    elif g == "indian" and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{whole}.{frac}"


def make_txns(r: random.Random, n: int) -> tuple[float, list[dict]]:
    bal = round(r.uniform(5000, 90000), 2)
    opening = bal
    d = date(2025, r.randint(1, 6), r.randint(1, 20))
    out = []
    for i in range(n):
        d += timedelta(days=r.choice([0, 0, 1, 1, 2, 3]))
        credit = r.random() < 0.3
        amt = round(r.choice([r.uniform(20, 2000), r.uniform(500, 30000)]), 2)
        if not credit and amt > bal:
            credit = True
        bal = round(bal + (amt if credit else -amt), 2)
        desc = r.choice(NARR).format(r="".join(r.choice("0123456789") for _ in range(12)), n=r.choice(NAMES), b=r.choice(BANKS),
                                     v=r.choice(NAMES).split()[0].lower(), m=r.choice(MERCH), c=r.choice(CITIES))
        out.append({"date": d, "desc": desc, "debit": None if credit else amt, "credit": amt if credit else None, "balance": bal})
    return opening, out


def wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        while len(w) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:width])
            w = w[width:]
        if len(cur) + len(w) + (1 if cur else 0) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def wrap_pts(text: str, max_w: float, fs: float) -> list[str]:
    """Wrap by measured width (what a real PDF writer does), breaking long tokens."""
    lines, cur = [], ""
    for word in text.split(" "):
        cand = f"{cur} {word}".strip()
        if pymupdf.get_text_length(cand, "helv", fs) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = ""
        while pymupdf.get_text_length(word, "helv", fs) > max_w:
            k = len(word)
            while k > 1 and pymupdf.get_text_length(word[:k], "helv", fs) > max_w:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def render(lay: Layout, opening: float, txns: list[dict]) -> bytes:
    W, H = 595, 842
    fs = lay.font_size
    lh = fs * 1.3
    char_w = fs * 0.5
    # size columns to their content, like real statements do
    sample_date = date(2025, 12, 28).strftime(lay.date_fmt)
    num_w = pymupdf.get_text_length(lay.prefix + "1,23,456.78 Cr", "helv", fs) + 12
    widths = {"serial": pymupdf.get_text_length("999", "helv", fs) + 14,
              "date": pymupdf.get_text_length(sample_date, "helv", fs) + 12,
              "value_date": pymupdf.get_text_length(sample_date, "helv", fs) + 12,
              "ref": pymupdf.get_text_length("999999999", "helv", fs) + 14,
              "description": pymupdf.get_text_length("M" * lay.desc_width, "helv", fs) * 0.62 + 10,
              "debit": num_w, "credit": num_w, "amount": num_w, "crdr": pymupdf.get_text_length("DR/CR", "hebo", fs) + 10,
              "balance": num_w}
    total = sum(widths[c] for c in lay.cols)
    if total > W - 60 and fs > 5.6:
        # too wide: shrink the type (as banks do), never let columns overlap
        k = (W - 60) / total
        fs = max(5.5, fs * k)
        lay.font_size = fs
        lh = fs * 1.3
        return render(lay, opening, txns)
    scale = min(1.0, (W - 60) / total)
    xs, x = {}, 30.0
    for c in lay.cols:
        w = widths[c] * scale
        xs[c] = (x, x + w)
        x += w
    tx0, tx1 = 30, x
    doc = pymupdf.open()
    hindi_font = "hi" if lay.bilingual else None

    def new_page(first: bool):
        p = doc.new_page(width=W, height=H)
        if lay.bilingual:
            p.insert_font(fontname="hi", fontfile=NOTO)
        y = 40
        if first:
            p.insert_text((30, y), "MERIDIAN BANK LTD.", fontsize=13, fontname="hebo")
            info = [("Account Name", "MR. VIVEK SAXENA"), ("Account No", "60123498765432"), ("IFSC", "MERD0001122"),
                    ("Statement Period", f"{txns[0]['date']:%d/%m/%Y} to {txns[-1]['date']:%d/%m/%Y}")]
            for i, (k, v) in enumerate(info):
                p.insert_text((30, y + 18 + i * 11), f"{k} : {v}", fontsize=8, fontname="helv")
            y += 18 + len(info) * 11 + 10
        return p, y

    def header(p, y):
        hh = (fs + 4) * 2 + 4
        if lay.header_fill:
            p.draw_rect(pymupdf.Rect(tx0, y, tx1, y + hh), color=None, fill=(0.15, 0.3, 0.45))
        color = (1, 1, 1) if lay.header_fill else (0, 0, 0)
        for c in lay.cols:
            x0, x1 = xs[c]
            label = lay.labels[c]
            colw = x1 - x0 - 6
            if "\n" in label:
                parts = label.split("\n")
            elif (lay.stacked_header or pymupdf.get_text_length(label, "hebo", fs) > colw) and " " in label:
                parts = label.split(" ", 1)  # wrap long labels inside their column, as banks do
            else:
                parts = [label]
            for i, part in enumerate(parts[:2]):
                tw = pymupdf.get_text_length(part, "hebo", fs)
                px = x1 - 3 - tw if c in ("debit", "credit", "amount", "balance") and lay.num_align == "right" else x0 + 3
                p.insert_text((px, y + fs + 2 + i * (fs + 3)), part, fontsize=fs, fontname="hebo", color=color)
            if lay.bilingual and c in HINDI and len(parts) == 1:
                hw = pymupdf.Font(fontfile=NOTO).text_length(HINDI[c], fs - 0.5)
                hx = x1 - 3 - hw if c in ("debit", "credit", "amount", "balance") and lay.num_align == "right" else x0 + 3
                p.insert_text((hx, y + 2 * fs + 5), HINDI[c], fontsize=fs - 0.5, fontname=hindi_font, color=color)
        if lay.rules in ("hlines", "grid"):
            p.draw_line((tx0, y + hh), (tx1, y + hh), color=(0, 0, 0), width=0.6)
        return y + hh + 2

    def money(v, suffix=None):
        s = lay.prefix + fmt_num(v, lay.grouping)
        return s + (f" {suffix}" if suffix else "")

    p, y = new_page(True)
    y = header(p, y)
    rows = list(reversed(txns)) if lay.descending else txns
    if lay.opening_row and not lay.descending and "balance" in lay.cols:
        p.insert_text((xs["description"][0] + 3, y + fs), lay.opening_row, fontsize=fs, fontname="helv")
        if "balance" in xs:
            s = money(opening)
            p.insert_text((xs["balance"][1] - 3 - pymupdf.get_text_length(s, "helv", fs), y + fs), s, fontsize=fs, fontname="helv")
        y += lh + 4
    count = 0
    zebra = False
    for i, t in enumerate(rows):
        desc_lines = wrap_pts(t["desc"], xs["description"][1] - xs["description"][0] - 8, fs)
        rh = len(desc_lines) * lh + 4
        if y + rh > H - 50 or count >= lay.rows_per_page:
            p.insert_text((W / 2 - 20, H - 25), f"Page {doc.page_count} ", fontsize=7, fontname="helv")
            p, y = new_page(False)
            y = header(p, y) if lay.repeat_header else y
            count = 0
        count += 1
        if lay.rules == "zebra" and zebra:
            p.draw_rect(pymupdf.Rect(tx0, y - 1, tx1, y + rh - 1), color=None, fill=(0.94, 0.95, 0.97))
        zebra = not zebra
        base = y + fs
        vals: dict[str, str] = {"date": t["date"].strftime(lay.date_fmt), "value_date": t["date"].strftime(lay.date_fmt),
                                "serial": str(i + 1), "ref": "".join(random.Random(i).choice("0123456789") for _ in range(9))}
        amt = t["debit"] or t["credit"]
        isdr = t["debit"] is not None
        if lay.scheme in ("dr_cr_cols", "dr_cr_no_balance"):
            vals["debit"] = money(t["debit"]) if isdr else lay.blank
            vals["credit"] = money(t["credit"]) if not isdr else lay.blank
        elif lay.scheme == "amount_crdr_col":
            vals["amount"] = money(amt)
            vals["crdr"] = "Dr" if isdr else "Cr"
        elif lay.scheme in ("amount_suffix", "amount_suffix_bal_suffix"):
            vals["amount"] = money(amt, "Dr" if isdr else "Cr")
        elif lay.scheme == "signed_amount":
            vals["amount"] = ("-" if isdr else "") + money(amt)
        if "balance" in lay.cols:
            vals["balance"] = money(t["balance"], "Cr" if lay.scheme == "amount_suffix_bal_suffix" else None)
        for c in lay.cols:
            x0, x1 = xs[c]
            if c == "description":
                for k, ln in enumerate(desc_lines):
                    p.insert_text((x0 + 3, base + k * lh), ln, fontsize=fs, fontname="helv")
                continue
            s = vals.get(c, "")
            if not s:
                continue
            tw = pymupdf.get_text_length(s, "helv", fs)
            if c in ("debit", "credit", "amount", "balance"):
                px = x1 - 3 - tw if lay.num_align == "right" else (x0 + x1 - tw) / 2
            else:
                px = x0 + 3
            p.insert_text((px, base), s, fontsize=fs, fontname="helv")
        y += rh
        if lay.rules in ("hlines", "grid"):
            p.draw_line((tx0, y - 1), (tx1, y - 1), color=(0.7, 0.7, 0.7), width=0.4)
    p.insert_text((W / 2 - 20, H - 25), f"Page {doc.page_count} ", fontsize=7, fontname="helv")
    if lay.rules == "grid":
        for i in range(doc.page_count):
            pg = doc[i]
            for c in lay.cols:
                pg.draw_line((xs[c][0], 100 if i else 110), (xs[c][0], H - 60), color=(0.75, 0.75, 0.75), width=0.4)
    return doc.tobytes()


def to_scan(pdf: bytes, seed: int) -> bytes:
    """Degrade to a skewed, noisy ~110-DPI image-only PDF, like a phone/office scan."""
    from make_samples import scanned_copy
    return scanned_copy(pymupdf.open(stream=pdf), seed=seed).tobytes()


def check(seed: int, n_rows: int = 30, keep: Path | None = None, scan: bool = False) -> tuple[bool, str, Layout]:
    from app.pipeline.pipeline import extract_statement

    r = random.Random(seed * 7 + 1)
    lay = rnd_layout(seed)
    opening, txns = make_txns(r, n_rows)
    pdf = render(lay, opening, txns)
    if scan:
        pdf = to_scan(pdf, seed)
    if keep:
        keep.mkdir(parents=True, exist_ok=True)
        (keep / f"layout_{seed}.pdf").write_bytes(pdf)
    try:
        out = extract_statement(pdf)
    except Exception as e:  # noqa: BLE001
        return False, f"exception {e.__class__.__name__}: {e}", lay
    got = out.txns
    if len(got) != len(txns):
        return False, f"rows {len(got)} != {len(txns)}", lay
    for i, (g, e) in enumerate(zip(got, txns)):
        if g.date != e["date"]:
            return False, f"row {i} date {g.date} != {e['date']} (raw {g.raw_date!r})", lay
        if round(g.debit or 0, 2) != round(e["debit"] or 0, 2) or round(g.credit or 0, 2) != round(e["credit"] or 0, 2):
            return False, f"row {i} amount dr={g.debit} cr={g.credit} != dr={e['debit']} cr={e['credit']}", lay
        if "balance" in lay.cols and g.balance != e["balance"]:
            return False, f"row {i} balance {g.balance} != {e['balance']}", lay
    return True, "ok", lay


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, nargs="?", default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--keep", type=Path)
    ap.add_argument("--scan", action="store_true", help="OCR path: rasterise each layout as a noisy scan")
    a = ap.parse_args()
    fails = []
    for s in range(a.seed, a.seed + a.n):
        ok, msg, lay = check(s, keep=a.keep, scan=a.scan)
        if not ok:
            fails.append((s, msg, lay))
    print(f"{a.n - len(fails)}/{a.n} layouts extracted perfectly")
    for s, msg, lay in fails[:40]:
        print(f"  seed {s}: {msg}\n      scheme={lay.scheme} date={lay.date_fmt} rules={lay.rules} fill={lay.header_fill} "
              f"stack={lay.stacked_header} bi={lay.bilingual} group={lay.grouping} prefix={lay.prefix!r} blank={lay.blank!r} "
              f"desc={lay.desc_width} desc_order={lay.descending} open={lay.opening_row} rep={lay.repeat_header} "
              f"align={lay.num_align}\n      labels={ {k: v for k, v in lay.labels.items()} }")


if __name__ == "__main__":
    main()
