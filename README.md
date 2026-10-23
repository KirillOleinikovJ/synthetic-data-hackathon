# Synthetic Data on Demand

Hackathon MVP: synthetic German private invoices (GOÄ, ophthalmology) as JSON and PDF from the same invoice object.

The demo builds **three eyelid pathways** that show up in the sample PDFs and in the official fee schedule. Other diagnoses stay in the catalog and are not offered in the demo. This is not a certified billing engine, not a medical review, and not a privacy proof.

## Install

PowerShell on this machine blocks `Activate.ps1`. Call the virtualenv Python directly:

```powershell
cd c:\Users\Асус\synthetic-data-hackathon
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## API key

Copy `.env.example` to `.env` and set:

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (a model that supports structured outputs)
- `OPENAI_BASE_URL` only if you use an OpenAI-compatible endpoint

`.env` is gitignored. Without those two variables the interface offers only **Rule-based demo**. A failed LLM call is not replaced by that demo.

## Run

Rule-based demo (no API):

```powershell
.\.venv\Scripts\python.exe generate_invoice.py --mode rule-based --scenario dermatochalasis_bds --count 2
```

LLM mode:

```powershell
.\.venv\Scripts\python.exe generate_invoice.py --mode llm --scenario ptosis_bds --count 1 --request "Outpatient bilateral ptosis, private invoice"
```

Interface:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Each run creates `output/run-<timestamp>-<id>/` and leaves older runs in place. Invoice IDs are random. The folder contains JSON, PDF, and `report.json` (model, prompt version, catalog version, timing, check counts).

Scenarios: `dermatochalasis_bds`, `entropium`, `ptosis_bds`. At most 10 invoices per run. The service period must be at least 21 days.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests mock the API. A live call happens only when you run `--mode llm` with a key.

## What the model is allowed to do

The model returns a case plan: diagnosis id, laterality, relative-day events, material names, and a short summary. Python checks that plan against `data/demo_scenarios.json`, fills fictional identity with Faker, prices every line from `data/service_catalog.json` with `Decimal`, and writes one invoice. The model does not set points or totals.

Up to two correction attempts are sent back with the validator errors. After that the run stops with those errors.

The user text is sent as data. A request for another specialty, or for a different one of the three pathways than the one selected, is rejected instead of being swapped.

## Pricing

- Points: [GOÄ Anlage](https://www.gesetze-im-internet.de/go__1982/anlage.html)
- Factors: [GOÄ § 5](https://www.gesetze-im-internet.de/go__1982/__5.html). Personal services 1.0–3.5, threshold 2.3. Zuschläge 440–449 stay at factor 1.0.
- Point value used here: 0.0582873 EUR (0.114 DM / 1.95583).
- Rounding: Einfachsatz is half-up to the cent, then the line (Einfachsatz × factor × quantity) is half-up to the cent. Ziffer 34 at 2.3 is 40.23 EUR, which matches the sample invoices. A single multiply of points × point value × factor gives 40.22 and is not used.
- Materials (`OP-Set`, `Vicryl-Naht 6-0`, `Steri-Set`) are sample-invoice amounts, not GOÄ points.

Demo factor caps are per code in `data/demo_scenarios.json`. GOÄ 1311 may use up to 3.5 because the samples do. GOÄ 1306 stays at most 2.3 in this demo. Suture removal (2007) and dressing (200) are follow-up events only, and only in scenarios that list them. Entropion does not include dressing 200.

## Checks shown in the UI

Reported separately, not as one accuracy percentage:

- share of LLM replies that match the schema
- invoices that passed the implemented rules
- rejected replies and correction attempts
- unique invoice IDs
- how many different service-code sets were produced
- generation time

A seed changes the rule-based demo and the fictional names. It does not make LLM output reproducible. The report does not claim that the invoices match the statistics of real billing data.

`python -m invoice_gen.accuracy` only checks catalog arithmetic against the Anlage and writes a new folder under `output/`. It is not a score for the synthetic cases.

## Limits

- Three demo pathways, not the full ophthalmology catalog and not ICD.
- Rules were checked against the Anlage and the sample PDFs. They are not a complete GOÄ commentary.
- Sample PDFs sometimes bill combinations the Anlage excludes (5 together with 6, or 1240 beside 5/6). The demo follows the Anlage.
- Personal data is fictional. That is not a formal privacy guarantee.
- Live LLM behaviour depends on the configured model and was verified only when a key was present.
