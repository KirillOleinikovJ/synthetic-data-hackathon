"""Small demo UI. LLM mode is offered only when the API settings are present."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from invoice_gen.catalog import load_catalog
from invoice_gen.llm_client import LLMGenerationError, LLMUnavailable, client_from_env
from invoice_gen.pipeline import UnsupportedScenarioRequest, run_batch
from invoice_gen.plans import PlanRejected
from invoice_gen.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _zip_run(run_dir: Path) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    return buffer.getvalue()


def main() -> None:
    _load_env()
    st.set_page_config(page_title="Synthetic GOÄ invoices", layout="wide")
    st.title("Synthetic German medical invoices")
    st.caption("Hackathon MVP. Prices are calculated from the GOÄ catalog. This is not a certified billing engine.")

    catalog = load_catalog(ROOT / "data" / "service_catalog.json")
    library = load_scenarios(ROOT / "data" / "demo_scenarios.json")
    llm_ready = bool(os.environ.get("OPENAI_API_KEY", "").strip() and os.environ.get("OPENAI_MODEL", "").strip())

    st.subheader("Request")
    user_request = st.text_area(
        "What kind of synthetic case do you want?",
        value="Outpatient eyelid surgery for a private invoice demo.",
        height=100,
    )
    batch_kind = st.radio("What to generate", ["One scenario", "Mixed set of supported scenarios"])
    if batch_kind == "One scenario":
        scenario_id = st.selectbox(
            "Supported scenario",
            library.ids(),
            format_func=lambda item: library.by_id(item).label,
        )
        selected_ids = [scenario_id]
        st.info(library.by_id(scenario_id).note)
    else:
        selected_ids = st.multiselect(
            "Scenarios to cover",
            library.ids(),
            default=library.ids(),
            format_func=lambda item: library.by_id(item).label,
        )
        scenario_id = selected_ids[0] if selected_ids else library.ids()[0]
        st.caption("If the number of invoices is at least the number of selected scenarios, each selected scenario is used at least once.")
    count = st.slider("Number of invoices", 1, 10, 2)
    start_default = date.today() - timedelta(days=60)
    period = st.date_input("Service period", value=(start_default, date.today()))
    age_min, age_max = st.slider("Age range used for fictional dates of birth", 18, 95, (45, 85))

    if llm_ready:
        mode = st.radio("Generation mode", ["llm", "rule-based"], format_func=lambda item: "LLM" if item == "llm" else "Rule-based demo")
    else:
        mode = "rule-based"
        st.warning("No OPENAI_API_KEY and OPENAI_MODEL. Only the Rule-based demo is available. LLM mode was not silently replaced after a failed call; it is unavailable.")

    if st.button("Generate", type="primary"):
        if not isinstance(period, tuple) or len(period) != 2:
            st.error("Choose both the start and the end of the service period.")
            return
        period_start, period_end = period
        if period_end < period_start:
            st.error("The service period ends before it starts.")
            return
        if not selected_ids:
            st.error("Select at least one supported scenario.")
            return
        client = None
        model_name = None
        if mode == "llm":
            try:
                client = client_from_env()
                model_name = os.environ.get("OPENAI_MODEL")
            except LLMUnavailable as exc:
                st.error(str(exc))
                return
        with st.spinner("Generating and checking invoices..."):
            try:
                report = run_batch(
                    mode=mode,
                    scenario_id=scenario_id,
                    user_request=user_request,
                    count=count,
                    period_start=period_start,
                    period_end=period_end,
                    age_min=age_min,
                    age_max=age_max,
                    seed=None,
                    catalog=catalog,
                    library=library,
                    output_root=ROOT / "output",
                    client=client,
                    model_name=model_name,
                    scenario_ids=selected_ids,
                )
            except UnsupportedScenarioRequest as exc:
                st.error(str(exc))
                return
            except LLMGenerationError as exc:
                st.error(str(exc))
                for item in exc.errors:
                    st.write(f"- {item}")
                st.write(exc.stats)
                return
            except PlanRejected as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"Generation stopped: {exc}")
                return
        st.session_state["report"] = report

    report = st.session_state.get("report")
    if not report:
        st.caption("Generated files stay in output/. A new run gets its own folder.")
        return
    st.success(f"Mode: {report['mode']}")
    checks = report["checks"]
    st.subheader("Checks")
    st.write(
        {
            "Passed on the first attempt": checks.get("passed_on_first_attempt"),
            "Corrected after a retry": checks.get("corrected_after_retry"),
            "Rejected results": checks["rejected_results"],
            "Distinct scenarios": checks.get("distinct_scenarios"),
            "Distinct service sets": checks["distinct_service_sets"],
            "Invoice totals EUR": checks.get("gross_eur_values"),
            "LLM responses matching the schema": checks["llm_schema_pass_rate"],
            "Invoices passing the implemented rules": f"{checks['invoices_passing_implemented_rules']} of {checks['invoices_requested']}",
            "Correction attempts": checks["correction_attempts"],
            "Invoice IDs unique": checks["invoice_ids_unique"],
            "Seconds": report["elapsed_seconds"],
            "Model": report["model"],
            "Request ids": report.get("request_ids"),
            "Prompt version": report["prompt_version"],
            "Catalog version": report["catalog_version"],
        }
    )
    st.caption(report["seed_note"])
    st.caption(report["disclaimer"])
    run_dir = Path(report["run_dir"])
    st.download_button("Download ZIP of this run", data=_zip_run(run_dir), file_name=f"{run_dir.name}.zip")
    for item in report["invoices"]:
        st.markdown(f"### {item['invoice_number']} — {item['gross_eur']} EUR")
        st.write(item["case_summary"])
        st.write("Codes:", ", ".join(item["codes"]))
        json_bytes = Path(item["json"]).read_bytes()
        pdf_bytes = Path(item["pdf"]).read_bytes()
        left, right = st.columns(2)
        left.download_button("JSON", data=json_bytes, file_name=Path(item["json"]).name, key=f"json-{item['invoice_number']}")
        right.download_button("PDF", data=pdf_bytes, file_name=Path(item["pdf"]).name, mime="application/pdf", key=f"pdf-{item['invoice_number']}")
        st.json(json.loads(json_bytes.decode("utf-8")))


if __name__ == "__main__":
    main()
