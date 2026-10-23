"""Run one demo batch into its own folder. Previous runs are left in place."""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from random import Random

from invoice_gen.assemble import assemble_invoice
from invoice_gen.catalog import ServiceCatalog
from invoice_gen.export_json import write_invoice_json
from invoice_gen.export_pdf import write_invoice_pdf
from invoice_gen.llm_client import LLMClient, LLMGenerationError, request_case_plan
from invoice_gen.plans import unsupported_request
from invoice_gen.rule_based import rule_based_plan
from invoice_gen.scenarios import ScenarioLibrary


class UnsupportedScenarioRequest(Exception):
    pass


def new_run_dir(output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    folder = output_root / f"run-{stamp}-{uuid.uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _write_unique(path: Path, writer) -> Path:
    if path.exists():
        path = path.with_name(f"{path.stem}-{uuid.uuid4().hex[:6]}{path.suffix}")
    writer(path)
    return path


def _assign_scenarios(chosen: list[str], count: int) -> list[str]:
    if count >= len(chosen):
        return [chosen[index % len(chosen)] for index in range(count)]
    return chosen[:count]


def run_batch(
    *,
    mode: str,
    scenario_id: str,
    user_request: str,
    count: int,
    period_start: date,
    period_end: date,
    age_min: int,
    age_max: int,
    seed: int | None,
    catalog: ServiceCatalog,
    library: ScenarioLibrary,
    output_root: Path,
    client: LLMClient | None = None,
    model_name: str | None = None,
    scenario_ids: list[str] | None = None,
) -> dict:
    if mode not in {"llm", "rule-based"}:
        raise ValueError("mode must be 'llm' or 'rule-based'")
    if count < 1 or count > 10:
        raise ValueError("demo count must be from 1 to 10")
    chosen = list(dict.fromkeys(scenario_ids or [scenario_id]))
    if not chosen:
        raise ValueError("select at least one supported scenario")
    for item in chosen:
        library.by_id(item)
    assignment = _assign_scenarios(chosen, count)
    refusal = unsupported_request(
        user_request,
        library.by_id(assignment[0]),
        selected_ids=set(chosen),
    )
    if refusal:
        raise UnsupportedScenarioRequest(refusal)
    if mode == "llm" and client is None:
        raise ValueError("LLM mode needs a client. Rule-based demo is a separate explicit mode.")

    started = time.perf_counter()
    rng = Random(seed)
    built: list[tuple] = []
    totals = {
        "schema_attempts": 0,
        "schema_passes": 0,
        "retries": 0,
        "rejected": 0,
        "passed_on_first_attempt": 0,
        "corrected_after_retry": 0,
    }
    request_ids: list[str] = []
    prior_code_sets: list[list[str]] = []

    for index, assigned_id in enumerate(assignment):
        scenario = library.by_id(assigned_id)
        if mode == "llm":
            try:
                plan, stats = request_case_plan(
                    client,
                    user_request=user_request,
                    scenario=scenario,
                    catalog=catalog,
                    library=library,
                    period_start=period_start,
                    period_end=period_end,
                    age_min=age_min,
                    age_max=age_max,
                    invoice_index=index + 1,
                    invoice_count=count,
                    prior_code_sets=prior_code_sets,
                )
            except LLMGenerationError as exc:
                for key in totals:
                    totals[key] += exc.stats.get(key, 0)
                exc.stats = {**totals, "request_ids": request_ids + list(exc.stats.get("request_ids") or [])}
                raise
            for key in totals:
                totals[key] += stats.get(key, 0)
            request_ids.extend(str(item) for item in stats.get("request_ids") or [])
        else:
            plan = rule_based_plan(scenario, rng, variation=index if seed is None else (seed + index))
        invoice = assemble_invoice(
            plan,
            scenario,
            catalog,
            period_start=period_start,
            period_end=period_end,
            age_min=age_min,
            age_max=age_max,
            seed=None if seed is None else seed + index,
            mode="LLM" if mode == "llm" else "Rule-based demo",
        )
        prior_code_sets.append([item.code for item in invoice.line_items])
        built.append((invoice, plan, assigned_id))

    run_dir = new_run_dir(output_root)
    invoices = []
    code_sets: list[tuple[str, ...]] = []
    ids: list[str] = []
    used_scenarios: list[str] = []
    gross_values: list[str] = []
    for invoice, plan, assigned_id in built:
        stem = f"{invoice.invoice_number}-{invoice.patient_number}"
        json_path = _write_unique(run_dir / f"{stem}.json", lambda path: write_invoice_json(invoice, path))
        pdf_path = _write_unique(run_dir / f"{stem}.pdf", lambda path: write_invoice_pdf(invoice, path))
        ids.append(invoice.invoice_number)
        code_sets.append(tuple(item.code for item in invoice.line_items))
        used_scenarios.append(assigned_id)
        gross_values.append(str(invoice.totals.gross_eur))
        invoices.append(
            {
                "invoice_number": invoice.invoice_number,
                "scenario_id": assigned_id,
                "diagnosis": invoice.diagnosis,
                "gross_eur": str(invoice.totals.gross_eur),
                "codes": [item.code for item in invoice.line_items],
                "json": str(json_path),
                "pdf": str(pdf_path),
                "case_summary": plan.case_summary,
            }
        )

    elapsed = round(time.perf_counter() - started, 3)
    schema_rate = None
    if mode == "llm" and totals["schema_attempts"]:
        schema_rate = round(totals["schema_passes"] / totals["schema_attempts"], 4)
    report = {
        "mode": "LLM" if mode == "llm" else "Rule-based demo",
        "api_response_used": mode == "llm",
        "model": model_name if mode == "llm" else None,
        "request_ids": request_ids,
        "prompt_version": library.prompt_version,
        "catalog_version": library.catalog_version,
        "scenario_id": assignment[0],
        "scenario_ids": used_scenarios,
        "seed_note": "Seed only affects Rule-based demo choices and fictional names. It does not make LLM output reproducible.",
        "seed": seed,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed,
        "disclaimer": library.disclaimer,
        "sources": list(library.sources),
        "checks": {
            "llm_schema_pass_rate": schema_rate,
            "passed_on_first_attempt": totals["passed_on_first_attempt"],
            "corrected_after_retry": totals["corrected_after_retry"],
            "invoices_passing_implemented_rules": len(invoices),
            "invoices_requested": count,
            "rejected_results": totals["rejected"],
            "correction_attempts": totals["retries"],
            "invoice_ids_unique": len(ids) == len(set(ids)),
            "distinct_scenarios": len(set(used_scenarios)),
            "distinct_service_sets": len(set(code_sets)),
            "gross_eur_values": gross_values,
            "note": "These counts are checks implemented in this demo. They are not a medical-accuracy score and not evidence of similarity to real invoices.",
        },
        "invoices": invoices,
    }
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["run_dir"] = str(run_dir)
    return report
