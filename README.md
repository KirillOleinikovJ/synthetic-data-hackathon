# Synthetic Data on Demand

Allianz hackathon — synthetic German **GOÄ health invoices** (JSON + PDF).

## Run on Windows (important)

PowerShell often blocks `Activate.ps1`. **Do not activate** — call venv Python directly:

```powershell
cd c:\Users\Асус\synthetic-data-hackathon
.\.venv\Scripts\python.exe generate_invoice.py --seed 42 --count 3
```

Or double-click / run:

```powershell
.\run_demo.bat
```

Tests:

```powershell
.\run_tests.bat
```

If packages are missing:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Outputs land in `output\Rechnung-*.json` and `output\Rechnung-*.pdf`.

GOÄ check (official point values vs catalog, plus constraint pass rate):

```powershell
.\.venv\Scripts\python.exe -m invoice_gen.accuracy
```

## Layout

- `invoice_gen/` — model, generator, validators, exporters
- `data/service_catalog.json` — GOÄ codes from Allianz sample invoices
- `reference/invoices/` — sample PDFs from Max
- `generate_invoice.py` — CLI
