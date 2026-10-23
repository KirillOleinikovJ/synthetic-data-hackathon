"""Compare the scenario catalog with the official GOÄ point table."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from invoice_gen.catalog import ServiceCatalog, load_catalog
from invoice_gen.generator import generate_invoice
from invoice_gen.validators import validate_invoice

PUNKTWERT = Decimal("0.0582873")
MONEY = Decimal("0.01")


def official_einfachsatz(points: int) -> Decimal:
    return (Decimal(points) * PUNKTWERT).quantize(MONEY, rounding=ROUND_HALF_UP)


def tariff_report(catalog: ServiceCatalog) -> dict:
    rows = []
    matched = 0
    checked = 0
    for service in catalog.services:
        if service.points is None:
            continue
        checked += 1
        official = official_einfachsatz(service.points)
        delta = official - service.einfachsatz_eur
        ok = delta == 0
        matched += int(ok)
        rows.append(
            {
                "code": service.code,
                "points": service.points,
                "catalog_eur": f"{service.einfachsatz_eur:.2f}",
                "official_eur": f"{official:.2f}",
                "delta_eur": f"{delta:.2f}",
                "match": ok,
                "phase": service.phase,
            }
        )
    return {
        "metric": "goae_einfachsatz_match",
        "source": "GOÄ Anlage, Einfachsatz = round(Punkte * 0.0582873, 2)",
        "codes_checked": checked,
        "codes_matching": matched,
        "match_rate": round(matched / checked, 4) if checked else 0,
        "rows": rows,
    }


def constraint_report(catalog: ServiceCatalog, *, n: int = 30, seed: int = 1) -> dict:
    passed = 0
    for i in range(n):
        invoice = generate_invoice(catalog, seed=seed + i)
        errors = validate_invoice(invoice, catalog, raise_on_error=False)
        passed += int(not errors)
    return {
        "metric": "generated_invoices_passing_goae_constraints",
        "invoices": n,
        "passed": passed,
        "pass_rate": round(passed / n, 4) if n else 0,
        "limits": [
            "One scenario only: private eyelid surgery.",
            "Sachkosten prices come from the sample PDFs, not from GOÄ.",
            "Names, addresses and bank details are synthetic.",
            "GOÄ 1240 is in the catalog but not auto-billed beside codes 5 or 6.",
            "GOÄ 76 (diet plan) is priced officially and excluded from this scenario.",
            "Sample PDFs sometimes break these rules; this generator follows the Anlage.",
        ],
    }


def build_report(catalog_path: Path, *, n: int = 30) -> dict:
    catalog = load_catalog(catalog_path)
    return {
        "scenario_id": catalog.scenario_id,
        "tariff": tariff_report(catalog),
        "constraints": constraint_report(catalog, n=n),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = build_report(root / "data" / "service_catalog.json")
    out = root / "output" / "goae_accuracy.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tariff = report["tariff"]
    rules = report["constraints"]
    print(
        f"GOAE tariff match: {tariff['codes_matching']}/{tariff['codes_checked']} "
        f"({tariff['match_rate']:.0%})"
    )
    print(
        f"Constraint pass: {rules['passed']}/{rules['invoices']} "
        f"({rules['pass_rate']:.0%})"
    )
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
