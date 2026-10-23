from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class DemoScenario:
    id: str
    diagnosis_id: str
    label: str
    allowed_laterality: tuple[str, ...]
    min_period_days: int
    required_codes: tuple[str, ...]
    one_of_codes: tuple[str, ...]
    optional_codes: tuple[str, ...]
    allows_suture_removal: bool
    allows_dressing: bool
    bilateral_quantity_codes: tuple[str, ...]
    forbidden_same_day: tuple[tuple[str, str], ...]
    materials: tuple[str, ...]
    roles: dict[str, str]
    factors: dict[str, tuple[Decimal, Decimal]]
    note: str

    def allowed_codes(self) -> set[str]:
        return set(self.required_codes) | set(self.one_of_codes) | set(self.optional_codes)

    def factor_bounds(self, code: str) -> tuple[Decimal, Decimal]:
        return self.factors[code]


@dataclass(frozen=True)
class ScenarioLibrary:
    catalog_version: str
    prompt_version: str
    sources: tuple[str, ...]
    disclaimer: str
    scenarios: tuple[DemoScenario, ...]

    def by_id(self, scenario_id: str) -> DemoScenario:
        for scenario in self.scenarios:
            if scenario.id == scenario_id:
                return scenario
        known = ", ".join(item.id for item in self.scenarios)
        raise KeyError(f"scenario {scenario_id!r} is not in the demo set ({known})")

    def ids(self) -> list[str]:
        return [item.id for item in self.scenarios]


def load_scenarios(path: Path | str) -> ScenarioLibrary:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    scenarios = []
    for item in raw["scenarios"]:
        scenarios.append(
            DemoScenario(
                id=item["id"],
                diagnosis_id=item["diagnosis_id"],
                label=item["label"],
                allowed_laterality=tuple(item["allowed_laterality"]),
                min_period_days=int(item["min_period_days"]),
                required_codes=tuple(item["required_codes"]),
                one_of_codes=tuple(item["one_of_codes"]),
                optional_codes=tuple(item["optional_codes"]),
                allows_suture_removal=bool(item["allows_suture_removal"]),
                allows_dressing=bool(item["allows_dressing"]),
                bilateral_quantity_codes=tuple(item["bilateral_quantity_codes"]),
                forbidden_same_day=tuple(tuple(pair) for pair in item["forbidden_same_day"]),
                materials=tuple(item["materials"]),
                roles=dict(item["roles"]),
                factors={code: (Decimal(bounds[0]), Decimal(bounds[1])) for code, bounds in item["factors"].items()},
                note=item["note"],
            )
        )
    return ScenarioLibrary(
        catalog_version=raw["catalog_version"],
        prompt_version=raw["prompt_version"],
        sources=tuple(raw["sources"]),
        disclaimer=raw["disclaimer"],
        scenarios=tuple(scenarios),
    )
