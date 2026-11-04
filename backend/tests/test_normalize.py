from datetime import date

import pytest

from app.pipeline.normalize import looks_like_date_start, parse_amount, parse_date, signed_balance


@pytest.mark.parametrize("text,expected", [
    ("03/10/2023", date(2023, 10, 3)), ("02/06/18", date(2018, 6, 2)), ("01-Dec-2022", date(2022, 12, 1)),
    ("20-NOV-24", date(2024, 11, 20)), ("3 May 2018", date(2018, 5, 3)), ("10 May 2018", date(2018, 5, 10)),
    ("2025-08-01", date(2025, 8, 1)), ("17.02.2022", date(2022, 2, 17)), ("Sept 5, 2024", date(2024, 9, 5)),
    ("13/31/2024", None),
])
def test_dates_day_first(text, expected):
    assert parse_date(text) == expected


def test_day_month_without_year_uses_hint():
    assert parse_date("12 Mar", year_hint=2024) == date(2024, 3, 12)
    assert parse_date("12 Mar") is None


def test_compact_ocr_date_only_when_allowed():
    assert parse_date("01082025") is None
    assert parse_date("01082025", allow_compact=True) == date(2025, 8, 1)


@pytest.mark.parametrize("text,value,marker", [
    ("1,20,749.89", 120749.89, None), ("₹ 2,500.00", 2500.0, None), ("300.00 (Dr)", 300.0, "dr"),
    ("25000.00 (Cr)", 25000.0, "cr"), ("25,296.00CR", 25296.0, "cr"), ("2.00 Cr", 2.0, "cr"), ("(1,234.50)", 1234.5, "neg"),
    ("-", None, None), ("0.0", 0.0, None), ("Rs. 99", 99.0, None),
])
def test_amounts(text, value, marker):
    assert parse_amount(text) == (value, marker)


def test_ocr_amount_repairs():
    assert parse_amount("400 00", ocr=True) == (400.0, None)
    assert parse_amount("§,217.50", ocr=True) == (5217.5, None)
    assert parse_amount("2.00 αr", ocr=True) == (2.0, "cr")


def test_long_reference_is_not_money():
    assert parse_amount("0000806023180071") == (None, None)


def test_signed_balance_overdraft():
    assert signed_balance("1,500.00 Dr") == -1500.0
    assert signed_balance("1,500.00") == 1500.0


def test_date_start_detection():
    assert looks_like_date_start("10 May")
    assert looks_like_date_start("01/08/2025 01/08/2025 UPI")
    assert not looks_like_date_start("UPI/DR/123")
