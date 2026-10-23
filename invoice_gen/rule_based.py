"""Deterministic plans inside a demo scenario. This is not an LLM."""

from __future__ import annotations

from decimal import Decimal
from random import Random

from invoice_gen.plans import CasePlan, TreatmentEvent
from invoice_gen.scenarios import DemoScenario

_DERMATO_35 = (
    "Die beidseitige Hautlappenverschiebung bei Dermatochalasis dauerte 75 Minuten "
    "wegen ausgepraegter Hautfalten, laenger als der einfache Regelfall."
)


def rule_based_plan(scenario: DemoScenario, rng: Random, *, variation: int) -> CasePlan:
    exam = scenario.one_of_codes[variation % len(scenario.one_of_codes)]
    events = [
        TreatmentEvent(day_offset=0, encounter_id="d0", code="1", factor="2.3"),
        TreatmentEvent(day_offset=0, encounter_id="d0", code=exam, factor="2.3"),
    ]
    optional_exams = [code for code in scenario.optional_codes if scenario.roles.get(code) == "exam"]
    if optional_exams:
        chosen = optional_exams[variation % len(optional_exams)]
        day = 2 if chosen == "1240" else 0
        events.append(TreatmentEvent(day_offset=day, encounter_id=f"d{day}", code=chosen, factor="2.3"))
    for code in scenario.required_codes:
        role = scenario.roles[code]
        if role == "preop":
            events.append(TreatmentEvent(day_offset=7, encounter_id="d7", code=code, factor="2.3"))
        elif role == "surgery":
            low, high = scenario.factor_bounds(code)
            justification = None
            if code == "1311" and variation % 2 == 1:
                factor: Decimal | str = high
                justification = _DERMATO_35
            elif low == high:
                factor = low
            else:
                factor = Decimal_factor(code)
            events.append(
                TreatmentEvent(
                    day_offset=14,
                    encounter_id="d14",
                    code=code,
                    factor=factor,
                    factor_justification=justification,
                )
            )
    if "1303" in scenario.optional_codes and variation % 2 == 0:
        events.append(TreatmentEvent(day_offset=14, encounter_id="d14", code="1303", factor="2.3"))
    if scenario.allows_suture_removal and variation % 3 != 0:
        events.append(TreatmentEvent(day_offset=21, encounter_id="d21", code="2007", factor="2.3"))
    if scenario.allows_dressing and variation % 2 == 1:
        events.append(TreatmentEvent(day_offset=21, encounter_id="d21", code="200", factor="2.3"))
    materials = [scenario.materials[variation % len(scenario.materials)]] if scenario.materials else []
    if len(scenario.materials) > 1 and variation % 2 == 0:
        materials.append(scenario.materials[1])
    laterality = scenario.allowed_laterality[variation % len(scenario.allowed_laterality)]
    return CasePlan(
        diagnosis_id=scenario.diagnosis_id,
        laterality=laterality,
        case_summary=f"Rule-based demo for {scenario.label}. Optional codes vary with the seed.",
        events=events,
        materials=materials,
    )


def Decimal_factor(code: str) -> str:
    if code in {"440", "442", "443", "444", "445"}:
        return "1.0"
    return "2.3"
