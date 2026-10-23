from __future__ import annotations

import json
from pathlib import Path

from invoice_gen.models import Invoice


def invoice_to_dict(invoice: Invoice) -> dict:
    return invoice.model_dump(mode="json")


def write_invoice_json(invoice: Invoice, path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(invoice_to_dict(invoice), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out
