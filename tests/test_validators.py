from datetime import date
from decimal import Decimal

import pytest

from invoice_gen.models import (
    Address,
    BankDetails,
    Invoice,
    InvoiceTotals,
    LineItem,
    MaterialItem,
    Patient,
    Provider,
)
from invoice_gen.validators import ValidationError, validate_invoice


def _base(**overrides) -> Invoice:
    data = dict(
        scenario_id="goae_eyelid_surgery_v1",
        invoice_number="3000",
        patient_number="2000",
        issue_date=date(2026, 3, 28),
        service_until=date(2026, 4, 7),
        payment_due_date=date(2026, 4, 18),
        diagnosis="Dermatochalasis bds. Oberlid",
        patient=Patient(
            salutation="Frau",
            full_name="Mandy Muster",
            birth_date=date(1957, 7, 5),
            address=Address(street="Teststr. 1", postal_code="10115", city="Berlin"),
            patient_number="2000",
        ),
        provider=Provider(
            physician_name="Dr. Walter",
            specialty="Augenheilkunde",
            address=Address(street="Klinik 1", postal_code="80331", city="Muenchen"),
        ),
        bank=BankDetails(
            bank_name="Testbank",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
        ),
        service_period_start=date(2026, 2, 10),
        service_period_end=date(2026, 4, 7),
        line_items=[
            LineItem(
                service_date=date(2026, 2, 10),
                code="1",
                description="Beratung",
                quantity=Decimal("1"),
                factor=Decimal("2.3"),
                einfachsatz_eur=Decimal("4.66"),
                line_total_eur=Decimal("10.72"),
            )
        ],
        materials=[
            MaterialItem(
                description="OP-Set",
                quantity=Decimal("1"),
                unit_price_eur=Decimal("16.66"),
                line_total_eur=Decimal("16.66"),
            )
        ],
        totals=InvoiceTotals(
            services_eur=Decimal("10.72"),
            materials_eur=Decimal("16.66"),
            gross_eur=Decimal("27.38"),
            tax_eur=Decimal("0.00"),
        ),
    )
    data.update(overrides)
    return Invoice(**data)


def test_valid_invoice_passes():
    assert validate_invoice(_base()) == []


def test_bad_goae_amount_fails():
    inv = _base(
        line_items=[
            LineItem(
                service_date=date(2026, 2, 10),
                code="1",
                description="Beratung",
                quantity=Decimal("1"),
                factor=Decimal("2.3"),
                einfachsatz_eur=Decimal("4.66"),
                line_total_eur=Decimal("99.00"),
            )
        ],
        materials=[],
        totals=InvoiceTotals(
            services_eur=Decimal("99.00"),
            materials_eur=Decimal("0.00"),
            gross_eur=Decimal("99.00"),
        ),
    )
    with pytest.raises(ValidationError) as exc:
        validate_invoice(inv)
    assert any("Einfachsatz" in e for e in exc.value.errors)


def test_date_outside_period_fails():
    inv = _base(
        line_items=[
            LineItem(
                service_date=date(2025, 1, 1),
                code="1",
                description="Beratung",
                quantity=Decimal("1"),
                factor=Decimal("2.3"),
                einfachsatz_eur=Decimal("4.66"),
                line_total_eur=Decimal("10.72"),
            )
        ],
        materials=[],
        totals=InvoiceTotals(
            services_eur=Decimal("10.72"),
            materials_eur=Decimal("0.00"),
            gross_eur=Decimal("10.72"),
        ),
    )
    with pytest.raises(ValidationError):
        validate_invoice(inv)
