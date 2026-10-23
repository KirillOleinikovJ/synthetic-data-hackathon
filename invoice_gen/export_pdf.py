from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from invoice_gen.models import Invoice
from invoice_gen.names import greeting_line, split_person

# Helvetica core fonts are Latin-1; fold common German chars for reliable PDF output.
_TRANSLATE = str.maketrans(
    {
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "–": "-",
        "—": "-",
        "€": "EUR",
    }
)


def _t(text: str) -> str:
    return str(text).translate(_TRANSLATE).encode("latin-1", "replace").decode("latin-1")


def _eur(value) -> str:
    return f"{value:.2f}".replace(".", ",") + " EUR"


def _d(value) -> str:
    return value.strftime("%d.%m.%Y")


def _patient_greeting(invoice: Invoice) -> str:
    last_name = invoice.patient.last_name or split_person(invoice.patient.full_name).last_name
    return greeting_line(invoice.patient.salutation, last_name)


def _fit_lines(pdf: FPDF, width: float, text: str, line_h: float) -> list[str]:
    lines = pdf.multi_cell(width, line_h, _t(text), align="L", dry_run=True, output="LINES")
    return lines or [""]


def _paint_row(
    pdf: FPDF,
    widths: tuple[float, ...],
    texts: list[str],
    line_h: float,
    font_size: float,
    *,
    style: str = "",
    on_break=None,
) -> None:
    pdf.set_font("Helvetica", style, font_size)
    wrapped = [_fit_lines(pdf, width - 1, text, line_h) for width, text in zip(widths, texts)]
    height = max(len(lines) for lines in wrapped) * line_h + 1
    if pdf.get_y() + height > pdf.page_break_trigger:
        pdf.add_page()
        if on_break is not None:
            on_break()
            pdf.set_font("Helvetica", style, font_size)
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    x = x0
    for width, lines in zip(widths, wrapped):
        pdf.rect(x, y0, width, height)
        pdf.set_xy(x + 0.4, y0 + 0.3)
        pdf.multi_cell(width - 1, line_h, "\n".join(lines), align="L")
        x += width
    pdf.set_xy(x0, y0 + height)


class InvoicePDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"Seite {self.page_no()}/{{nb}} | Synthetic Data on Demand", align="C")


def write_invoice_pdf(invoice: Invoice, path: Path | str) -> Path:
    """Render a German-style GOÄ invoice PDF from the same Invoice model as JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = InvoicePDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pr = invoice.provider
    pa = invoice.patient

    # Provider header
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, _t(pr.physician_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _t(pr.specialty), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        5,
        _t(f"{pr.address.street}, {pr.address.postal_code} {pr.address.city}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # Patient + meta
    left_x = pdf.l_margin
    pdf.set_xy(left_x, pdf.get_y())
    pdf.multi_cell(
        100,
        5,
        _t(
            f"{pa.salutation} {pa.full_name}\n"
            f"{pa.address.street}\n"
            f"{pa.address.postal_code} {pa.address.city}"
        ),
    )
    meta_y = pdf.get_y() - 15
    pdf.set_xy(120, meta_y)
    pdf.multi_cell(
        80,
        5,
        _t(
            f"Rechnungsdatum: {_d(invoice.issue_date)}\n"
            f"Rechnungs-Nr.: {invoice.invoice_number}\n"
            f"Patientennummer: {invoice.patient_number}"
        ),
    )
    pdf.set_y(max(pdf.get_y(), meta_y + 20))
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0,
        5,
        _t(
            f"{_patient_greeting(invoice)}\n\n"
            f"fuer aerztliche Bemuehungen bis {_d(invoice.service_until)} "
            f"erlaube ich mir zu berechnen: {_eur(invoice.totals.gross_eur)}.\n\n"
            f"Behandlung von {pa.salutation} {pa.full_name}, geb. {_d(pa.birth_date)}.\n"
            f"Diagnose(n): {invoice.diagnosis}\n"
            f"Berechnet nach der {invoice.billing_rule}."
        ),
    )
    pdf.ln(3)

    cols = (26, 14, 82, 14, 22, 32)
    headers = ("Datum / Sitzung", "Nr.", "Leistungsbezeichnung", "Anz.", "Faktor", "Betrag")

    def _header() -> None:
        _paint_row(pdf, cols, list(headers), 4, 8, style="B")

    _header()
    for item in invoice.line_items:
        quantity = str(int(item.quantity)) if item.quantity == int(item.quantity) else str(item.quantity)
        visit = item.service_date.strftime("%d.%m.%y")
        if item.encounter_id:
            visit = f"{visit}\n{item.encounter_id}"
        _paint_row(
            pdf,
            cols,
            [
                visit,
                item.code,
                item.description,
                quantity,
                f"{item.factor:.3f}".replace(".", ","),
                _eur(item.line_total_eur).replace(" EUR", ""),
            ],
            4,
            8,
            on_break=_header,
        )

    reasons = [
        item
        for item in invoice.line_items
        if item.factor_justification and item.factor > Decimal("2.3")
    ]
    if reasons:
        pdf.ln(2)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 9)
        pdf.multi_cell(0, 5, _t("Begruendung einer Steigerung ueber 2,3 (GOAE Par. 5)"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        for item in reasons:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                0,
                4,
                _t(
                    f"GOAE {item.code} am {_d(item.service_date)}, Faktor {item.factor}: "
                    f"{item.factor_justification}"
                ),
                new_x="LMARGIN",
                new_y="NEXT",
            )

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(
        0,
        6,
        _t(f"Summe aerztliche Leistung: {_eur(invoice.totals.services_eur)}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    if invoice.materials:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _t("Sachkosten / Auslagen Par. 10 GOAE"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        mcols = (120, 20, 40)
        for w, h in zip(mcols, ("Bezeichnung", "Menge", "Betrag")):
            pdf.cell(w, 6, _t(h), border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for mat in invoice.materials:
            row = (
                mat.description,
                str(int(mat.quantity)),
                _eur(mat.line_total_eur).replace(" EUR", ""),
            )
            for w, value in zip(mcols, row):
                pdf.cell(w, 5, _t(value), border=1)
            pdf.ln()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(
            0,
            6,
            _t(f"Summe Sachkosten: {_eur(invoice.totals.materials_eur)}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(
        0,
        7,
        _t(f"Rechnungsbetrag gesamt: {_eur(invoice.totals.gross_eur)}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(
        0,
        5,
        _t(
            f"Bitte ueberweisen Sie den Betrag bis {_d(invoice.payment_due_date)} auf folgendes Konto:\n"
            f"Bank: {invoice.bank.bank_name}\n"
            f"IBAN: {invoice.bank.iban}\n"
            f"BIC: {invoice.bank.bic}\n\n"
            f"Mit freundlichen Gruessen\n{pr.physician_name}"
        ),
    )
    if invoice.notes:
        pdf.ln(3)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, _t(invoice.notes))

    pdf.output(str(out))
    return out
