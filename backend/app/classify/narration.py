"""Parse Indian bank narrations into channel / counterparty / UPI handle / reference.

Narrations are dense codes that differ per bank:
  UPI/DR/253135370887/DOMINGO S/BKID/silvadomni/Paym          (SBI)
  UPI-303702011409044-9307676700@UPI-815518132372-OK          (HDFC)
  UPIAR/204845513259/DR/Latheef/CNRB/0749101056362@           (Union)
  UPI209216896553CRDEVKPYTM946954655paytmNA                   (IndusInd, separators stripped)
  NEFT DR-UBIN0539686-RAJU DUBEY-NETBANK, MUM-N1551...        (HDFC)
  MMT/IMPS/328219701406/PENNYDROP/NorthernAr/Axis Ba           (ICICI)
  ACH D- TP ACH HOME-105909750, NFS/CASH WDL/..., POS 4160XX DCSIRELIANCE ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CHANNEL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("UPI", re.compile(r"\bUPI|@(?:ok\w+|ybl|ibl|axl|paytm|upi|apl|icici|sbi|hdfcbank|axisbank|kotak|yesbank|freecharge|jupiteraxis|fbl|idfcbank|waicici|pthdfc|ptyes|ptaxis|ptsbi)\b", re.I)),
    ("NEFT", re.compile(r"\bNEFT\b|^N[A-Z]{4}[A-Z0-9]{10,}", re.I)),
    ("RTGS", re.compile(r"\bRTGS\b", re.I)),
    ("IMPS", re.compile(r"\bIMPS|\bMMT/|\bP2A\d", re.I)),
    ("ATM", re.compile(r"\bATM\b|\bNFS/|CASH\s*WDL|\bCAM/|ATMWDL|CASH\s*WITHDRAWAL", re.I)),
    ("CARD", re.compile(r"\bPOS\b|\bVPS/|\bIPS/|\bPCD/|\bECOM\b|DEBIT\s*CARD|\bDC\s|\bVISA\b|\bMASTERCARD\b|\bRUPAY\b", re.I)),
    ("NACH", re.compile(r"\bN?ACH\b|\bNACH\b|\bECS\b|\bSI\b|STANDING\s*INSTRUCTION|\bMANDATE\b", re.I)),
    ("CHEQUE", re.compile(r"\bCHQ\b|CHEQUE|\bCLEARING\b|\bCLG\b|\bINWARD\b", re.I)),
    ("BILLPAY", re.compile(r"BILL\s*PAY|\bBIL/|\bBPAY\b|BILLDESK|BILLDK", re.I)),
    ("CASH", re.compile(r"CASH\s*DEP|BY\s*CASH|CASH\s*DEPOSIT", re.I)),
    ("TRANSFER", re.compile(r"\bTRANSFER\b|\bTRF\b|\bTFR\b|\bFT\b|\bINFT?\b|\bINB\b|\bNET\s*BANKING", re.I)),
    ("INTEREST", re.compile(r"\bINT(EREST)?\b.*\b(PD|PAID|CREDIT|CAPITALI[SZ]ED)\b|\bCREDIT\s*INTEREST\b|\bINT\.PD\b", re.I)),
]

RE_VPA = re.compile(r"([a-z0-9][a-z0-9.\-_]{1,60}@[a-z][a-z0-9]{1,30})", re.I)
RE_REF = re.compile(r"(?<![A-Z0-9])(\d{12})(?!\d)")
RE_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
RE_SPACES = re.compile(r"\s+")

NOISE_TOKENS = {
    "UPI", "DR", "CR", "NEFT", "IMPS", "RTGS", "MMT", "PAYM", "PAYMENT", "PAY", "TO", "BY", "FROM", "TRANSFER",
    "TRF", "TFR", "WDL", "DEP", "NA", "OK", "NETBANK", "PERSONAL", "OTHPSPNA", "UPIAR", "UPIAB", "SENT", "RECEIVED",
    "INB", "MOB", "IB", "FT", "P2A", "P2M", "REF", "NO", "UTR", "THE", "OF", "AND", "CHQ", "EMI", "POS", "DEBIT",
    "CREDIT", "BILLPAY", "BIL", "BPAY", "ACH", "NACH", "ECS", "DCSI", "VPS", "IPS", "ATM", "CASH", "INWD", "INET",
    "IMPSP", "CORP", "XXXX",
}
BANK_CODES = {
    "SBIN", "HDFC", "ICIC", "UTIB", "KKBK", "INDB", "UBIN", "IDIB", "PUNB", "BARB", "CNRB", "YESB", "IDFB", "FDRL",
    "BKID", "MAHB", "CBIN", "IOBA", "UCBA", "AUBL", "RATN", "SIBL", "KVBL", "PYTM", "AIRP", "IPOS", "DCBL", "CIUB",
    "KARB", "SRCB", "ESMF", "KLGB", "JAKA", "TMBL", "CSBK", "DLXB", "UJVN", "NSPB", "FINO", "JIOP", "ICICI", "AXIS",
}
MERCHANT_VPA_HINTS = re.compile(r"paytmqr|bharatpe|\.rzp@|razorpay|pinelabs|yespay|ezetap|cashfree|payu|"
                                r"\bq\d{6,}@|gpay-\d+|merchant|\.mid@|@hdfcbankmer|@mairtel|instamojo|^mab\d", re.I)


@dataclass
class Narration:
    raw: str
    normalized: str
    channel: str = "OTHER"
    counterparty: str = ""
    vpa: str = ""
    reference: str = ""
    counterparty_bank: str = ""
    is_merchant_vpa: bool = False
    tokens: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable key used for recurring detection and learned user rules."""
        base = self.vpa or self.counterparty or self.normalized
        return re.sub(r"[^a-z0-9@.]", "", base.lower())[:48]


def normalize(text: str) -> str:
    t = (text or "").upper()
    t = re.sub(r"[|]", " ", t)
    return RE_SPACES.sub(" ", t).strip()


def _channel(text: str) -> str:
    for name, pat in CHANNEL_PATTERNS:
        if pat.search(text):
            return name
    return "OTHER"


def _clean_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z&.' ]", " ", s)
    words = [w for w in s.split() if w.upper() not in NOISE_TOKENS and w.upper() not in BANK_CODES and len(w) > 1]
    return " ".join(words[:5]).strip().title()


def parse(text: str) -> Narration:
    raw = text or ""
    norm = normalize(raw)
    n = Narration(raw=raw, normalized=norm, channel=_channel(norm))

    vm = RE_VPA.search(raw.replace(" ", "")) if "@" in raw else None
    if vm:
        n.vpa = vm.group(1).lower().strip(".-")
        n.is_merchant_vpa = bool(MERCHANT_VPA_HINTS.search(n.vpa))
    if re.search(r"BHARATPE|PAYTMQR|(?:\b|/)Q\d{7,}(?:@|/|\b)|RAZORPAY|PINELABS|\.RZP", norm):
        n.is_merchant_vpa = True
    rm = RE_REF.search(norm)
    if rm:
        n.reference = rm.group(1)
    im = RE_IFSC.search(norm)
    if im:
        n.counterparty_bank = im.group(1)[:4]

    # counterparty extraction per channel
    cp = ""
    if n.channel == "UPI":
        parts = [p for p in re.split(r"[/\-]", norm) if p]
        # UPI/DR/<ref>/<NAME>/<BANK>/<vpa>/<note>  |  UPIAR/<ref>/DR/<NAME>/<BANK>/...
        names = []
        for p in parts:
            pu = p.strip()
            if re.fullmatch(r"\d+", pu) or pu in NOISE_TOKENS or pu[:4] in BANK_CODES and len(pu) <= 5:
                continue
            if "@" in pu or re.fullmatch(r"[A-Z0-9]{10,}", pu):
                continue
            names.append(pu)
        if names:
            cp = names[0]
        if not cp and n.vpa:
            cp = n.vpa.split("@")[0]
        if not cp:
            # IndusInd style: UPI<12 digits>CR<NAME...>PYTM...
            m = re.search(r"UPI\d{12}(?:CR|DR)?([A-Z]{3,})", norm.replace(" ", ""))
            if m:
                cp = m.group(1)[:20]
    elif n.channel in ("NEFT", "RTGS", "IMPS"):
        m = re.search(r"(?:NEFT|RTGS|IMPS)\s*(?:DR|CR)?\s*-\s*(?:[A-Z]{4}0[A-Z0-9]{6}-)?([A-Z][A-Z .]{2,40}?)-", norm)
        if not m:
            m = re.search(r"IMPS-\d+-([A-Z][A-Z .]{2,40}?)(?:-|$)", norm)
        if not m:
            m = re.search(r"MMT/IMPS/\d+/([^/]+)/([^/]+)", norm)
        if m:
            cp = m.group(1)
        else:
            # IndusInd inward NEFT: N<BANK><ref><IFSC> <NAME> ...
            m = re.search(r"^N[A-Z]{4}[A-Z0-9]+\s+([A-Z][A-Z ]{3,40})", norm)
            if m:
                cp = m.group(1)
    elif n.channel == "ATM":
        cp = "ATM cash"
    elif n.channel == "CARD":
        m = re.search(r"POS\s+\S+\s+(.+?)(?:\s+POS\b|$)", norm) or re.search(r"VPS/([^/]+)", norm)
        if m:
            cp = m.group(1)
    elif n.channel == "NACH":
        m = re.search(r"ACH\s*(?:D|C|DR|CR|DEBIT|CREDIT)?\s*-?\s*([A-Z][A-Z .]{2,40})", norm)
        if m:
            cp = m.group(1)
    elif n.channel == "BILLPAY":
        m = re.search(r"BILLDK\s*([A-Z]+)|BILLPAY\s*DR-([A-Z]+)", norm)
        if m:
            cp = m.group(1) or m.group(2)
    if not cp:
        cp = norm.split("  ")[0][:40]
    cp = re.sub(r"^DCSI(?=[A-Z])", "", cp.strip())  # HDFC debit-card POS prefix glued to merchant
    n.counterparty = _clean_name(cp)
    n.tokens = [t for t in re.split(r"[^A-Z0-9]+", norm) if t and not t.isdigit()]
    return n
