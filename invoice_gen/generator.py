from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from random import Random

from faker import Faker

from invoice_gen.catalog import ServiceCatalog, ServiceOffering
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
from invoice_gen.validators import validate_invoice

# Older catalog sampler used by tests/test_generator.py.
# The demo CLI and UI do not call this. Suture removal and dressings
# are not added here; a demo scenario has to list those events itself.

MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _de_address(fake: Faker) -> Address:
    return Address(
        street=fake.street_address(),
        postal_code=fake.postcode(),
        city=fake.city(),
        country="DE",
    )


def _line(service: ServiceOffering, service_date: date, bilateral: bool) -> LineItem:
    qty = Decimal("2") if (service.bilateral_qty and bilateral) else Decimal("1")
    factor = service.typical_factor
    einfach = service.einfachsatz_eur
    return LineItem(
        service_date=service_date,
        code=service.code,
        description=service.description,
        quantity=qty,
        factor=factor,
        einfachsatz_eur=einfach,
        line_total_eur=_money(einfach * qty * factor),
    )


def generate_invoice(
    catalog: ServiceCatalog,
    *,
    seed: int | None = None,
    issue_date: date | None = None,
) -> Invoice:
    """Generate one GOÄ eyelid-surgery invoice matching Archiv-Invoices structure."""
    rng = Random(seed)
    fake = Faker("de_DE")
    if seed is not None:
        Faker.seed(seed)
        fake.seed_instance(seed)

    by_code = catalog.by_code()
    diagnosis = rng.choice(list(catalog.diagnoses))
    bilateral = diagnosis.bilateral
    # These eye codes already include the exam, or GOÄ forbids them beside 5/6.
    restricted = {"1203", "1204", "1210", "1211", "1212", "1213", "1217", "1228", "1240"}
    laser_ops = {"1360", "1365", "1369"}

    today = issue_date or date.today()
    payment_due = today + timedelta(days=rng.randint(10, 21))
    has_surgery = bool(diagnosis.surgery_codes)
    if has_surgery:
        surgery_day = today - timedelta(days=rng.randint(12, 26))
        preop_day = surgery_day - timedelta(days=rng.randint(7, 14))
        consult_day = preop_day - timedelta(days=rng.randint(7, 21))
    else:
        consult_day = today - timedelta(days=rng.randint(8, 20))
        surgery_day = preop_day = consult_day
    extra_day = consult_day + timedelta(days=rng.randint(1, 4))

    line_items: list[LineItem] = []
    line_items.append(_line(by_code["1"], consult_day, bilateral))
    needs_separate_exam = any(code in restricted for code in diagnosis.exam_codes)
    if not needs_separate_exam:
        line_items.append(_line(by_code[rng.choice(["5", "6"])], consult_day, bilateral))
    for code in diagnosis.exam_codes:
        day = extra_day if code in restricted else consult_day
        line_items.append(_line(by_code[code], day, bilateral))

    surgery_points = 0
    for code in diagnosis.surgery_codes:
        service = by_code[code]
        surgery_points = max(surgery_points, service.points or 0)
        line_items.append(_line(service, surgery_day, bilateral))
    major = surgery_points >= 500
    if major and "34" in by_code:
        line_items.append(_line(by_code["34"], preop_day, bilateral))
    if surgery_points >= 250 and not set(diagnosis.surgery_codes) <= laser_ops and "491" in by_code:
        line_items.append(_line(by_code["491"], surgery_day, bilateral))
    if major and not set(diagnosis.surgery_codes) <= laser_ops and "440" in by_code:
        line_items.append(_line(by_code["440"], surgery_day, bilateral))
    if surgery_points >= 250:
        for service in catalog.by_phase("ambulatory_surcharge"):
            if service.point_min is None or service.point_max is None:
                continue
            if service.point_min <= surgery_points <= service.point_max:
                line_items.append(_line(service, surgery_day, bilateral))
                break

    line_items.sort(key=lambda x: (x.service_date, x.code))
    period_start = min(item.service_date for item in line_items)
    period_end = max(item.service_date for item in line_items)
    service_until = period_end

    materials: list[MaterialItem] = []
    if catalog.materials and major:
        n_mat = rng.randint(2, min(3, len(catalog.materials)))
        for mat in rng.sample(list(catalog.materials), k=n_mat):
            qty = Decimal("1")
            materials.append(
                MaterialItem(
                    description=mat.description,
                    quantity=qty,
                    unit_price_eur=mat.unit_price_eur,
                    line_total_eur=_money(mat.unit_price_eur * qty),
                )
            )

    services_sum = _money(sum((i.line_total_eur for i in line_items), Decimal("0")))
    materials_sum = _money(sum((m.line_total_eur for m in materials), Decimal("0")))
    gross = _money(services_sum + materials_sum)

    sex = rng.choice(["F", "M"])
    if sex == "F":
        salutation = "Frau"
        full_name = fake.name_female()
    else:
        salutation = "Herr"
        full_name = fake.name_male()

    # Stable-looking numbers like references (3000+/2000+)
    invoice_no = str(3000 + rng.randint(0, 80))
    patient_no = str(2000 + rng.randint(0, 80))

    physician = fake.last_name()
    invoice = Invoice(
        scenario_id=catalog.scenario_id,
        billing_rule=catalog.billing_rule,
        invoice_number=invoice_no,
        patient_number=patient_no,
        issue_date=today,
        service_until=service_until,
        payment_due_date=payment_due,
        diagnosis=diagnosis.label,
        patient=Patient(
            salutation=salutation,
            full_name=full_name,
            birth_date=fake.date_of_birth(minimum_age=35, maximum_age=85),
            address=_de_address(fake),
            patient_number=patient_no,
            insurance_number=None,
        ),
        provider=Provider(
            physician_name=f"Dr. {physician}",
            specialty=catalog.specialty,
            address=_de_address(fake),
            lanr=f"{rng.randint(100000000, 999999999)}",
            bsnr=f"{rng.randint(100000000, 999999999)}",
        ),
        bank=BankDetails(
            bank_name=f"{fake.city()} Bank",
            iban=fake.iban(),
            bic=fake.swift(),
        ),
        service_period_start=period_start,
        service_period_end=period_end,
        line_items=line_items,
        materials=materials,
        totals=InvoiceTotals(
            services_eur=services_sum,
            materials_eur=materials_sum,
            gross_eur=gross,
            tax_eur=Decimal("0.00"),
        ),
        notes=(
            "Synthetic ophthalmology invoice. "
            "GOAE points from the official fee schedule, section Augenheilkunde."
        ),
    )
    validate_invoice(invoice, catalog)
    return invoice
