"""Turn a validated case plan into one Invoice. Amounts come only from the catalog."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from random import Random

from faker import Faker

from invoice_gen.catalog import ServiceCatalog
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
from invoice_gen.names import display_name, split_person
from invoice_gen.plans import CasePlan, PlanRejected, validate_plan
from invoice_gen.pricing import einfachsatz_from_points, line_amount
from invoice_gen.scenarios import DemoScenario
from invoice_gen.validators import validate_invoice


def _address(fake: Faker) -> Address:
    return Address(
        street=fake.street_address(),
        postal_code=fake.postcode(),
        city=fake.city(),
        country="DE",
    )


def _default_factor(scenario: DemoScenario, code: str) -> Decimal:
    low, high = scenario.factor_bounds(code)
    if low == high:
        return low
    return min(Decimal("2.3"), high)


def assemble_invoice(
    plan: CasePlan,
    scenario: DemoScenario,
    catalog: ServiceCatalog,
    *,
    period_start: date,
    period_end: date,
    age_min: int,
    age_max: int,
    seed: int | None,
    mode: str,
) -> Invoice:
    errors = validate_plan(plan, scenario, period_start=period_start, period_end=period_end)
    if errors:
        raise PlanRejected(errors)

    by_code = catalog.by_code()
    materials_by_name = {item.description: item for item in catalog.materials}
    bilateral = plan.laterality == "both"
    issue_date = period_end
    rng = Random(seed)
    fake = Faker("de_DE")
    if seed is not None:
        fake.seed_instance(seed)

    line_items: list[LineItem] = []
    for event in sorted(plan.events, key=lambda item: (item.day_offset, item.code)):
        service = by_code.get(event.code)
        if service is None or service.points is None:
            raise PlanRejected([f"code {event.code} is not in the priced catalog"])
        einfach = einfachsatz_from_points(service.points)
        if einfach != service.einfachsatz_eur:
            raise PlanRejected(
                [
                    f"catalog einfachsatz for {event.code} is {service.einfachsatz_eur}, "
                    f"official points give {einfach}"
                ]
            )
        factor = event.factor if event.factor is not None else _default_factor(scenario, event.code)
        low, high = scenario.factor_bounds(event.code)
        if factor < low or factor > high:
            raise PlanRejected([f"code {event.code} factor {factor} is outside {low}..{high}"])
        quantity = Decimal("2") if bilateral and event.code in scenario.bilateral_quantity_codes else Decimal("1")
        line_items.append(
            LineItem(
                service_date=period_start + timedelta(days=event.day_offset),
                code=service.code,
                description=service.description,
                encounter_id=event.encounter_id,
                factor_justification=event.factor_justification if factor > Decimal("2.3") else None,
                quantity=quantity,
                factor=factor,
                einfachsatz_eur=einfach,
                line_total_eur=line_amount(einfach, factor, quantity),
            )
        )

    materials: list[MaterialItem] = []
    for name in plan.materials:
        offering = materials_by_name.get(name)
        if offering is None:
            raise PlanRejected([f"material {name!r} has no catalog price"])
        materials.append(
            MaterialItem(
                description=offering.description,
                quantity=Decimal("1"),
                unit_price_eur=offering.unit_price_eur,
                line_total_eur=offering.unit_price_eur,
            )
        )

    services_sum = sum((item.line_total_eur for item in line_items), Decimal("0.00"))
    materials_sum = sum((item.line_total_eur for item in materials), Decimal("0.00"))
    gross = services_sum + materials_sum

    female = rng.random() < 0.5
    raw_name = fake.name_female() if female else fake.name_male()
    person = split_person(raw_name)
    full_name = display_name(person)
    salutation = "Frau" if female else "Herr"
    age_years = rng.randint(age_min, age_max)
    birth_year = issue_date.year - age_years
    birth_date = date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
    if birth_date > issue_date:
        birth_date = birth_date.replace(year=birth_date.year - 1)
    invoice_number = f"RE-{uuid.uuid4().hex[:10].upper()}"
    patient_number = f"P-{uuid.uuid4().hex[:8].upper()}"
    period_dates = [item.service_date for item in line_items]

    invoice = Invoice(
        scenario_id=scenario.id,
        billing_rule=catalog.billing_rule,
        invoice_number=invoice_number,
        patient_number=patient_number,
        issue_date=issue_date,
        service_until=max(period_dates),
        payment_due_date=issue_date + timedelta(days=14),
        diagnosis=scenario.label,
        patient=Patient(
            salutation=salutation,
            full_name=full_name,
            first_name=person.first_name,
            last_name=person.last_name,
            academic_title=person.academic_title,
            birth_date=birth_date,
            address=_address(fake),
            patient_number=patient_number,
        ),
        provider=Provider(
            physician_name=f"Dr. {fake.last_name()}",
            specialty=catalog.specialty,
            address=_address(fake),
        ),
        bank=BankDetails(bank_name=f"{fake.city()} Bank", iban=fake.iban(), bic=fake.swift()),
        service_period_start=min(period_dates),
        service_period_end=max(period_dates),
        line_items=line_items,
        materials=materials,
        totals=InvoiceTotals(
            services_eur=services_sum,
            materials_eur=materials_sum,
            gross_eur=gross,
            tax_eur=Decimal("0.00"),
        ),
        notes=(
            f"Mode: {mode}. {plan.case_summary} "
            "Prices and totals were calculated in Python from the GOÄ catalog, not by the text model. "
            "Personal data is fictional."
        ),
    )
    validate_invoice(invoice, catalog)
    return invoice
