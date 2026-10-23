from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import re
import zlib

from invoice_gen.assemble import assemble_invoice
from invoice_gen.catalog import load_catalog
from invoice_gen.export_pdf import write_invoice_pdf
from invoice_gen.llm_client import LLMGenerationError, request_case_plan
from invoice_gen.names import display_name, family_name, greeting_line, split_person
from invoice_gen.pipeline import UnsupportedScenarioRequest, run_batch
from invoice_gen.plans import CasePlan, validate_plan
from invoice_gen.pricing import einfachsatz_from_points, line_amount
from invoice_gen.rule_based import rule_based_plan
from invoice_gen.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "data" / "service_catalog.json")
LIBRARY = load_scenarios(ROOT / "data" / "demo_scenarios.json")
START = date(2026, 1, 6)
END = date(2026, 3, 3)


def _valid_plan() -> CasePlan:
    return rule_based_plan(LIBRARY.by_id("dermatochalasis_bds"), __import__("random").Random(1), variation=1)


def test_unknown_code_is_rejected():
    plan = _valid_plan()
    plan.events.append(plan.events[0].model_copy(update={"code": "9999"}))
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("9999" in item for item in errors)


def test_incompatible_exam_codes_are_rejected():
    plan = _valid_plan()
    other = "5" if all(event.code != "5" for event in plan.events) else "6"
    present = "6" if other == "5" else "5"
    if all(event.code != present for event in plan.events):
        plan.events.append(plan.events[0].model_copy(update={"code": present, "day_offset": 0}))
    plan.events.append(plan.events[0].model_copy(update={"code": other, "day_offset": 0}))
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("5" in item and "6" in item for item in errors)


def test_date_after_period_is_rejected():
    plan = _valid_plan()
    plan.events[0] = plan.events[0].model_copy(update={"day_offset": 90})
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("after the service period" in item or "before the consultation" in item or "after the operation" in item for item in errors)


def test_factor_outside_code_limit_is_rejected():
    plan = _valid_plan()
    plan.events[0] = plan.events[0].model_copy(update={"factor": Decimal("9")})
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("factor" in item and "1" == plan.events[0].code for item in errors)


def test_goae_rounding_matches_sample_ziffer_34():
    einfach = einfachsatz_from_points(300)
    assert einfach == Decimal("17.49")
    assert line_amount(einfach, Decimal("2.3"), Decimal("1")) == Decimal("40.23")


def test_rule_based_invoice_builds_json_amounts():
    scenario = LIBRARY.by_id("ptosis_bds")
    plan = rule_based_plan(scenario, __import__("random").Random(2), variation=2)
    invoice = assemble_invoice(
        plan,
        scenario,
        CATALOG,
        period_start=START,
        period_end=END,
        age_min=50,
        age_max=80,
        seed=2,
        mode="Rule-based demo",
    )
    assert invoice.issue_date >= max(item.service_date for item in invoice.line_items)
    assert "2007" not in [item.code for item in invoice.line_items] or all(
        item.service_date > next(row.service_date for row in invoice.line_items if row.code == "1306")
        for item in invoice.line_items
        if item.code == "2007"
    )


def test_runs_do_not_overwrite(tmp_path: Path):
    scenario_id = "entropium"
    first = run_batch(
        mode="rule-based",
        scenario_id=scenario_id,
        user_request="Unilateral entropion demo",
        count=1,
        period_start=START,
        period_end=END,
        age_min=40,
        age_max=80,
        seed=3,
        catalog=CATALOG,
        library=LIBRARY,
        output_root=tmp_path,
    )
    second = run_batch(
        mode="rule-based",
        scenario_id=scenario_id,
        user_request="Unilateral entropion demo",
        count=1,
        period_start=START,
        period_end=END,
        age_min=40,
        age_max=80,
        seed=4,
        catalog=CATALOG,
        library=LIBRARY,
        output_root=tmp_path,
    )
    assert first["run_dir"] != second["run_dir"]
    assert first["invoices"][0]["invoice_number"] != second["invoices"][0]["invoice_number"]
    assert Path(first["invoices"][0]["pdf"]).exists()
    assert Path(second["invoices"][0]["pdf"]).exists()
    assert "200" not in first["invoices"][0]["codes"]
    assert "200" not in second["invoices"][0]["codes"]


def test_minimum_period_builds(tmp_path: Path):
    report = run_batch(
        mode="rule-based",
        scenario_id="dermatochalasis_bds",
        user_request="Outpatient eyelid demo",
        count=1,
        period_start=date(2026, 1, 6),
        period_end=date(2026, 1, 27),
        age_min=50,
        age_max=80,
        seed=1,
        catalog=CATALOG,
        library=LIBRARY,
        output_root=tmp_path,
    )
    assert report["checks"]["invoices_passing_implemented_rules"] == 1


def test_unsupported_request_writes_nothing(tmp_path: Path):
    with pytest.raises(UnsupportedScenarioRequest):
        run_batch(
            mode="rule-based",
            scenario_id="dermatochalasis_bds",
            user_request="Bitte einen Zahnarzt-Fall erzeugen",
            count=1,
            period_start=START,
            period_end=END,
            age_min=50,
            age_max=80,
            seed=1,
            catalog=CATALOG,
            library=LIBRARY,
            output_root=tmp_path,
        )
    assert list(tmp_path.rglob("*")) == []


class _GoodClient:
    def complete(self, messages):
        plan = rule_based_plan(LIBRARY.by_id("dermatochalasis_bds"), __import__("random").Random(1), variation=1)
        return plan.model_dump(mode="json")


def test_mock_llm_writes_checked_invoice(tmp_path: Path):
    report = run_batch(
        mode="llm",
        scenario_id="dermatochalasis_bds",
        user_request="Outpatient eyelid demo",
        count=1,
        period_start=START,
        period_end=END,
        age_min=50,
        age_max=80,
        seed=1,
        catalog=CATALOG,
        library=LIBRARY,
        output_root=tmp_path,
        client=_GoodClient(),
        model_name="mock-model",
    )
    assert report["mode"] == "LLM"
    assert report["checks"]["llm_schema_pass_rate"] == 1.0
    assert report["model"] == "mock-model"
    assert Path(report["invoices"][0]["json"]).exists()


class _DownClient:
    def complete(self, messages):
        raise RuntimeError("API unavailable")


class _BadClient:
    def complete(self, messages):
        return {"diagnosis_id": "nope"}


def test_api_error_is_not_replaced_with_a_template(tmp_path: Path):
    with pytest.raises(RuntimeError, match="API unavailable"):
        run_batch(
            mode="llm",
            scenario_id="dermatochalasis_bds",
            user_request="Outpatient eyelid demo",
            count=1,
            period_start=START,
            period_end=END,
            age_min=50,
            age_max=80,
            seed=1,
            catalog=CATALOG,
            library=LIBRARY,
            output_root=tmp_path,
            client=_DownClient(),
            model_name="mock",
        )
    assert list(tmp_path.rglob("*.pdf")) == []


def test_invalid_llm_payload_stops_after_corrections(tmp_path: Path):
    with pytest.raises(LLMGenerationError):
        request_case_plan(
            _BadClient(),
            user_request="Outpatient eyelid demo",
            scenario=LIBRARY.by_id("dermatochalasis_bds"),
            catalog=CATALOG,
            library=LIBRARY,
            period_start=START,
            period_end=END,
            age_min=50,
            age_max=80,
            invoice_index=1,
            invoice_count=1,
        )


def test_family_name_ignores_degree_suffix():
    assert family_name("Alida Weihmann B.Sc.") == "Weihmann"
    assert family_name("Dr. Marta Klein M.Sc.") == "Klein"
    person = split_person("Alida Junken B.Eng.")
    assert person.last_name == "Junken"
    assert split_person("Giesela Stey MBA.").last_name == "Stey"
    assert split_person("Giesela Stey MBA.").academic_title == "MBA."
    assert person.academic_title == "B.Eng."
    assert person.first_name == "Alida"
    assert greeting_line("Frau", person.last_name) == "Sehr geehrte Frau Junken,"
    assert greeting_line("Herr", "Kraus") == "Sehr geehrter Herr Kraus,"
    titled = split_person("Univ.Prof. Fernando Albers B.Eng.")
    assert titled.first_name == "Fernando"
    assert titled.last_name == "Albers"
    assert titled.academic_title == "Univ.Prof. B.Eng."
    assert display_name(titled) == "Univ.Prof. Fernando Albers, B.Eng."
    assert greeting_line("Herr", titled.last_name) == "Sehr geehrter Herr Albers,"


def test_consultation_and_preop_need_separate_encounters():
    plan = _valid_plan()
    for index, event in enumerate(plan.events):
        if event.code == "34":
            plan.events[index] = event.model_copy(update={"encounter_id": "d0", "day_offset": 0})
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("1 and 34" in item for item in errors)


def test_separate_encounters_may_share_a_calendar_day():
    plan = _valid_plan()
    for index, event in enumerate(plan.events):
        if event.code == "34":
            plan.events[index] = event.model_copy(update={"encounter_id": "d7", "day_offset": 0})
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert not any("1 and 34" in item for item in errors)


def test_threshold_justification_is_not_kept_at_or_below_2_3():
    scenario = LIBRARY.by_id("entropium")
    plan = rule_based_plan(scenario, __import__("random").Random(2), variation=2)
    plan.events[0] = plan.events[0].model_copy(
        update={"factor_justification": "This visit took longer, but the factor stays at the threshold."}
    )
    invoice = assemble_invoice(
        plan,
        scenario,
        CATALOG,
        period_start=START,
        period_end=END,
        age_min=50,
        age_max=80,
        seed=2,
        mode="Rule-based demo",
    )
    first = next(item for item in invoice.line_items if item.code == "1")
    assert first.factor == Decimal("2.3")
    assert first.factor_justification is None


def test_factor_above_threshold_needs_a_case_specific_reason():
    plan = _valid_plan()
    for index, event in enumerate(plan.events):
        if event.code == "1311":
            plan.events[index] = event.model_copy(
                update={"factor": Decimal("3.5"), "factor_justification": "Erhoehter Zeitaufwand"}
            )
    errors = validate_plan(plan, LIBRARY.by_id("dermatochalasis_bds"), period_start=START, period_end=END)
    assert any("justification" in item for item in errors)


class _SameVisitClient:
    def complete(self, messages):
        plan = _valid_plan()
        plan.events = [
            event.model_copy(update={"encounter_id": "d0", "day_offset": 0}) if event.code == "34" else event
            for event in plan.events
        ]
        return plan.model_dump(mode="json")


def test_rejected_plan_is_not_exported(tmp_path: Path):
    with pytest.raises(LLMGenerationError):
        run_batch(
            mode="llm",
            scenario_id="dermatochalasis_bds",
            user_request="Outpatient eyelid demo",
            count=1,
            period_start=START,
            period_end=END,
            age_min=50,
            age_max=80,
            seed=1,
            catalog=CATALOG,
            library=LIBRARY,
            output_root=tmp_path,
            client=_SameVisitClient(),
            model_name="mock",
        )
    assert list(tmp_path.rglob("*.pdf")) == []
    assert list(tmp_path.rglob("*.json")) == []


def test_mixed_batch_covers_selected_scenarios(tmp_path: Path):
    report = run_batch(
        mode="rule-based",
        scenario_id="dermatochalasis_bds",
        scenario_ids=["dermatochalasis_bds", "entropium", "ptosis_bds"],
        user_request="Synthetic outpatient eyelid cases",
        count=3,
        period_start=START,
        period_end=END,
        age_min=50,
        age_max=80,
        seed=5,
        catalog=CATALOG,
        library=LIBRARY,
        output_root=tmp_path,
    )
    assert report["checks"]["distinct_scenarios"] == 3
    assert report["mode"] == "Rule-based demo"
    assert "100%" not in report["checks"]["note"]


def _pdf_text(path: Path) -> str:
    raw = path.read_bytes()
    chunks = []
    for match in re.finditer(rb"/Length\s+(\d+)\s*>>\s*stream\r?\n", raw):
        start = match.end()
        blob = raw[start : start + int(match.group(1))]
        try:
            blob = zlib.decompress(blob)
        except zlib.error:
            pass
        chunks.append(blob.decode("latin-1", "replace"))
    return "\n".join(chunks)


def test_pdf_greeting_and_full_description(tmp_path: Path):
    scenario = LIBRARY.by_id("dermatochalasis_bds")
    plan = rule_based_plan(scenario, __import__("random").Random(1), variation=1)
    invoice = assemble_invoice(
        plan,
        scenario,
        CATALOG,
        period_start=START,
        period_end=END,
        age_min=50,
        age_max=80,
        seed=1,
        mode="Rule-based demo",
    )
    invoice.patient.salutation = "Frau"
    invoice.patient.first_name = "Alida"
    invoice.patient.last_name = "Junken"
    invoice.patient.academic_title = "B.Eng."
    invoice.patient.full_name = "Alida Junken, B.Eng."
    invoice.line_items[0].description = (
        "Spaltlampenmikroskopie der vorderen und mittleren Augenabschnitte einschließlich Hruby-Linse"
    )
    path = tmp_path / "invoice.pdf"
    write_invoice_pdf(invoice, path)
    text = _pdf_text(path)
    assert "Sehr geehrte Frau Junken," in text
    assert "geehrte/r" not in text
    assert "d0" in text
    assert "Hruby-Linse" in text
    assert "..." not in text
    assert "75 Minuten" in text
