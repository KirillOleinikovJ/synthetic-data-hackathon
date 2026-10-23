"""Structured case plan. Prices are not part of the schema."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from invoice_gen.scenarios import DemoScenario

_BLOCKED_WORDS = (
    "zahn",
    "dental",
    "kardio",
    "cardio",
    "herzinfarkt",
    "orthop",
    "gynäk",
    "gynaek",
    "schwanger",
    "radiolog",
    "laborwert",
)


_GENERIC_JUSTIFICATION = {
    "erschwerte bedingungen",
    "erhoehter zeitaufwand",
    "erhöhter zeitaufwand",
    "besondere schwierigkeit",
    "besondere umstaende",
    "besondere umstände",
}
_VAGUE_STEMS = ("zeit", "schwier", "beding", "umstand", "besonder", "eingriff", "operation", "behandl")
_THRESHOLD = Decimal("2.3")
_SAME_ENCOUNTER = (("1", "34"), ("5", "6"), ("5", "1240"), ("6", "1240"))


class TreatmentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_offset: int = Field(ge=0, le=180)
    encounter_id: str = Field(min_length=1, max_length=12)
    code: str
    factor: Decimal | None = None
    factor_justification: str | None = None

    @field_validator("factor", mode="before")
    @classmethod
    def _factor(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @field_validator("factor_justification", mode="before")
    @classmethod
    def _justification(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class CasePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnosis_id: str
    laterality: Literal["right", "left", "both", "not_applicable"]
    case_summary: str = Field(min_length=8, max_length=400)
    events: list[TreatmentEvent] = Field(min_length=1, max_length=16)
    materials: list[str] = Field(default_factory=list)


class PlanRejected(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def unsupported_request(
    query: str,
    scenario: DemoScenario,
    selected_ids: set[str] | None = None,
) -> str | None:
    """Explain a request that is outside the selected demo scenario."""
    text = query.lower()
    chosen = selected_ids or {scenario.id}
    if any(word in text for word in _BLOCKED_WORDS):
        return (
            "This demo only builds German GOÄ ophthalmology invoices for "
            f"{scenario.label}. The request mentions a different specialty, "
            "so no invoice was generated."
        )
    aliases = {
        "dermatochalasis_bds": ("dermatochalasis", "schlupflid"),
        "entropium": ("entropium", "ektropium"),
        "ptosis_bds": ("ptosis",),
    }
    mentioned = [name for name, words in aliases.items() if any(word in text for word in words)]
    outside = [name for name in mentioned if name not in chosen]
    if outside:
        return (
            f"The request names a pathway ({', '.join(outside)}) that was not selected. "
            "Choose that scenario explicitly. Nothing was substituted."
        )
    return None


def _justification_is_specific(text: str, summary: str) -> bool:
    folded = re.sub(r"\s+", " ", text.casefold()).strip(" .")
    if folded in _GENERIC_JUSTIFICATION:
        return False
    if any(character.isdigit() for character in text):
        return True
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{6,}", text.casefold())
    concrete = [word for word in words if not word.startswith(_VAGUE_STEMS)]
    summary_words = set(re.findall(r"[A-Za-zÄÖÜäöüß]{6,}", summary.casefold()))
    return bool(concrete) or bool(set(words) & summary_words)


def validate_plan(
    plan: CasePlan,
    scenario: DemoScenario,
    *,
    period_start: date,
    period_end: date,
) -> list[str]:
    errors: list[str] = []
    span = (period_end - period_start).days
    if span < scenario.min_period_days:
        errors.append(
            f"service period is {span} days; {scenario.id} needs at least {scenario.min_period_days}"
        )
    if plan.diagnosis_id != scenario.diagnosis_id:
        errors.append(
            f"diagnosis_id {plan.diagnosis_id!r} does not match scenario {scenario.diagnosis_id!r}"
        )
    if plan.laterality not in scenario.allowed_laterality:
        errors.append(
            f"laterality {plan.laterality!r} is outside {list(scenario.allowed_laterality)}"
        )
    allowed = scenario.allowed_codes()
    codes = [event.code for event in plan.events]
    seen = set(codes)
    for code in codes:
        if code not in allowed:
            errors.append(f"code {code} is not allowed in scenario {scenario.id}")
    for code in scenario.required_codes:
        if code not in seen:
            errors.append(f"required code {code} is missing")
    exam_hits = [code for code in scenario.one_of_codes if code in seen]
    if scenario.one_of_codes and len(exam_hits) != 1:
        errors.append(f"choose exactly one of {list(scenario.one_of_codes)}, got {exam_hits or 'none'}")
    if "2007" in seen and not scenario.allows_suture_removal:
        errors.append("suture removal 2007 is not an event of this scenario")
    if "200" in seen and not scenario.allows_dressing:
        errors.append("dressing 200 is not an event of this scenario")
    for name in plan.materials:
        if name not in scenario.materials:
            errors.append(f"material {name!r} is not allowed for this scenario")

    by_day: dict[int, set[str]] = {}
    by_encounter: dict[str, set[str]] = {}
    encounter_days: dict[str, set[int]] = {}
    surgery_day: int | None = None
    for event in plan.events:
        by_encounter.setdefault(event.encounter_id, set()).add(event.code)
        encounter_days.setdefault(event.encounter_id, set()).add(event.day_offset)
        if event.factor is not None and event.factor > _THRESHOLD:
            reason = event.factor_justification or ""
            if len(reason) < 40 or not _justification_is_specific(reason, plan.case_summary):
                errors.append(
                    f"code {event.code} factor {event.factor} is above the GOÄ § 5 threshold 2.3 "
                    "without a case-specific justification. Name the difficulty or extra time of this case. "
                    "A stock phrase is not accepted, and the date was not changed."
                )
        by_day.setdefault(event.day_offset, set()).add(event.code)
        if event.code not in scenario.roles:
            continue
        if scenario.roles[event.code] == "surgery" and event.code not in {"491", "440", "444"}:
            surgery_day = event.day_offset if surgery_day is None else min(surgery_day, event.day_offset)
        if event.factor is not None and event.code in scenario.factors:
            low, high = scenario.factor_bounds(event.code)
            if event.factor < low or event.factor > high:
                errors.append(
                    f"code {event.code} factor {event.factor} is outside {low}..{high}"
                )
        service_day = period_start + timedelta(days=event.day_offset)
        if service_day > period_end:
            errors.append(
                f"code {event.code} day_offset {event.day_offset} is after the service period"
            )
    for encounter, days in encounter_days.items():
        if len(days) > 1:
            errors.append(
                f"encounter {encounter} is used on day offsets {sorted(days)}. "
                "One encounter_id is one visit on one day. Dates were not moved."
            )
    for encounter, enc_codes in by_encounter.items():
        for left, right in _SAME_ENCOUNTER:
            if left in enc_codes and right in enc_codes:
                errors.append(
                    f"encounter {encounter} bills GOÄ {left} and {right} in one Sitzung. "
                    "Nr. 34 includes Beratung (GOÄ Anlage, Nr. 34); § 4 Abs. 2a bars billing a component "
                    "again in the same visit. Nr. 5, 6 and 1240 are also exclusive in one visit. "
                    "Give the services different encounter_id values. Dates were not moved."
                )
    if codes.count("1") > 1:
        errors.append(
            "GOÄ 1 may be billed only once in this treatment case beside section C-O services "
            "(Allgemeine Bestimmung to Abschnitt B)."
        )
    if codes.count("5") > 1:
        errors.append(
            "GOÄ 5 may be billed only once in this treatment case beside section C-O services "
            "(Allgemeine Bestimmung to Abschnitt B)."
        )
    for left, right in scenario.forbidden_same_day:
        for day, day_codes in by_day.items():
            if left in day_codes and right in day_codes:
                errors.append(f"codes {left} and {right} are both on day offset {day}")
    if surgery_day is not None:
        for event in plan.events:
            role = scenario.roles.get(event.code)
            if role == "followup" and event.day_offset <= surgery_day:
                errors.append(
                    f"code {event.code} must be after the operation (day {surgery_day}), not on day {event.day_offset}"
                )
            if role in {"consult", "exam", "preop"} and event.day_offset > surgery_day:
                errors.append(f"code {event.code} is dated after the operation")
        stage_days: dict[str, list[int]] = {}
        for event in plan.events:
            role = scenario.roles.get(event.code)
            if role:
                stage_days.setdefault(role, []).append(event.day_offset)
        if "preop" in stage_days and "consult" in stage_days:
            if min(stage_days["preop"]) < max(stage_days["consult"]):
                errors.append("the pre-operative talk is dated before the consultation")
        if "preop" in stage_days and min(stage_days["preop"]) >= surgery_day:
            errors.append("the pre-operative talk must be before the operation")
        if "exam" in stage_days and max(stage_days["exam"]) > surgery_day:
            errors.append("an examination is dated after the operation")
    return errors
