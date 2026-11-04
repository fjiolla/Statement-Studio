"""Heuristic rule engine.

Rules are evaluated in priority order; the first match wins. Each rule carries
a confidence and a human explanation so the UI can show *why* a transaction
got its category. Rules deliberately encode banking semantics that a model
trained on narrations alone would get wrong (direction, statement type,
reversals, interest/charges codes).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .merchants import find_merchant
from .narration import Narration


@dataclass
class RuleHit:
    category: str
    confidence: float
    rule_id: str
    explanation: str
    merchant: str = ""


@dataclass
class Ctx:
    n: Narration
    text: str          # normalized narration (upper)
    match_text: str    # narration with UPI handles / QR ids removed (for merchant lookup)
    is_debit: bool
    amount: float
    statement_type: str


Pred = Callable[[Ctx], bool]


@dataclass
class Rule:
    id: str
    category: str
    pattern: Optional[re.Pattern]
    confidence: float
    explanation: str
    when: Optional[Pred] = None

    def match(self, c: Ctx) -> Optional[RuleHit]:
        if self.when is not None and not self.when(c):
            return None
        if self.pattern is not None:
            m = self.pattern.search(c.text)
            if not m:
                return None
            token = m.group(0).strip()
            return RuleHit(self.category, self.confidence, self.id, self.explanation.format(token=token))
        return RuleHit(self.category, self.confidence, self.id, self.explanation)


def R(p: str) -> re.Pattern:
    return re.compile(p, re.I)


debit: Pred = lambda c: c.is_debit
credit: Pred = lambda c: not c.is_debit
card: Pred = lambda c: c.statement_type == "credit_card"
bank: Pred = lambda c: c.statement_type != "credit_card"

RULES: list[Rule] = [
    # --- reversals & refunds first: they look like the original transaction
    Rule("reversal", "refund", R(r"\bREV(ERSAL)?\b|\bRVSL\b|\bREV-|REVERSED?\b|\bRETURN(ED)?\b|CHARGEBACK|\bREFUND\b|CASHBACK"),
         0.93, "Narration says “{token}”", credit),
    Rule("upi_reward", "refund", R(r"GOOG-?PAYMENT|GOOGLE\s*PAY|GOOGL\s*EPA|PHONEPE\s*REWARD|SCRATCH\s*CARD"),
         0.85, "UPI app reward / cashback (“{token}”)", lambda c: (not c.is_debit) and c.amount < 1000),
    Rule("tax_refund", "refund", R(r"TAX\s*REFUND|ITD\s*REFUND|\bITR\s*REFUND"), 0.97, "Income-tax refund (“{token}”)", credit),

    # --- income
    Rule("salary", "salary", R(r"SALARY|\bSAL\b|\bSALARIES\b|PAYROLL|\bSAL\s*CR|STIPEND|INCENTIVE|\bBONUS\b"),
         0.95, "Narration contains “{token}”", credit),
    Rule("interest_cr", "interest", R(r"CREDIT\s*INTEREST|\bINT\.?\s*(PD|PAID|CR|CREDIT)\b|INTEREST\s*(CAPITALI[SZ]ED|PAID|CREDIT)|\bSB\s*INT|\bFD\s*INT|DIVIDEND"),
         0.97, "Interest/dividend credit (“{token}”)", credit),

    # --- bank charges & taxes (debits)
    Rule("gst", "charges", R(r"\b[ICS]?GST\b|GOODS\s*AND\s*SERVICES\s*TAX|SERVICE\s*TAX"), 0.9, "Tax on bank/card charges (“{token}”)",
         lambda c: c.is_debit and c.amount < 5000),
    Rule("charges", "charges", R(r"CHARGE|\bCHRG|\bCHG\b|^TO\s*INTEREST|INTEREST\s*(DEBIT|CHARGED|ON\s*OD)|\bFEE\b|\bFEES\b|ANNUAL\s*FEE|AMC\b|\bMCC\b|PENALTY|\bPENAL\b|MIN\s*BAL|"
                                r"NON\s*MAINT|CROSS\s*CURRENCY|MARKUP|OVERLIMIT|LATE\s*PAYMENT|FINANCE\s*CHARGE|SMS\s*ALERT|"
                                r"DEBIT\s*CARD\s*(ANNUAL|ISSU)|CONSOLIDATED\s*CHG|RECOVERY|STAMP\s*DUTY|\bINT\.?\s*COLL"),
         0.92, "Bank/card charge (“{token}”)", debit),
    Rule("tax", "tax", R(r"\bTDS\b|ADVANCE\s*TAX|SELF\s*ASSESSMENT|\bDTAX\b|\bIDTX\b|INCOME\s*TAX|\bCBDT\b|GST\s*PAYMENT|\bTIN\s*NSDL|PROFESSION\s*TAX"),
         0.94, "Tax payment (“{token}”)", debit),

    # --- card statement specifics
    Rule("cc_bill", "card_payment", R(r"^CC\s?X{2,}\d{4}|\bCCXX\d{4}|CREDIT\s*CARD\s*(BILL|PAYMENT|DUES)|\bPAVC\b|"
                                      r"BILL\s*PAY\s*DR-\w+-\d{4,6}X{4,8}\d{4}"),
         0.9, "Credit-card bill payment (“{token}”)", lambda c: c.is_debit and c.statement_type != "credit_card"),
    Rule("bbps", "utilities", R(r"\bBBPS|PAYBIL|BHARAT\s*BILL"), 0.85, "Bill payment via BBPS (“{token}”)",
         lambda c: c.is_debit and c.statement_type != "credit_card"),
    Rule("card_bill_paid", "card_payment", R(r"PAYMENT\s*RECEIVED|THANK\s*YOU|PAYMENT\s*-?\s*(NEFT|IMPS|UPI|BBPS|AUTO\s*DEBIT)|"
                                             r"\bBBPS\b|AUTOPAY|CC\s*PAYMENT|ONLINE\s*PAYMENT"),
         0.94, "Payment towards the card (“{token}”)", lambda c: card(c) and credit(c)),
    Rule("card_credit", "refund", None, 0.8, "Credit on a card statement that isn't a bill payment: refund or reversal",
         lambda c: card(c) and credit(c)),

    # --- cash
    Rule("chq_transfer", "transfer_out", R(r"TRANSFER\s*BY\s*CHEQUE|\bCHQ\s*TR\b|DEBIT\s*THROUGH\s*CHEQUE|\bTO\s*CLG\b|CHQ\s*PAID"),
         0.85, "Cheque payment (“{token}”)", debit),
    Rule("chq_clearing", "transfer_out", R(r"ZONE\s*SERIAL|\bCLG\s*CHQ|INWARD\s*CLEARING|OUTWARD\s*CHQ"),
         0.8, "Cheque cleared to a payee (“{token}”)", debit),
    Rule("atm", "cash_withdrawal", R(r"\bATM\b|\bNFS/|CASH\s*WDL|ATMWDL|\bCAM/|CASH\s*WITHDRAWAL|CASH\s*CHEQUE|SELF\s*CHQ|"
                                     r"MICRO\s*ATM\s*CASH\s*WDL|^(NWD|ATW|EAW|ATM)-\d"),
         0.96, "Cash withdrawal (“{token}”)", debit),
    Rule("cash_dep", "cash_deposit", R(r"CASH\s*DEP|BY\s*CASH|CASH\s*DEPOSIT|\bCDM\b|MICRO\s*ATM\s*CASH\s*DEP"),
         0.95, "Cash deposit (“{token}”)", credit),

    # --- loans, EMIs, mandates
    Rule("emi", "loan", R(r"\bEMI\b|LOAN|\bLN\s*PY|\bLNPY\b|HOUSING\s*LOAN|PERSONAL\s*LOAN|CAR\s*LOAN|EDUCATION\s*LOAN|\bLAN\s*\d|INSTALMENT|INSTALLMENT"),
         0.93, "Loan repayment (“{token}”)", debit),
    Rule("loan_disb", "transfer_in", R(r"LOAN\s*DISB|DISBURSAL|DISBURSEMENT"), 0.9, "Loan disbursal (“{token}”)", credit),
    Rule("sip", "investment", R(r"\bSIP\b|MUTUAL\s*FUND|\bMF\b|\bNPS\b|\bPPF\b|\bRD\s*INST|RECURRING\s*DEP|FIXED\s*DEP|\bFD\s*BOOK|TO\s*RD|TO\s*FD|"
                                r"SOVEREIGN\s*GOLD|\bSGB\b|\bDEMAT\b|SECURITIES|BROKING|CLEARING\s*CORP"),
         0.9, "Investment (“{token}”)", debit),
    Rule("insurance", "insurance", R(r"INSURANCE|\bPREMIUM\b|\bPOLICY\b|\bPMSBY\b|\bPMJJBY\b|\bPMJBY\b|\bLIC\b"), 0.9, "Insurance (“{token}”)", debit),

    # --- bills & rent
    Rule("rent", "rent", R(r"\bRENT\b|HOUSE\s*RENT|\bLEASE\b|MAINTENANCE|SOCIETY"), 0.85, "Rent/housing (“{token}”)", debit),
    Rule("bills", "utilities", R(r"ELECTRICITY|\bPOWER\b|RECHARGE|\bRCHG\b|\bTOP\b\s*-|POSTPAID|PREPAID|BROADBAND|\bDTH\b|\bGAS\b\s*BILL|WATER\s*BILL|"
                                 r"MOBILE\s*BILL|TELECOM|BILLPAY|BILL\s*PAY|BILLDESK|BILLDK|\bBPAY\b|\bBIL/"),
         0.75, "Bill payment (“{token}”)", debit),
]

# Generic channel fallbacks: lower confidence, overridable by ML.
P2P_HINTS = R(r"\b(MR|MRS|MS|SHRI|SMT)\b|[A-Z]+\s+[A-Z]\b")


GENERIC_MERCHANTS = {"Rent", "Electricity Bill", "Water Bill", "Society Maintenance", "Mutual Fund", "Card bill payment", "PPF", "NPS"}


def _clean_for_merchant(text: str) -> str:
    t = re.sub(r"[\w.\-]+@[\w]+", " ", text)
    t = re.sub(r"\S*(paytmqr|pytm\d|paytmna|paytmbw|paytmpayout|bharatpe|othpsp)\S*", " ", t, flags=re.I)
    return t


def apply_rules(n: Narration, is_debit: bool, amount: float, statement_type: str) -> Optional[RuleHit]:
    ctx = Ctx(n=n, text=n.normalized, match_text=_clean_for_merchant(n.raw), is_debit=is_debit,
              amount=abs(amount), statement_type=statement_type)

    for rule in RULES[:2]:  # reversals/refunds before merchant lookup
        hit = rule.match(ctx)
        if hit:
            return hit

    for rule in RULES[2:]:
        if rule.id in ("bills", "rent"):
            break
        hit = rule.match(ctx)
        if hit:
            return hit

    m = find_merchant(ctx.match_text)
    if m:
        merchant, cat, alias = m
        if not is_debit and cat in ("food", "groceries", "shopping", "travel", "fuel", "entertainment", "health", "education"):
            return RuleHit("refund", 0.8, "merchant_credit", f"Credit from {merchant}: likely a refund", merchant)
        if not is_debit:
            return RuleHit("transfer_in", 0.72, "merchant_credit", f"Credit from {merchant} (payout / redemption)", merchant)
        if cat == "card_payment" and statement_type == "credit_card" and is_debit:
            cat = "shopping"
        # generic dictionary entries name a *kind* of payee; keep the real payee name for display
        label = "" if merchant in GENERIC_MERCHANTS else merchant
        return RuleHit(cat, 0.9, "merchant", f"Known merchant: {merchant} (matched “{alias}”)", label)

    for rule in RULES:
        if rule.id in ("bills", "rent"):
            hit = rule.match(ctx)
            if hit:
                return hit
    return None


def channel_fallback(n: Narration, is_debit: bool, statement_type: str) -> Optional[RuleHit]:
    """Weak priors from the payment channel alone; ML may override these."""
    if statement_type == "credit_card":
        return None
    if n.channel in ("UPI", "IMPS", "NEFT", "RTGS", "TRANSFER", "CHEQUE"):
        if n.channel == "UPI" and n.is_merchant_vpa and is_debit:
            return RuleHit("shopping", 0.6, "upi_merchant", f"UPI payment to a merchant QR ({n.vpa or 'merchant'})")
        who = f" {n.counterparty}" if n.counterparty else ""
        # a payee that reads like a person's name makes a P2P transfer near-certain
        person = bool(n.counterparty) and bool(re.fullmatch(r"(?:Mr |Mrs |Ms |Shri |Smt )?[A-Za-z]{2,}(?: [A-Za-z.]{1,})*",
                                                            n.counterparty)) and len(n.counterparty.split()) <= 4
        conf = 0.74 if person else 0.62
        if is_debit:
            return RuleHit("transfer_out", conf, "p2p_out", f"{n.channel} transfer to{who or ' another account'}")
        return RuleHit("transfer_in", conf, "p2p_in", f"{n.channel} transfer from{who or ' another account'}")
    if n.channel == "NACH":
        return RuleHit("loan" if is_debit else "transfer_in", 0.55, "nach", "Auto-debit mandate (NACH/ACH)")
    if n.channel == "CASH":
        return RuleHit("cash_deposit" if not is_debit else "cash_withdrawal", 0.7, "cash", "Cash transaction")
    return None
