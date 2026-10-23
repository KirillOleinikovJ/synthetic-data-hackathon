from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class ServiceOffering:
    code: str
    description: str
    einfachsatz_eur: Decimal
    typical_factor: Decimal
    max_factor: Decimal
    phase: str
    bilateral_qty: bool
    points: int | None = None
    point_min: int | None = None
    point_max: int | None = None


@dataclass(frozen=True)
class MaterialOffering:
    description: str
    unit_price_eur: Decimal
    max_qty: int


@dataclass(frozen=True)
class DiagnosisOption:
    id: str
    label: str
    surgery_codes: tuple[str, ...]
    exam_codes: tuple[str, ...] = ()
    bilateral: bool = False


@dataclass(frozen=True)
class ServiceCatalog:
    scenario_id: str
    currency: str
    billing_rule: str
    specialty: str
    diagnoses: tuple[DiagnosisOption, ...]
    services: tuple[ServiceOffering, ...]
    materials: tuple[MaterialOffering, ...]
    source_path: Path

    def by_code(self) -> dict[str, ServiceOffering]:
        return {s.code: s for s in self.services}

    def by_phase(self, phase: str) -> list[ServiceOffering]:
        return [s for s in self.services if s.phase == phase]


def load_catalog(path: Path | str) -> ServiceCatalog:
    catalog_path = Path(path)
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    meta = raw.get("_meta", {})
    services = tuple(
        ServiceOffering(
            code=str(item["code"]),
            description=item["description"],
            einfachsatz_eur=Decimal(str(item["einfachsatz_eur"])),
            typical_factor=Decimal(str(item["typical_factor"])),
            max_factor=Decimal(str(item.get("max_factor", item["typical_factor"]))),
            phase=item["phase"],
            bilateral_qty=bool(item.get("bilateral_qty", False)),
            points=int(item["points"]) if item.get("points") is not None else None,
            point_min=int(item["point_min"]) if item.get("point_min") is not None else None,
            point_max=int(item["point_max"]) if item.get("point_max") is not None else None,
        )
        for item in raw["services"]
    )
    materials = tuple(
        MaterialOffering(
            description=item["description"],
            unit_price_eur=Decimal(str(item["unit_price_eur"])),
            max_qty=int(item.get("max_qty", 1)),
        )
        for item in raw.get("materials", [])
    )
    diagnoses = tuple(
        DiagnosisOption(
            id=d["id"],
            label=d["label"],
            surgery_codes=tuple(str(c) for c in d.get("surgery_codes", [])),
            exam_codes=tuple(str(c) for c in d.get("exam_codes", [])),
            bilateral=bool(d.get("bilateral", False)),
        )
        for d in raw.get("diagnoses", [])
    )
    if not services:
        raise ValueError(f"catalog has no services: {catalog_path}")
    if not diagnoses:
        raise ValueError(f"catalog has no diagnoses: {catalog_path}")
    return ServiceCatalog(
        scenario_id=meta.get("scenario_id", "unknown"),
        currency=meta.get("currency", "EUR"),
        billing_rule=meta.get("billing_rule", "GOAE"),
        specialty=meta.get("specialty", "Augenheilkunde"),
        diagnoses=diagnoses,
        services=services,
        materials=materials,
        source_path=catalog_path,
    )
