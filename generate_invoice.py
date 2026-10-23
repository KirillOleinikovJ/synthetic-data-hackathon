#!/usr/bin/env python3
"""Generate synthetic German GOÄ medical invoices (JSON + PDF from same data)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _ensure_venv() -> None:
    """Windows users often hit ModuleNotFoundError if Activate.ps1 is blocked."""
    if os.environ.get("VIRTUAL_ENV"):
        return
    if not VENV_PYTHON.is_file():
        return
    # Already running the venv interpreter
    if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return
    print(
        "NOTE: system Python has no project packages.\n"
        f"Re-running with: {VENV_PYTHON}\n"
        "(Tip: use run_demo.bat — no Activate.ps1 needed)\n"
    )
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(ROOT / "generate_invoice.py"), *sys.argv[1:]])


_ensure_venv()

from invoice_gen.catalog import load_catalog
from invoice_gen.export_json import write_invoice_json
from invoice_gen.export_pdf import write_invoice_pdf
from invoice_gen.generator import generate_invoice
from invoice_gen.validators import ValidationError, validate_invoice

DEFAULT_CATALOG = ROOT / "data" / "service_catalog.json"
DEFAULT_OUT = ROOT / "output"


def clear_output_dir(path: Path) -> int:
    """Remove previous files so the folder contains only this run's invoices."""
    path.mkdir(parents=True, exist_ok=True)
    removed = 0
    for item in path.iterdir():
        if item.is_file() and item.name != ".gitkeep":
            item.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    print("Scenario:", catalog.scenario_id)
    print("Billing:", catalog.billing_rule.encode("ascii", "replace").decode("ascii"))

    removed = clear_output_dir(args.out_dir)
    print(f"Cleared {removed} old file(s) from {args.out_dir}")
    for i in range(args.count):
        seed = None if args.seed is None else args.seed + i
        invoice = generate_invoice(catalog, seed=seed)
        validate_invoice(invoice)
        stem = f"Rechnung-{invoice.invoice_number}-{invoice.patient_number}"
        json_path = write_invoice_json(invoice, args.out_dir / f"{stem}.json")
        pdf_path = write_invoice_pdf(invoice, args.out_dir / f"{stem}.pdf")
        diag = invoice.diagnosis.encode("ascii", "replace").decode("ascii")
        print(f"OK Rechnungs-Nr. {invoice.invoice_number}")
        print(f"  Diagnose: {diag}")
        print(f"  JSON: {json_path}")
        print(f"  PDF:  {pdf_path}")
        print(f"  Gesamt: {invoice.totals.gross_eur} EUR")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print("VALIDATION FAILED:")
        for err in exc.errors:
            print(f"  - {err}")
        raise SystemExit(1)
