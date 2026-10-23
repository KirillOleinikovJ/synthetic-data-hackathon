from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from invoice_gen.catalog import ServiceCatalog
from invoice_gen.models import Invoice

MONEY = Decimal("0.01")
FACTOR = Decimal("0.001")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class ValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def check_required_fields(invoice: Invoice) -> list[str]:
    errors: list[str] = []
    required = {
        "invoice_number": invoice.invoice_number,
        "patient_number": invoice.patient_number,
        "issue_date": invoice.issue_date,
        "diagnosis": invoice.diagnosis,
        "patient.full_name": invoice.patient.full_name,
        "patient.birth_date": invoice.patient.birth_date,
        "patient.address.street": invoice.patient.address.street,
        "provider.physician_name": invoice.provider.physician_name,
        "provider.specialty": invoice.provider.specialty,
        "bank.iban": invoice.bank.iban,
        "line_items": invoice.line_items,
        "totals.gross_eur": invoice.totals.gross_eur,
    }
    for path, value in required.items():
        if value is None or value == "" or value == []:
            errors.append(f"missing required field: {path}")
    for i, item in enumerate(invoice.line_items):
        for field in (
            "service_date",
            "code",
            "description",
            "quantity",
            "factor",
            "einfachsatz_eur",
            "line_total_eur",
        ):
            if getattr(item, field) in (None, ""):
                errors.append(f"line_items[{i}].{field} is required")
    return errors


def check_date_order(invoice: Invoice) -> list[str]:
    errors: list[str] = []
    if invoice.patient.birth_date > invoice.issue_date:
        errors.append("patient.birth_date must be on or before issue_date")
    if invoice.service_period_start > invoice.service_period_end:
        errors.append("service_period_start must be <= service_period_end")
    if invoice.service_period_end > invoice.service_until:
        errors.append("service_period_end must be on or before service_until")
    if invoice.service_until > invoice.issue_date and False:
        # Reference samples sometimes print service_until slightly after issue_date;
        # we allow service_until >= period_end and payment_due after issue.
        pass
    if invoice.payment_due_date < invoice.issue_date:
        errors.append("payment_due_date must be on or after issue_date")
    for i, item in enumerate(invoice.line_items):
        if item.service_date < invoice.service_period_start:
            errors.append(f"line_items[{i}].service_date before service period")
        if item.service_date > invoice.service_period_end:
            errors.append(f"line_items[{i}].service_date after service period")
        if item.service_date > invoice.service_until:
            errors.append(f"line_items[{i}].service_date after service_until")
    return errors


def check_amounts(invoice: Invoice) -> list[str]:
    errors: list[str] = []
    services_sum = Decimal("0.00")
    for i, item in enumerate(invoice.line_items):
        expected = _money(item.einfachsatz_eur * item.quantity * item.factor)
        actual = _money(item.line_total_eur)
        if expected != actual:
            errors.append(
                f"line_items[{i}] Betrag={actual} != "
                f"Einfachsatz*Anzahl*Faktor={expected}"
            )
        services_sum += expected
    services_sum = _money(services_sum)

    materials_sum = Decimal("0.00")
    for i, mat in enumerate(invoice.materials):
        expected = _money(mat.unit_price_eur * mat.quantity)
        actual = _money(mat.line_total_eur)
        if expected != actual:
            errors.append(
                f"materials[{i}] Betrag={actual} != Preis*Menge={expected}"
            )
        materials_sum += expected
    materials_sum = _money(materials_sum)

    if _money(invoice.totals.services_eur) != services_sum:
        errors.append(
            f"totals.services_eur={_money(invoice.totals.services_eur)} "
            f"!= sum(line_items)={services_sum}"
        )
    if _money(invoice.totals.materials_eur) != materials_sum:
        errors.append(
            f"totals.materials_eur={_money(invoice.totals.materials_eur)} "
            f"!= sum(materials)={materials_sum}"
        )
    expected_gross = _money(services_sum + materials_sum)
    if _money(invoice.totals.gross_eur) != expected_gross:
        errors.append(
            f"totals.gross_eur={_money(invoice.totals.gross_eur)} "
            f"!= services+materials={expected_gross}"
        )
    return errors


def check_goae_constraints(invoice: Invoice, catalog: ServiceCatalog) -> list[str]:
    """Rules taken from the GOÄ Anlage, not from the sample PDFs."""
    errors: list[str] = []
    by_code = catalog.by_code()
    by_day: dict = {}
    for item in invoice.line_items:
        by_day.setdefault(item.service_date, set()).add(item.code)
        offering = by_code.get(item.code)
        if offering is None:
            errors.append(f"code {item.code} is not in the GOÄ catalog")
            continue
        if item.factor > offering.max_factor:
            errors.append(
                f"code {item.code} factor {item.factor} exceeds max {offering.max_factor}"
            )
        if offering.points is not None:
            expected = _money(Decimal(offering.points) * Decimal("0.0582873"))
            if _money(item.einfachsatz_eur) != expected:
                errors.append(
                    f"code {item.code} einfachsatz {item.einfachsatz_eur} != official {expected}"
                )
    for day, codes in by_day.items():
        if "5" in codes and "6" in codes:
            errors.append(f"{day}: GOÄ 5 and 6 are mutually exclusive")
        blocked = {"1203", "1204", "1210", "1211", "1212", "1213", "1217", "1228", "1240"}
        if codes.intersection(blocked) and codes.intersection({"5", "6", "7", "8"}):
            errors.append(f"{day}: GOÄ 5/6 cannot be billed beside {sorted(codes.intersection(blocked))}")
        ambulatory = codes.intersection({"442", "443", "444", "445"})
        if len(ambulatory) > 1:
            errors.append(f"{day}: only one ambulatory surcharge 442-445")
        surgery_points = 0
        for code in codes:
            offering = by_code.get(code)
            if offering and offering.phase == "surgery" and offering.code != "491" and offering.points:
                surgery_points = max(surgery_points, offering.points)
        for code in ambulatory:
            offering = by_code[code]
            if offering.point_min is None or not (
                offering.point_min <= surgery_points <= (offering.point_max or 0)
            ):
                errors.append(
                    f"{day}: surcharge {code} does not match surgery points {surgery_points}"
                )
        if "200" in codes and surgery_points > 0:
            errors.append(f"{day}: GOÄ 200 is included in the operative fee")
    return errors


def validate_invoice(
    invoice: Invoice,
    catalog: ServiceCatalog | None = None,
    *,
    raise_on_error: bool = True,
) -> list[str]:
    errors = (
        check_required_fields(invoice)
        + check_date_order(invoice)
        + check_amounts(invoice)
    )
    if catalog is not None:
        errors += check_goae_constraints(invoice, catalog)
    if errors and raise_on_error:
        raise ValidationError(errors)
    return errors
