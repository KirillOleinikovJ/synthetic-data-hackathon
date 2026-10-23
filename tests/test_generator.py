from invoice_gen.catalog import load_catalog
from invoice_gen.generator import generate_invoice
from invoice_gen.validators import validate_invoice


def test_generate_reproducible_and_valid():
    catalog = load_catalog("data/service_catalog.json")
    a = generate_invoice(catalog, seed=42)
    b = generate_invoice(catalog, seed=42)
    assert a.diagnosis == b.diagnosis
    assert a.totals.gross_eur == b.totals.gross_eur
    assert len(a.line_items) >= 2
    assert validate_invoice(a, catalog) == []
    codes_by_day: dict = {}
    for item in a.line_items:
        codes_by_day.setdefault(item.service_date, set()).add(item.code)
    for codes in codes_by_day.values():
        assert not ({"5", "6"} <= codes)
