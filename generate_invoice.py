#!/usr/bin/env python3
"""Generate synthetic GOÄ invoices. LLM mode never falls back to the rule-based demo."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _ensure_venv() -> None:
    if os.environ.get("VIRTUAL_ENV"):
        return
    if not VENV_PYTHON.is_file():
        return
    if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(ROOT / "generate_invoice.py"), *sys.argv[1:]])


_ensure_venv()

from invoice_gen.catalog import load_catalog
from invoice_gen.llm_client import LLMGenerationError, LLMUnavailable, client_from_env
from invoice_gen.pipeline import UnsupportedScenarioRequest, run_batch
from invoice_gen.plans import PlanRejected
from invoice_gen.scenarios import load_scenarios


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _say(text: str) -> None:
    print(text.encode("cp1251", "replace").decode("cp1251"))


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("rule-based", "llm"), default="rule-based")
    parser.add_argument("--scenario", default="dermatochalasis_bds")
    parser.add_argument("--scenarios", default="", help="Comma-separated scenario ids for a mixed batch")
    parser.add_argument("--request", default="Synthetic outpatient eyelid case for a demo.")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--period-start", default="2026-01-06")
    parser.add_argument("--period-end", default="2026-03-03")
    parser.add_argument("--age-min", type=int, default=45)
    parser.add_argument("--age-max", type=int, default=85)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()

    catalog = load_catalog(ROOT / "data" / "service_catalog.json")
    library = load_scenarios(ROOT / "data" / "demo_scenarios.json")
    client = None
    model_name = None
    if args.mode == "llm":
        try:
            client = client_from_env()
            model_name = os.environ.get("OPENAI_MODEL")
        except LLMUnavailable as exc:
            print(exc)
            print("LLM mode was not run. The rule-based demo was not substituted.")
            return 2
    try:
        report = run_batch(
            mode=args.mode,
            scenario_id=args.scenario,
            user_request=args.request,
            count=args.count,
            period_start=date.fromisoformat(args.period_start),
            period_end=date.fromisoformat(args.period_end),
            age_min=args.age_min,
            age_max=args.age_max,
            seed=args.seed,
            catalog=catalog,
            library=library,
            output_root=args.out_dir,
            client=client,
            model_name=model_name,
            scenario_ids=[item.strip() for item in args.scenarios.split(",") if item.strip()] or None,
        )
    except (UnsupportedScenarioRequest, LLMGenerationError, PlanRejected, KeyError, ValueError) as exc:
        _say(str(exc))
        if isinstance(exc, LLMGenerationError):
            for item in exc.errors:
                _say(f"  - {item}")
            _say(f"Attempts: {exc.stats.get('schema_attempts')} rejected: {exc.stats.get('rejected')}")
        return 1
    _say(f"Mode: {report['mode']}")
    _say(f"Run: {report['run_dir']}")
    for item in report["invoices"]:
        _say(f"{item['invoice_number']} {item['scenario_id']} {item['gross_eur']} EUR")
        _say(f"  {item['pdf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
